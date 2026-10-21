"""Design 0001 §7.2 and design 0002 §2.16: everything of one user lives under CLANK_HOME (`~/.clank` unless the
environment names another folder), in the folders the kernel creates."""

from pathlib import Path

from clank.kernel.home import Home


def test_clank_home_from_the_environment_wins(tmp_path: Path) -> None:
    assert Home.resolve({"CLANK_HOME": str(tmp_path / "elsewhere")}).root == tmp_path / "elsewhere"


def test_the_default_is_dot_clank_in_the_home_folder() -> None:
    assert Home.resolve({}).root == Path.home() / ".clank"


def test_ensure_creates_every_folder(tmp_path: Path) -> None:
    home = Home(tmp_path / "h")
    home.ensure()
    for folder in (home.config, home.secrets, home.state, home.logs, home.library, home.artifacts):
        assert folder.is_dir()
    assert home.database == home.state / "clank.db"


def test_a_homes_id_is_the_same_every_time_and_differs_between_homes(tmp_path: Path) -> None:
    first = Home(tmp_path / "a")
    assert first.id == Home(tmp_path / "a").id
    assert first.id != Home(tmp_path / "b").id
    assert len(first.id) == 12
    assert set(first.id) <= set("0123456789abcdef")
