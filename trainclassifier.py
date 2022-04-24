#!/usr/bin/env python
# coding: utf-8

# bb: if use full-atlocation for AtLocation: get 65-70 dev acc.
# bb: lama 2e-4 65
# 同样的lr下，大model比小model更容易只预测一样的...
import gc
from transformers import RobertaTokenizer, RobertaForSequenceClassification, RobertaModel
from transformers import BertTokenizer, BertModel
from torch.utils.data import Dataset, DataLoader
import torch
import random
from models.lama_knowledge_scorer import LAMAKnowledgeScorer

plm = "roberta-large"
lmlr = 1e-5
clslr = 1e-4
testname = "lama"


savename = f"{plm}_{testname}_{str(lmlr)}_{str(clslr)}_bestmodel.pt"
if testname == "conceptnet":
    testfile = "data/ckbc/conceptnet_high_quality.txt"
elif testname == "lama":
    testfile = "data/lama/lama_test.txt"

            
# logits = model(**inputs).logits
# criterion(logits, torch.tensor([0, 1, 1]))

# testfile = "data/ckbc/conceptnet_full.txt"
with open(testfile, 'r') as f:
    data = f.readlines()
random.shuffle(data)
# data = [i for i in data if i.strip().split('\t')[0] == 'AtLocation']
n_samples = len(data)
print("n_samples: ", n_samples)
data_stats = [int(i.strip().split('\t')[3]) for i in data]
print("n_pos_samples: ", sum(data_stats))

# print(len(data))
step = 0
best_valid_acc = 0
best_valid_f1 = 0
test_f1 = 0

def get_collator(tokenizer):
    def collator(batch):
        # inputs = tokenizer([h + " [SEP] " + r + " [SEP] " + t for (r, h, t), _ in batch], return_tensors='pt', padding=True)
        inputs = tokenizer([h + " | " + r + " | " + t for (r, h, t), _ in batch], return_tensors='pt', padding=True)
        labels = torch.tensor([int(_) for (r, h, t), _ in batch])
        return inputs.to("cuda"), labels.to("cuda")
    return collator

class lamadataset(torch.utils.data.Dataset):
    def __init__(self, _data):
        self.data = [i.strip().split('\t')[:3] for i in _data]
        self.label = [i.strip().split('\t')[3] for i in _data]
    def __len__(self):
        return len(self.data)
    def __getitem__(self, idx):
        return self.data[idx], self.label[idx]


model = LAMAKnowledgeScorer(plm)
if "roberta" in plm:
    tokenizer = RobertaTokenizer.from_pretrained("roberta-large")
else:
    tokenizer = BertTokenizer.from_pretrained("bert-base-cased")
trainset = lamadataset(data[:int(0.7 * n_samples)])
devset = lamadataset(data[int(0.7*n_samples): int(0.85*n_samples)])
testset = lamadataset(data[int(0.85*n_samples):])
# devset = lamadataset(test_data)
# testset = lamadataset(test_data)
trainloader = DataLoader(trainset, batch_size=32, collate_fn=get_collator(tokenizer), shuffle=True)
devloader = DataLoader(devset, batch_size=64, collate_fn=get_collator(tokenizer), shuffle=False)
testloader = DataLoader(testset, batch_size=64, collate_fn=get_collator(tokenizer), shuffle=False)
criterion = torch.nn.BCEWithLogitsLoss(reduction="mean") # torch.nn.CrossEntropyLoss()
"""
optimizer_grouped_parameters = [
    {
        "params": [p for n, p in model.named_parameters() if "classifier" not in n],
        "lr": 5e-5
    },
    {
        "params": [p for n, p in model.named_parameters() if "classifier" in n],
        "lr": 1e-3
    }
]
"""
# optimizer = torch.optim.AdamW(optimizer_grouped_parameters)
param_optimizer = list(model.named_parameters())
optimizer_grouped_parameters = [
    {'params': [p for n, p in param_optimizer
        if n[:7] == 'encoder']},  # only a bert model
    {'params': [p for n, p in param_optimizer
        if n[:7] != 'encoder'], 'lr': clslr}]
optimizer = torch.optim.Adam(optimizer_grouped_parameters, lr=lmlr)
optimizer.zero_grad()
def test(model, loader):
    pt = 0
    model.eval()
    print("validating...")
    acc_samples = 0
    acc_correct = 0
    for idx, (inputs, labels) in enumerate(loader):
        acc_samples += len(labels)
        with torch.no_grad():
            logits = model(inputs)
        # loss = criterion(logits, labels)
        # loss.backward()
        # acc_correct += torch.sum(torch.argmax(logits, dim=1) == labels).item()
        pt += torch.sum(logits > 0).item()
        acc_correct += torch.sum((logits.reshape(-1) > 0) == labels).item()
        if idx == 0:
            print(logits[:10], labels[:10])
    model.train()
    # print("prediction positive: ", pt/acc_samples)
    return acc_correct/acc_samples
acc_loss = 0
acc_samples = 0
acc_correct = 0
best_dev_acc = 0
model.train()
no_improvement = 5
for r in range(10):
    for idx, (inputs, labels) in enumerate(trainloader):
        if (idx + 1) % 50 == 0:
            # print(acc_loss/acc_samples)
            # print(acc_correct/acc_samples)
            acc_loss = 0
            acc_samples = 0
            acc_correct = 0
        if (idx + 1) % 200 == 0:
            acc_dev = test(model, devloader)
            if best_dev_acc < acc_dev:
                best_dev_acc = acc_dev
                torch.save(model, savename)
                no_improvement = 0
            else:
                no_improvement += 1
                if no_improvement == 5:
                    break
            print(f"step {idx}: ",acc_dev)
        acc_samples += len(labels)
        # logits = model(**inputs).logits
        logits = model(inputs).reshape(-1)
        # loss = criterion(logits, labels)
        loss = criterion(logits, labels.float())
        loss.backward()
        acc_loss += loss.item()
        # acc_correct += torch.sum(torch.argmax(logits, dim=1) == labels).item()
        acc_correct += torch.sum((logits > 0) == labels).item()
        optimizer.step()
        optimizer.zero_grad()
        model.zero_grad()
        # print(loss)
        # break
    # print("dubugging: ")
    # print("train acc: ", test(model, trainloader))
    # print("dev acc: ", test(model, devloader))
    if no_improvement == 5:
        break

model = torch.load(savename)
print("test results: ", test(model, testloader))
