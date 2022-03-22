import os
import openai
from nltk import sent_tokenize

from data_utils.data_utils import get_ent_tuple_from_sentence,\
    get_gpt3_prompt_mask_filling, fix_ent_tuples


class GPT3:
    def __init__(self):
        openai.api_key = os.getenv("OPENAI_API_KEY")

    def get_raw_response(self,
                         prompt,
                         engine="text-davinci-002",
                         temperature=1.,
                         max_tokens=30,
                         top_p=1.,
                         frequency_penalty=0,
                         presence_penalty=0,
                         logprobs=0,
                         n=1):
        return openai.Completion.create(
            engine=engine,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            logprobs=logprobs,
            n=n)

    def get_ent_tuples(self, prompt, n):
        gpt3_prompt = get_gpt3_prompt_mask_filling(prompt=prompt)

        choices = []
        while n > 0:
            raw_response = self.get_raw_response(
                prompt=gpt3_prompt, n=min(n, 128))
            choices.extend(raw_response['choices'])
            n -= min(n, 128)

        ent_tuples = []
        for choice in choices:
            try:
                sent = choice['text'].strip().strip('.')
                assert '\n' not in sent
                assert len(sent_tokenize(sent)) == 1

                tokens = choice['logprobs']['tokens']
                token_logprobs = choice['logprobs']['token_logprobs']

                sent_logprob = 0.
                for token, token_logprob in zip(tokens, token_logprobs):
                    if token == '<|endoftext|>':
                        break
                    elif token not in ['\n', '.']:
                        assert token in sent
                        sent_logprob += token_logprob

                ent_tuple = get_ent_tuple_from_sentence(
                    sent=sent, prompt=prompt)
                ent_tuple['logprob'] = sent_logprob

                ent_tuples.append(ent_tuple)

            except:
                print('an error.')
                print('choice:', choice)

        ent_tuples = fix_ent_tuples(raw_ent_tuples=ent_tuples)

        return ent_tuples

    # def get_paraphrase_prompt(self, prompt, ent_pair):