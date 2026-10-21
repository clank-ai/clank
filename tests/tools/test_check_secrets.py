"""Design 0001 §8.4: the secrets check finds keys, tokens, home folders and machine identifiers in any text file,
names the file, line and kind but never the value, skips files that are not text, and leaves placeholders alone."""

from pathlib import Path

from tools.check_secrets import patterns, scan, scan_text

DEFAULT = patterns(None, None, "Clank")

# Fake secrets are assembled when the tests run, so that this file itself contains none.
FAKES = {
    "a private key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "a GitHub token": "gh" + "p_" + "A1b2" * 9,
    "an API key (sk-...)": "s" + "k-" + "proj-" + "x" * 24,
    "an AWS access key": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "a Google API key": "AI" + "za" + "A" * 35,
    "a Hugging Face token": "h" + "f_" + "a" * 34,
    "a Slack token": "xo" + "xb-" + "1234567890-abc",
    "a Windows home folder": "C:" + "\\Users\\" + "alice\\project",
    "a macOS home folder": "/Us" + "ers/alice/project",
    "a Linux home folder": "/ho" + "me/alice/project",
    "a GPU identifier": "GPU-" + "0123abcd-0123-4567-89ab-0123456789ab",
    "a network hardware address": "00:1A:" + "2B:3C:4D:5E",
}


def test_each_kind_of_secret_is_found_and_named() -> None:
    for kind, value in FAKES.items():
        found = scan_text("notes.md", f"some text {value} more text\n", DEFAULT)
        assert [finding.kind for finding in found] == [kind], kind


def test_a_finding_names_the_file_and_line_but_not_the_value() -> None:
    value = FAKES["a GitHub token"]
    [finding] = scan_text("docs/notes.md", f"first line\ntoken {value}\n", DEFAULT)
    assert str(finding) == "docs/notes.md:2: looks like a GitHub token"
    assert value not in str(finding)


def test_placeholders_and_home_shorthand_are_not_findings() -> None:
    text = "C:\\Users\\<you>\\x and ~/.clank and /home/<you>/x and C:\\Users\\Public and %APPDATA%\\Python\n"
    assert scan_text("guide.md", text, DEFAULT) == []


def test_the_names_of_the_user_and_the_computer_are_found_unless_generic() -> None:
    compiled = patterns("alice", "alices-laptop", "Clank")
    found = scan_text("x.md", "made by alice on alices-laptop\n", compiled)
    assert sorted(finding.kind for finding in found) == ["the user's name", "this computer's name"]
    assert "the user's name" not in patterns("runner", None, "Clank")


def test_the_users_of_containers_and_services_are_generic_names() -> None:
    # Inside a sandbox the check runs as the container's user; such names are also words of this repository.
    for name in ("node", "agent", "clank", "nobody"):
        assert "the user's name" not in patterns(name, None, "Clank"), name


def test_the_repositorys_own_home_on_github_is_not_personal() -> None:
    assert scan_text("x.md", "https://github.com/alice/Clank\n", patterns("alice", None, "Clank")) == []


def test_files_that_are_not_text_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00" + FAKES["a GitHub token"].encode())
    (tmp_path / "notes.md").write_text(FAKES["an AWS access key"] + "\n", encoding="utf-8")
    found = scan(tmp_path, [Path("image.png"), Path("notes.md")], DEFAULT)
    assert [(finding.path, finding.kind) for finding in found] == [("notes.md", "an AWS access key")]


def test_the_check_does_not_trip_on_its_own_patterns() -> None:
    source = Path(__file__).resolve().parents[2] / "tools" / "check_secrets.py"
    assert scan_text("tools/check_secrets.py", source.read_text(encoding="utf-8"), DEFAULT) == []


def test_environment_placeholders_and_generic_users_homes_are_not_findings() -> None:
    text = (
        "C:\\Users\\%USERNAME%\\x and C:\\Users\\$env:USERNAME\\x and /home/$USER/x and /home/${USER}/x "
        "and /home/node/app and /home/runner/work and /Users/runner/x\n"
    )
    assert scan_text("guide.md", text, DEFAULT) == []
    assert [finding.kind for finding in scan_text("x.md", "/ho" + "me/alice/x\n", DEFAULT)] == ["a Linux home folder"]
