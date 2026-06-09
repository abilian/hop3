# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the generic object registry."""

from __future__ import annotations

import pytest

from hop3.lib.registry import (
    Metadata,
    Registry,
    lookup,
    register,
    registry,
)


@pytest.fixture
def reg() -> Registry:
    """A fresh, isolated registry for each test."""
    return Registry()


class TestMetadata:
    """Tests for the Metadata frozen dataclass."""

    def test_defaults_are_empty(self):
        metadata = Metadata()

        assert metadata.name == ""
        assert metadata.module == ""
        assert metadata.tag == ""
        assert metadata.extras == {}

    def test_extras_default_is_independent_per_instance(self):
        first = Metadata()
        second = Metadata()

        first.extras["k"] = "v"

        assert second.extras == {}

    def test_fields_are_stored(self):
        metadata = Metadata(name="foo", module="bar", tag="t", extras={"a": 1})

        assert metadata.name == "foo"
        assert metadata.module == "bar"
        assert metadata.tag == "t"
        assert metadata.extras == {"a": 1}

    def test_is_frozen(self):
        metadata = Metadata()

        with pytest.raises(AttributeError):
            setattr(metadata, "name", "changed")  # noqa: B010


class Animal:
    pass


class Dog(Animal):
    pass


class Cat(Animal):
    pass


def sample_function():
    pass


class TestRegister:
    """Tests for Registry.register."""

    def test_register_returns_the_object(self, reg: Registry):
        result = reg.register(Dog)

        assert result is Dog

    def test_register_defaults_name_from_dunder_name(self, reg: Registry):
        reg.register(Dog)

        metadata = reg.get_metadata(Dog)
        assert metadata.name == "Dog"

    def test_register_defaults_module_from_dunder_module(self, reg: Registry):
        reg.register(Dog)

        metadata = reg.get_metadata(Dog)
        assert metadata.module == Dog.__module__

    def test_register_explicit_name_overrides_default(self, reg: Registry):
        reg.register(Dog, name="canine")

        assert reg.get_metadata(Dog).name == "canine"

    def test_register_explicit_module_overrides_default(self, reg: Registry):
        reg.register(Dog, module="my.module")

        assert reg.get_metadata(Dog).module == "my.module"

    def test_register_stores_tag(self, reg: Registry):
        reg.register(Dog, tag="pet")

        assert reg.get_metadata(Dog).tag == "pet"

    def test_register_extras_default_is_empty_dict(self, reg: Registry):
        reg.register(Dog)

        assert reg.get_metadata(Dog).extras == {}

    def test_register_stores_extras(self, reg: Registry):
        reg.register(Dog, extras={"legs": 4})

        assert reg.get_metadata(Dog).extras == {"legs": 4}

    def test_register_works_on_a_function(self, reg: Registry):
        reg.register(sample_function)

        assert reg.get_metadata(sample_function).name == "sample_function"

    def test_re_registering_overwrites_metadata(self, reg: Registry):
        reg.register(Dog, tag="first")
        reg.register(Dog, tag="second")

        assert reg.get_metadata(Dog).tag == "second"
        # Same key, so only one entry exists.
        assert len(list(reg.items())) == 1


class TestLookupAll:
    """Tests for Registry.lookup with an empty key (return everything)."""

    def test_empty_registry_returns_empty_list(self, reg: Registry):
        assert reg.lookup() == []

    def test_returns_all_registered_objects(self, reg: Registry):
        reg.register(Dog)
        reg.register(Cat)

        result = reg.lookup()

        assert set(result) == {Dog, Cat}

    def test_tag_filters_when_listing_all(self, reg: Registry):
        reg.register(Dog, tag="pet")
        reg.register(Cat, tag="wild")

        assert reg.lookup(tag="pet") == [Dog]


class TestLookupByName:
    """Tests for Registry.lookup with a string key."""

    def test_lookup_by_name_returns_matching_object(self, reg: Registry):
        reg.register(Dog, name="canine")

        assert reg.lookup("canine") == [Dog]

    def test_lookup_by_name_no_match_returns_empty(self, reg: Registry):
        reg.register(Dog, name="canine")

        assert reg.lookup("feline") == []

    def test_lookup_by_name_returns_all_with_same_name(self, reg: Registry):
        reg.register(Dog, name="animal")
        reg.register(Cat, name="animal")

        assert set(reg.lookup("animal")) == {Dog, Cat}

    def test_lookup_by_name_with_tag_filters(self, reg: Registry):
        reg.register(Dog, name="animal", tag="pet")
        reg.register(Cat, name="animal", tag="wild")

        assert reg.lookup("animal", tag="pet") == [Dog]


class TestLookupByType:
    """Tests for Registry.lookup with a type key."""

    def test_lookup_by_type_matches_subclasses(self, reg: Registry):
        reg.register(Dog)
        reg.register(Cat)

        assert set(reg.lookup(Animal)) == {Dog, Cat}

    def test_lookup_by_type_matches_exact_class(self, reg: Registry):
        reg.register(Dog)
        reg.register(Cat)

        assert reg.lookup(Dog) == [Dog]

    def test_lookup_by_type_matches_registered_instances(self, reg: Registry):
        instance = Dog()
        reg.register(instance, name="rex")

        assert reg.lookup(Animal) == [instance]

    def test_lookup_by_type_unrelated_class_returns_empty(self, reg: Registry):
        reg.register(Dog)

        assert reg.lookup(Cat) == []

    def test_lookup_by_type_with_tag_filters(self, reg: Registry):
        reg.register(Dog, tag="pet")
        reg.register(Cat, tag="wild")

        assert reg.lookup(Animal, tag="wild") == [Cat]

    def test_lookup_by_type_ignores_non_matching_instances(self, reg: Registry):
        # An instance of an unrelated type is registered, then we look up by a
        # type it is not an instance of.
        instance = Cat()
        reg.register(instance, name="felix")

        assert reg.lookup(Dog) == []


class TestLookupInvalidKey:
    """Tests for Registry.lookup error paths."""

    @pytest.mark.parametrize("bad_key", [123, 4.5, ["list"], {"dict": 1}])
    def test_invalid_key_type_raises_type_error(self, reg: Registry, bad_key):
        with pytest.raises(TypeError, match="Invalid key type"):
            reg.lookup(bad_key)


class TestDunderAndAccessors:
    """Tests for __iter__, items, __contains__, get_metadata, clear."""

    def test_contains_true_for_registered(self, reg: Registry):
        reg.register(Dog)

        assert Dog in reg

    def test_contains_false_for_unregistered(self, reg: Registry):
        assert Dog not in reg

    def test_iter_yields_registered_keys(self, reg: Registry):
        reg.register(Dog)
        reg.register(Cat)

        assert set(iter(reg)) == {Dog, Cat}

    def test_items_returns_object_metadata_pairs(self, reg: Registry):
        reg.register(Dog, tag="pet")

        items = dict(reg.items())

        assert items[Dog].tag == "pet"

    def test_get_metadata_returns_metadata(self, reg: Registry):
        reg.register(Dog, name="canine")

        metadata = reg.get_metadata(Dog)

        assert isinstance(metadata, Metadata)
        assert metadata.name == "canine"

    def test_get_metadata_missing_raises_key_error(self, reg: Registry):
        with pytest.raises(KeyError):
            reg.get_metadata(Dog)

    def test_clear_empties_the_registry(self, reg: Registry):
        reg.register(Dog)
        reg.register(Cat)

        reg.clear()

        assert reg.lookup() == []
        assert Dog not in reg


class TestModuleLevelSingleton:
    """Tests for the module-level registry/register/lookup singletons.

    These mutate shared state, so each test restores the singleton afterwards.
    """

    @pytest.fixture(autouse=True)
    def _restore_singleton(self):
        saved = dict(registry.registered)
        yield
        registry.registered.clear()
        registry.registered.update(saved)

    def test_module_register_uses_shared_registry(self):
        register(Dog, tag="pet")

        assert Dog in registry
        assert registry.get_metadata(Dog).tag == "pet"

    def test_module_lookup_sees_module_register(self):
        register(Dog, name="shared-canine")

        assert lookup("shared-canine") == [Dog]
