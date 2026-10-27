"""Design 0002 §3.2 (M0.1): the spelling check finds British forms in code and documents and names the American one;
a line marked `spelling: keep`, a Markdown code block, and a file that is not text are left alone."""

from pathlib import Path

from tools.check_spelling import scan, scan_text

# British forms are assembled when the tests run, so that this file itself contains none.
BRITISH_COLOR = "colo" + "ur"
BRITISH_CANCELED = "cancel" + "led"


def test_a_british_form_is_found_with_its_american_form() -> None:
    [finding] = scan_text("notes.md", f"The {BRITISH_COLOR} of the header.\n")
    assert str(finding) == f"notes.md:1: {BRITISH_COLOR} -> color"


def test_capitals_and_identifiers_do_not_hide_a_british_form() -> None:
    found = scan_text(
        "code.py", f"{BRITISH_COLOR.upper()} = 1\n{BRITISH_COLOR}_map = {{}}\nwas_{BRITISH_CANCELED} = True\n"
    )
    assert [finding.line for finding in found] == [1, 2, 3]


def test_american_forms_and_longer_words_are_not_findings() -> None:
    assert scan_text("notes.md", "The color was canceled; the analyses of each parameter.\n") == []


def test_a_line_marked_keep_is_left_alone() -> None:
    assert scan_text("notes.md", f'The paper says "{BRITISH_COLOR}" (spelling: keep, a quotation).\n') == []


def test_markdown_code_blocks_are_skipped_but_code_files_are_not() -> None:
    text = f"Text.\n```\n{BRITISH_COLOR} = 1\n```\n"
    assert scan_text("notes.md", text) == []
    assert len(scan_text("notes.py", text)) == 1


def test_files_that_are_not_text_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "image.png").write_bytes(b"\x89PNG\x00" + BRITISH_COLOR.encode())
    assert scan(tmp_path, [Path("image.png")]) == []


def test_a_patch_for_another_project_is_left_alone_as_it_copies_that_projects_code(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    patch = f'-    throw "prefill failed or {BRITISH_CANCELED}";\n'
    (tmp_path / "docs" / "fix.patch").write_text(patch, encoding="utf-8")
    (tmp_path / "docs" / "fix.md").write_text(f"The prefill was {BRITISH_CANCELED}.\n", encoding="utf-8")
    found = scan(tmp_path, [Path("docs/fix.patch"), Path("docs/fix.md")])
    assert [finding.path for finding in found] == ["docs/fix.md"]
