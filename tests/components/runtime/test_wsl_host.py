"""Design 0003 §2 and decision 0030: the WSL host does everything inside its distribution with one `bash -c` script per
question, each answering one line: a start answers with the engine's identity once its command line is its own, or
the distribution's own words for why it could not start; a signal goes only to the same process; a question the
distribution leaves unanswered says nothing of the engine (neither alive nor gone, and a stop not done); a file's
facts, the home folder and a port's listener are read there; WSL's list of distributions is read from its UTF-16; and
a step of an install runs in the distribution, its output followed line by line, its process group ended there when it
is canceled."""

from collections.abc import Callable, Sequence

import pytest

from clank.components.runtime.hosts.host import HostError, ProcessIdentity, command_hash
from clank.components.runtime.hosts.wsl import SCRIPTS, WslHost
from clank.kernel.processes import decode

ENGINE = ["/home/<you>/src/kvmem-llama.cpp/build/bin/llama-kvmem-server", "-m", "/m/model.gguf"]
HASH = command_hash(ENGINE)


class Wsl:
    """wsl.exe as a test sets it: each script's answer by its name, every call kept."""

    def __init__(self, answers: dict[str, str | None]) -> None:
        self.answers = answers
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str], timeout: float = 15.0) -> str | None:
        self.calls.append(list(argv))
        if list(argv[:2]) == ["wsl.exe", "--list"]:
            return self.answers.get("list")
        name = argv[6].split("\n", 1)[0].removeprefix("# clank: ")
        return self.answers.get(name)


def test_a_start_runs_its_script_in_the_distribution_and_answers_with_the_engines_identity() -> None:
    wsl = Wsl({"spawn": f"ok 4242 98765 {HASH}\n"})
    identity = WslHost(wsl, "Ubuntu").spawn(ENGINE, {"CUDA_DEVICE_ORDER": "PCI_BUS_ID"}, "/opt/kvmem", PATH)
    assert identity == ProcessIdentity("wsl:Ubuntu", 4242, "98765", HASH)
    assert wsl.calls == [
        [
            "wsl.exe", "-d", "Ubuntu", "-e", "bash", "-c", SCRIPTS["spawn"], "clank",
            "/opt/kvmem", str(PATH), "CUDA_DEVICE_ORDER=PCI_BUS_ID", "--", *ENGINE,
        ]
    ]  # fmt: skip


PATH = __import__("pathlib").PureWindowsPath(r"C:\Users\<you>\.clank\logs\processes\main.log")


def test_a_start_the_distribution_refuses_is_said_in_its_own_words() -> None:
    wsl = Wsl({"spawn": "error cannot start /opt/missing: no such program\n"})
    with pytest.raises(HostError, match="cannot start /opt/missing: no such program"):
        WslHost(wsl, "Ubuntu").spawn(["/opt/missing"], {}, "/", PATH)
    with pytest.raises(HostError, match="WSL did not answer for the distribution Ubuntu"):
        WslHost(Wsl({}), "Ubuntu").spawn(ENGINE, {}, "/", PATH)


def test_alive_and_stop_take_the_whole_identity_to_the_distribution() -> None:
    identity = ProcessIdentity("wsl:Ubuntu", 4242, "98765", HASH)
    wsl = Wsl({"alive": "alive\n", "stop": "killed\n"})
    host = WslHost(wsl, "Ubuntu")
    assert host.alive(identity)
    assert host.stop(identity, 30) == "killed"
    assert wsl.calls[-1][-4:] == ["4242", "98765", HASH, "30"]
    assert WslHost(Wsl({"alive": "gone\n"}), "Ubuntu").alive(identity) is False
    other = ProcessIdentity("local", 4242, "98765", HASH)
    assert host.alive(other) is False, "another host's process is not this one's"


def test_a_distribution_that_does_not_answer_says_nothing_of_the_engine() -> None:
    """A busy WSL can leave a question unanswered: the engine is then neither alive nor gone, and a stop is not done."""
    identity = ProcessIdentity("wsl:Ubuntu", 4242, "98765", HASH)
    silent = WslHost(Wsl({}), "Ubuntu")
    assert silent.alive(identity) is None
    with pytest.raises(HostError, match=r"did not answer.*may still run"):
        silent.stop(identity, 30)


def test_a_files_facts_the_home_folder_and_a_ports_listener_are_read_there() -> None:
    wsl = Wsl(
        {
            "size": "11358\n",
            "sha256": "ab" * 32 + "\n",
            "home": "/home/<you>\n",
            "listener": 'LISTEN 0 4096 127.0.0.1:18200 0.0.0.0:* users:(("llama-kvmem-ser",pid=41873,fd=3))\n',
        }
    )
    host = WslHost(wsl, "Ubuntu")
    assert (host.exists("/m/f"), host.size("/m/f"), host.sha256("/m/f")) == (True, 11358, "ab" * 32)
    assert host.expand("~/.clank/models") == "/home/<you>/.clank/models"
    assert host.listener(18200) == "llama-kvmem-ser (process 41873)"
    none = WslHost(Wsl({"size": "none\n", "sha256": "none\n", "listener": ""}), "Ubuntu")
    assert (none.exists("/m/f"), none.size("/m/f"), none.sha256("/m/f"), none.listener(18200)) == (
        False,
        None,
        None,
        None,
    )


def test_the_distributions_are_read_from_wsls_utf16_list() -> None:
    listed = decode("Ubuntu-22.04\r\nUbuntu\r\ndocker-desktop\r\n".encode("utf-16-le"))
    assert WslHost.distributions(Wsl({"list": listed})) == ["Ubuntu-22.04", "Ubuntu", "docker-desktop"]
    assert WslHost.distributions(Wsl({})) == []


def test_a_short_commands_output_is_read_there_whatever_its_exit_status() -> None:
    wsl = Wsl({"output": "usage: llama-kvmem-server -m model.gguf\n"})
    assert WslHost(wsl, "Ubuntu").output(["/opt/kvmem/llama-kvmem-server", "--help"]) == (
        "usage: llama-kvmem-server -m model.gguf\n"
    )
    assert wsl.calls[-1][-2:] == ["/opt/kvmem/llama-kvmem-server", "--help"]
    assert WslHost(Wsl({}), "Ubuntu").output(["x"]) is None


class Stream:
    """wsl.exe followed line by line, as a test sets it: the lines it writes, then its exit status (None: canceled)."""

    def __init__(self, lines: list[str], status: int | None) -> None:
        self.lines = lines
        self.status = status
        self.calls: list[list[str]] = []

    def __call__(
        self, argv: Sequence[str], line: Callable[[str], None], *, canceled: Callable[[], bool] = lambda: False
    ) -> int | None:
        self.calls.append(list(argv))
        for text in self.lines:
            line(text)
        return self.status


def test_a_step_runs_its_script_in_the_distribution_and_each_line_but_its_group_is_given() -> None:
    stream = Stream(["clank-group 4242 98765", "one", "two"], 3)
    lines: list[str] = []
    host = WslHost(Wsl({}), "Ubuntu", stream=stream)
    env = {"MAMBA_ROOT_PREFIX": "/e/mamba"}
    assert host.run_step(["ninja", "-C", "build"], env, "/e", lines.append, lambda: False) == 3
    assert lines == ["one", "two"]
    assert stream.calls == [
        [
            "wsl.exe", "-d", "Ubuntu", "-e", "bash", "-c", SCRIPTS["step"], "clank",
            "/e", "MAMBA_ROOT_PREFIX=/e/mamba", "--", "ninja", "-C", "build",
        ]
    ]  # fmt: skip


def test_a_canceled_step_ends_its_process_group_in_the_distribution() -> None:
    wsl = Wsl({"end": "stopped\n"})
    host = WslHost(wsl, "Ubuntu", stream=Stream(["clank-group 4242 98765", "compiling"], None))
    assert host.run_step(["ninja"], {}, "/e", lambda text: None, lambda: True) is None
    assert wsl.calls == [["wsl.exe", "-d", "Ubuntu", "-e", "bash", "-c", SCRIPTS["end"], "clank", "4242", "98765"]]


def test_a_step_wsl_does_not_run_is_said() -> None:
    host = WslHost(Wsl({}), "Ubuntu", stream=Stream([], None))
    with pytest.raises(HostError, match="WSL did not run the step in the distribution Ubuntu"):
        host.run_step(["ninja"], {}, "/e", lambda text: None, lambda: False)
