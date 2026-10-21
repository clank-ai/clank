"""Design 0002 §2.2: every kind of record is one Pydantic class, declared once, whose every field has a label and help
for the explain key."""

import pytest
from pydantic import BaseModel, Field

from clank import registry
from clank.kernel.records import Registry, RegistryError, Settings, StateKind, undocumented_fields


class Sample(Settings):
    KIND = "sample"
    LABEL = "Sample"
    HELP = "A kind used by these tests."

    size: int = Field(3, title="Size", description="How big it is.")


class Inner(BaseModel):
    depth: int = Field(1, title="Depth")


class Outer(StateKind):
    KIND = "outer"
    LABEL = "Outer"
    HELP = "A kind with a nested model."

    id: str = Field(title="Id", description="Its name.")
    inner: list[Inner] = Field(default_factory=list, title="Inner", description="Nested records.")


def test_a_kind_declared_twice_is_refused() -> None:
    kinds = Registry()
    kinds.add(Sample)
    with pytest.raises(RegistryError, match="sample"):
        kinds.add(Sample)


def test_a_kind_missing_its_constants_is_refused() -> None:
    class Nameless(StateKind):
        pass

    with pytest.raises(RegistryError, match="KIND"):
        Registry().add(Nameless)


def test_a_field_without_a_label_or_help_is_found_in_nested_models_too() -> None:
    assert undocumented_fields(Outer) == ["inner.depth: no help"]
    assert undocumented_fields(Sample) == []


def test_settings_kinds_name_their_folder() -> None:
    assert Sample.folder() == "samples"


def test_every_kind_clank_declares_has_every_field_documented() -> None:
    assert {kind.KIND: undocumented_fields(kind) for kind in registry.kinds().all()} == {
        kind.KIND: [] for kind in registry.kinds().all()
    }
