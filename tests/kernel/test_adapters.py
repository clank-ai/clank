"""Design 0002 §2.10: each kind of adapter has an interface and the list of its adapters; an adapter that does not
implement the whole interface, has no name, label or platform, or reuses a name, is refused."""

from abc import abstractmethod

import pytest

from clank.kernel.adapters import Adapter, AdapterError, AdapterKind, Capability


class Speaker(Adapter):
    """A made-up kind of adapter."""

    @abstractmethod
    def speak(self) -> str:
        """What it says."""


class Loud(Speaker):
    NAME = "loud"
    LABEL = "Loud"
    PLATFORMS = ("win32", "linux")

    def capabilities(self) -> list[Capability]:
        return [Capability("shout", True, "always")]

    def speak(self) -> str:
        return "HELLO"


class Quiet(Speaker):
    NAME = "quiet"
    LABEL = "Quiet"
    PLATFORMS = ("darwin",)

    def capabilities(self) -> list[Capability]:
        return [Capability("shout", False, "it cannot")]

    def speak(self) -> str:
        return "hello"


class Mute(Speaker):
    NAME = "mute"
    LABEL = "Mute"
    PLATFORMS = ("linux",)

    def capabilities(self) -> list[Capability]:
        return []


class Nameless(Loud):
    NAME = ""


def kind(*adapters: type[Speaker]) -> AdapterKind[Speaker]:
    return AdapterKind("speaker", "Things that speak.", Speaker, adapters)


def test_a_kind_lists_its_adapters_and_finds_them_by_name_and_platform() -> None:
    speakers = kind(Loud, Quiet)
    assert speakers.all() == [Loud, Quiet]
    assert speakers.get("quiet") is Quiet
    assert speakers.for_platform("linux") == [Loud]


def test_an_unknown_adapter_is_refused_naming_the_known_ones() -> None:
    with pytest.raises(AdapterError, match="loud, quiet"):
        kind(Loud, Quiet).get("whisper")


def test_an_adapter_missing_a_method_of_the_interface_is_refused() -> None:
    with pytest.raises(AdapterError, match="speak"):
        kind(Loud, Mute)  # type: ignore[type-abstract]


def test_an_adapter_without_a_name_or_with_a_name_used_twice_is_refused() -> None:
    with pytest.raises(AdapterError, match="NAME"):
        kind(Nameless)
    with pytest.raises(AdapterError, match="loud"):
        kind(Loud, Loud)


def test_an_adapter_of_another_kind_is_refused() -> None:
    with pytest.raises(AdapterError, match="Speaker"):
        AdapterKind("speaker", "Things that speak.", Speaker, [Capability])  # type: ignore[type-var]
