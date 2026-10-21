"""Design 0001 §8.4, design 0002 §3.2 and design 0011 §6: the repository passes its own checks, so `pytest` alone
catches what continuous integration would: a generated document out of date, a broken link, a secret, a British
spelling, a color or a state's mark written in the console's code."""

from pathlib import Path

from tools import (
    apidoc,
    check_colors,
    check_docs,
    check_secrets,
    check_spelling,
    codemap,
    eventsdoc,
    schemas,
    testspage,
    tstypes,
)
from tools.files import repository_files

REPO = Path(__file__).resolve().parents[1]


def current(path: Path) -> str:
    target = REPO / path
    return target.read_bytes().decode("utf-8") if target.exists() else ""


def test_the_code_map_is_up_to_date() -> None:
    assert current(codemap.OUTPUT) == codemap.render(REPO), f"run `{codemap.COMMAND}`"


def test_the_tests_page_is_up_to_date() -> None:
    assert current(testspage.OUTPUT) == testspage.render(REPO), f"run `{testspage.COMMAND}`"


def test_the_events_page_is_up_to_date() -> None:
    assert current(eventsdoc.OUTPUT) == eventsdoc.render_repository(), f"run `{eventsdoc.COMMAND}`"


def test_the_api_page_is_up_to_date(tmp_path: Path) -> None:
    assert current(apidoc.OUTPUT) == apidoc.render_repository(tmp_path), f"run `{apidoc.COMMAND}`"


def test_the_extensions_typescript_types_are_up_to_date() -> None:
    assert current(tstypes.OUTPUT) == tstypes.render_repository(), f"run `{tstypes.COMMAND}`"


def test_the_settings_schemas_are_up_to_date() -> None:
    expected = schemas.render_all()
    folder = REPO / schemas.FOLDER
    found = {path.name: path.read_bytes().decode("utf-8") for path in folder.glob("*.schema.json")}
    assert found == expected, f"run `{schemas.COMMAND}`"


def test_clanks_own_default_settings_read_without_a_problem(tmp_path: Path) -> None:
    assert schemas.default_problems(tmp_path) == []


def test_every_link_index_and_section_status_is_in_order() -> None:
    assert check_docs.problems(REPO, repository_files(REPO)) == []


def test_nothing_looks_secret_or_personal() -> None:
    compiled = check_secrets.local_patterns(REPO)
    assert [str(finding) for finding in check_secrets.scan(REPO, repository_files(REPO), compiled)] == []


def test_everything_is_written_in_american_english() -> None:
    assert [str(finding) for finding in check_spelling.scan(REPO, repository_files(REPO))] == []


def test_the_console_names_only_the_styles_colors_and_marks() -> None:
    assert check_colors.problems(check_colors.console_roots(REPO), check_colors.style_names()) == []
