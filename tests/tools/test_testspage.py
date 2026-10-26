"""Design 0001 §8.5: the tests page lists each design section with the test files that name it, says which sections
have no tests yet, and refuses a test file that names no section, or a section that no design has."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from tools.testspage import PageError, render

Write = Callable[[dict[str, str]], Path]

DESIGN = """\
# Design 0009: a sample design

## Sections

## 1. The first part

### 1.1 A detail

### 1.2 Another detail

## 2. The second part

```
## 3. Not a section: this is inside a code block
```
"""
DETAIL_TEST = '"""Design 0009 §1.1: details hold."""\n\n\ndef test_it_holds() -> None: ...\n'
TEST_IT = "def test_it() -> None: ...\n"  # the one test of a file whose docstring a test writes


def test_a_section_lists_the_test_files_that_name_it(write_files: Write) -> None:
    root = write_files({"docs/design/0009-sample.md": DESIGN, "tests/test_detail.py": DETAIL_TEST})
    page = render(root)
    assert "| 1.1 | A detail | `tests/test_detail.py` (1) |" in page
    assert "### `tests/test_detail.py`" in page
    assert "Design 0009 §1.1: details hold." in page
    assert "- it holds" in page


def test_sections_without_tests_say_so_and_only_leaves_are_counted(write_files: Write) -> None:
    root = write_files({"docs/design/0009-sample.md": DESIGN, "tests/test_detail.py": DETAIL_TEST})
    page = render(root)
    assert "| 1.2 | Another detail | none yet |" in page
    assert "| 1 | The first part | see its subsections |" in page
    assert "**1 of 3 design sections have tests.**" in page


def test_a_test_file_is_listed_under_each_section_of_a_list_and_under_a_section_named_across_a_line_break(
    write_files: Write,
) -> None:
    root = write_files(
        {
            "docs/design/0009-sample.md": DESIGN,
            "tests/test_listed.py": '"""Each part holds: design 0009 §1.1, §1.2 and §2."""\n\n\n' + TEST_IT,
            "tests/test_wrapped.py": '"""As design 0009\n§1.2 says."""\n\n\n' + TEST_IT,
        }
    )
    page = render(root)
    assert "| 1.1 | A detail | `tests/test_listed.py` (1) |" in page
    assert "| 1.2 | Another detail | `tests/test_listed.py` (1), `tests/test_wrapped.py` (1) |" in page
    assert "| 2 | The second part | `tests/test_listed.py` (1) |" in page


def test_a_section_of_a_list_that_does_not_exist_is_refused(write_files: Write) -> None:
    root = write_files(
        {
            "docs/design/0009-sample.md": DESIGN,
            "tests/test_stale.py": '"""Design 0009 §1.1, §2 and §7: one was removed."""\n\n\n' + TEST_IT,
        }
    )
    with pytest.raises(PageError, match=r"design 0009 §7, which"):
        render(root)


def test_headings_inside_code_blocks_are_not_sections(write_files: Write) -> None:
    root = write_files({"docs/design/0009-sample.md": DESIGN})
    assert "Not a section" not in render(root)


def test_a_test_file_that_names_no_section_is_refused(write_files: Write) -> None:
    root = write_files(
        {
            "docs/design/0009-sample.md": DESIGN,
            "tests/test_vague.py": '"""Some tests."""\n\n\ndef test_something() -> None: ...\n',
        }
    )
    with pytest.raises(PageError, match=r"tests/test_vague\.py"):
        render(root)


def test_a_section_that_does_not_exist_is_refused(write_files: Write) -> None:
    root = write_files(
        {
            "docs/design/0009-sample.md": DESIGN,
            "tests/test_stale.py": (
                '"""Design 0009 §7.4: a section that was removed."""\n\n\ndef test_old() -> None: ...\n'
            ),
        }
    )
    with pytest.raises(PageError, match=r"design 0009 §7\.4"):
        render(root)


def test_tests_in_classes_and_asynchronous_tests_are_listed(write_files: Write) -> None:
    root = write_files(
        {
            "docs/design/0009-sample.md": DESIGN,
            "tests/test_kinds.py": (
                '"""Design 0009 §2: kinds of tests."""\n\n\n'
                "class TestGroup:\n    def test_inside_a_class(self) -> None: ...\n\n\n"
                "async def test_that_awaits() -> None: ...\n"
            ),
        }
    )
    page = render(root)
    assert "- inside a class" in page
    assert "- that awaits" in page


def test_the_extensions_typescript_test_files_are_placed_by_their_leading_comment(write_files: Write) -> None:
    script = (
        "// Design 0009 §1.1: the extension holds its details.\n"
        "// More that the summary leaves out.\n"
        "\n"
        'import { test } from "node:test";\n'
        'test("a detail holds", () => {});\n'
        '  test("another detail holds", async () => {});\n'
    )
    root = write_files({"docs/design/0009-sample.md": DESIGN, "vscode/test/detail.test.ts": script})
    text = render(root)
    assert "`vscode/test/detail.test.ts` (2)" in text
    assert "Design 0009 §1.1: the extension holds its details. More that the summary leaves out." in text
    assert "- a detail holds" in text
    assert "- another detail holds" in text


def test_a_typescript_test_file_that_names_no_section_is_refused(write_files: Write) -> None:
    root = write_files({"docs/design/0009-sample.md": DESIGN, "vscode/test/vague.test.ts": "// Some tests.\n"})
    with pytest.raises(PageError, match="vague"):
        render(root)


def test_a_test_file_git_ignores_is_not_on_the_page(write_files: Write) -> None:
    root = write_files(
        {
            ".gitignore": "tests/test_scratch.py\n",
            "docs/design/0009-sample.md": DESIGN,
            "tests/test_details.py": DETAIL_TEST,
            "tests/test_scratch.py": DETAIL_TEST,
        }
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    text = render(root)
    assert "tests/test_details.py" in text
    assert "test_scratch" not in text


def test_the_phone_apps_node_test_files_are_placed_by_their_leading_comment(write_files: Write) -> None:
    script = (
        "// Design 0009 §1.1: the phone app's logic holds.\n"
        "\n"
        'import { test } from "node:test";\n'
        'test("the stream is live while connected", () => {});\n'
    )
    root = write_files({"docs/design/0009-sample.md": DESIGN, "tests/phone/model.test.mjs": script})
    text = render(root)
    assert "`tests/phone/model.test.mjs` (1)" in text
    assert "Design 0009 §1.1: the phone app's logic holds." in text
    assert "- the stream is live while connected" in text
