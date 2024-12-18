import re
import typing
import pathlib
import unidecode
import owlready2 as owlready
from lazy_property import LazyProperty
from ontologies import PATH as PATH_ONTOLOGY


PATH_ONTOLOGY = PATH_ONTOLOGY / "ontology.owl"
PATTERN_SYMBOLS = re.compile(r"[^A-Za-z\d_]")


def first(iterable: typing.Iterable[typing.Any]) -> typing.Any:
    return next(iter(iterable))


def first_or_none(iterable: typing.Iterable[typing.Any]) -> typing.Any:
    try:
        return first(iterable)
    except StopIteration:
        return None


def get_filtered_instances(cls: owlready.ThingClass, namespace: str) -> typing.List[owlready.Thing]:
    return [entity for entity in cls.instances() if entity.namespace.name == namespace]


def human_name(cls_or_instance: owlready.ThingClass | owlready.Thing) -> str:
    return first_or_none(cls_or_instance.fancyName) or cls_or_instance.name


def overlap(a: typing.Iterable, b: typing.Iterable) -> bool:
    met_in_a = set()
    met_in_b = set()
    iter_a = iter(a)
    iter_b = iter(b)
    over_a = False
    over_b = False
    while not (over_a and over_b):
        if not over_a:
            try:
                item_a = next(iter_a)
                if item_a in met_in_b:
                    return True
                met_in_a.add(item_a)
            except StopIteration:
                over_a = True
        if not over_b:
            try:
                item_b = next(iter_b)
                if item_b in met_in_a:
                    return True
                met_in_b.add(item_b)
            except StopIteration:
                over_b = True
    return False


def replace_symbols_with(name: str, replacement: str) -> str:
    replaced = PATTERN_SYMBOLS.sub(replacement, name)
    while replaced.endswith(replacement):
        replaced = replaced[:-1]
    return replaced


def subtype(cls1: owlready.ThingClass, cls2: owlready.ThingClass, strict: bool = False) -> bool:
    return overlap([cls1], cls2.descendants(include_self=not strict))


def supertype(cls1: owlready.ThingClass, cls2: owlready.ThingClass, strict: bool = False) -> bool:
    return overlap([cls1], cls2.ancestors(include_self=not strict))


def owl_name(name: str, instance: bool = True) -> str:
    name = unidecode.unidecode(name)
    name = name.strip()
    name = replace_symbols_with(name, "_")
    name = name.lower()
    if not instance:
        name = name.capitalize()
    return name


class KnowledgeGraph:
    def __init__(self, path: pathlib.Path = PATH_ONTOLOGY) -> None:
        self._path = path
        self._uri = path.as_uri()

    @property
    def path(self) -> pathlib.Path:
        return self._path

    @LazyProperty
    def onto(self) -> owlready.Ontology:
        return owlready.get_ontology(self._uri).load(only_local=True, reload=True, reload_if_newer=True)

    def _find_root_class(self):
        things = set()
        for cls in self.onto.classes():
            if cls.ancestors() == {owlready.Thing, cls}:
                things.add(cls)
        if len(things) == 1:
            return first(things)
        else:
            return owlready.Thing

    def add_property(self, cls_or_instance: owlready.ThingClass | owlready.Thing,
                     property: str | owlready.ObjectPropertyClass,
                     value: owlready.ThingClass | owlready.Thing | str) -> None:
        if isinstance(property, owlready.ObjectPropertyClass):
            property = property.name
        property_values = getattr(cls_or_instance, property)
        if value not in property_values:
            property_values.append(value)

    def set_class_of_instance(self, instance: owlready.Thing, cls: str | owlready.ThingClass) -> owlready.Thing:
        initial = set(instance.is_instance_of)
        too_generic_types = [c for c in instance.is_instance_of if supertype(c, cls, strict=True)]
        too_specific_types = [c for c in instance.is_instance_of if subtype(c, cls, strict=False)]
        if len(too_generic_types) > 0:
            for type in too_generic_types:
                instance.is_instance_of.remove(type)
        if len(too_specific_types) == 0:
            instance.is_instance_of.append(cls)
        if len(instance.is_instance_of) > 1 and owlready.ThingClass in instance.is_instance_of:
            instance.is_instance_of.remove(owlready.Thing)
        final = set(instance.is_instance_of)
        for snapshot in [initial, final]:
            if owlready.Thing in snapshot:
                snapshot.remove(owlready.Thing)
        else:
            pass
        return instance

    def add_instance(self, cls: str | owlready.ThingClass, name: str,
                     add_to_class_if_existing: bool = True) -> owlready.Thing:
        fancy_name = name
        name = owl_name(name)
        cls = self.onto[cls] if isinstance(cls, str) else cls
        instance = first_or_none(filter(lambda i: i.name == name, cls.instances()))
        if instance is not None:
            if add_to_class_if_existing:
                self.set_class_of_instance(instance, cls)
            else:
                raise KeyError(f"Instance {name} already exists in classes {instance.is_instance_of}")
        else:
            instance = cls(name)
        if self.onto.fancyName is not None and name != fancy_name:
            self.add_property(instance, "fancyName", fancy_name)
        return instance

    def merge_instances(self, instance1: owlready.Thing, instance2: owlready.Thing, cls: owlready.ThingClass) -> bool:
        all_instances = [inst for inst in cls.instances()]
        if not (instance1 in all_instances):
            return False
        if not (instance2 in all_instances):
            return False
        for prop in instance2.get_properties():
            if prop.name != 'fancyName':
                prop_values = getattr(instance2, prop.name)
                for value in prop_values:
                    self.add_property(instance1, prop.name, value)
        owlready.destroy_entity(instance2)
        return True

    def visit_classes_depth_first(self, root: str | owlready.ThingClass | None = None, postorder=True) -> \
            typing.Iterable[owlready.ThingClass]:
        root = self._find_root_class() if root is None else root
        root = self.onto[root] if isinstance(root, str) else root
        if not postorder:
            yield root
        for child in root.subclasses():
            yield from self.visit_classes_depth_first(child, postorder)
        if postorder:
            yield root

    def save(self) -> None:
        self.onto.save(str(self._path))

    def __enter__(self) -> "KnowledgeGraph":
        # self.onto
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        # self.save()
        pass


def name_to_snake_case(name: str) -> str:
    return name.replace(" ", "_").lower()
