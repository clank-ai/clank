"""Design 0001 §8.4: the documentation check finds links to files or headings that do not exist, documents missing
from their index, and design sections without a status, reading the documents the way GitHub shows them."""

from collections.abc import Callable
from pathlib import Path

from tools.check_docs import anchors, problems, slug

Write = Callable[[dict[str, str]], Path]
SAMPLE = (
    "# Design 0001: a sample\n\n## Sections\n\n| § | Section | Status |\n| --- | --- | --- |\n"
    "| 1 | First | Approved |\n\n## 1. First\n"
)


def every_file(root: Path) -> list[Path]:
    return sorted((path.relative_to(root) for path in root.rglob("*") if path.is_file()), key=Path.as_posix)


def test_a_link_to_a_missing_file_is_reported(write_files: Write) -> None:
    root = write_files({"README.md": "See [the guide](docs/guide.md).\n"})
    assert problems(root, every_file(root)) == ["README.md: links to docs/guide.md, which does not exist"]


def test_a_link_to_a_missing_heading_is_reported_and_a_real_one_is_not(write_files: Write) -> None:
    root = write_files(
        {
            "README.md": "[ok](docs/guide.md#2-the-kernel) and [stale](docs/guide.md#9-gone)\n",
            "docs/guide.md": "# Guide\n\n## 2. The kernel\n",
        }
    )
    assert problems(root, every_file(root)) == [
        "README.md: links to docs/guide.md#9-gone, but that heading does not exist"
    ]


def test_anchors_follow_github_for_punctuation_section_signs_code_and_repeats() -> None:
    assert slug("3. The skeleton (M0) and the order of milestones") == "3-the-skeleton-m0-and-the-order-of-milestones"
    assert slug("2.6 Policy: deny wins") == "26-policy-deny-wins"
    assert slug("Design 0001 §8.5") == "design-0001-85"
    assert slug("`tests/test_version.py`") == "teststest_versionpy"
    assert anchors("# A\n\n## A\n\n### A\n") == {"a", "a-1", "a-2"}


def test_links_inside_code_are_not_checked(write_files: Write) -> None:
    root = write_files({"README.md": "````\n```\n[x](missing.md)\n```\n````\nAnd `[y](missing.md)` inline.\n"})
    assert problems(root, every_file(root)) == []


def test_outside_links_are_not_checked(write_files: Write) -> None:
    root = write_files({"README.md": "[site](https://example.com/missing) [mail](mailto:someone@example.com)\n"})
    assert problems(root, every_file(root)) == []


def test_a_link_out_of_the_repository_is_reported(write_files: Write) -> None:
    outer = write_files({"outside.md": "# Outside\n", "repo/README.md": "[x](../outside.md)\n"})
    root = outer / "repo"
    assert problems(root, every_file(root)) == ["README.md: links to ../outside.md, which is outside the repository"]


def test_documents_missing_from_their_index_and_gaps_in_numbers_are_reported(write_files: Write) -> None:
    root = write_files(
        {
            "docs/decisions/README.md": "[0001](0001-first.md)\n",
            "docs/decisions/0001-first.md": "# 0001\n",
            "docs/decisions/0003-third.md": "# 0003\n",
            "docs/plans/README.md": "# Plans\n",
            "docs/plans/m0.1-first-step.md": "# A plan\n",
        }
    )
    assert problems(root, every_file(root)) == [
        "docs/decisions/README.md: does not list 0003-third.md",
        "docs/decisions: numbers must run from 0001 without gaps or repeats; missing 0002",
        "docs/plans/README.md: does not list m0.1-first-step.md",
    ]


def test_design_sections_missing_from_the_table_or_without_a_status_are_reported(write_files: Write) -> None:
    design = (
        "# Design 0001: a sample\n\n## Sections\n\n| § | Section | Status |\n| --- | --- | --- |\n"
        "| 1 | First | Approved |\n| 2 | Second |  |\n| 4 | Fourth | Proposed |\n\n"
        "## 1. First\n\n## 2. Second\n\n## 3. Third\n"
    )
    root = write_files({"docs/design/README.md": "[0001](0001-sample.md)\n", "docs/design/0001-sample.md": design})
    assert problems(root, every_file(root)) == [
        "docs/design/0001-sample.md: section 2 has no status in its Sections table",
        "docs/design/0001-sample.md: section 3 is missing from its Sections table",
        "docs/design/0001-sample.md: its Sections table lists section 4, which has no heading",
    ]


def test_tidy_documents_have_no_problems(write_files: Write) -> None:
    root = write_files(
        {
            "README.md": "Read [the design](docs/design/0001-sample.md#1-first).\n",
            "docs/design/README.md": "[0001](0001-sample.md)\n",
            "docs/design/0001-sample.md": SAMPLE,
        }
    )
    assert problems(root, every_file(root)) == []


def test_setext_headings_have_anchors_as_github_gives_them() -> None:
    assert anchors("The kernel\n==========\n\nIts parts\n---\n\nSome text\n") == {"the-kernel", "its-parts"}


def test_a_link_from_the_repositorys_root_resolves_there(write_files: Write) -> None:
    root = write_files(
        {"docs/a/notes.md": "[ok](/docs/guide.md#guide) and [gone](/docs/missing.md)\n", "docs/guide.md": "# Guide\n"}
    )
    assert problems(root, every_file(root)) == ["docs/a/notes.md: links to /docs/missing.md, which does not exist"]


def test_an_index_linking_with_a_leading_dot_lists_the_document(write_files: Write) -> None:
    root = write_files(
        {
            "docs/plans/README.md": "- [One](./m1-one.md)\n- [Two](../plans/m1-two.md)\n",
            "docs/plans/m1-one.md": "# One\n",
            "docs/plans/m1-two.md": "# Two\n",
        }
    )
    assert problems(root, every_file(root)) == []
