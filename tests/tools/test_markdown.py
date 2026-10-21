"""Design 0001 §8.4 and design 0001 §8.5: documents are read as GitHub reads them, so a heading or a link inside a code
block is code, not part of the document."""

from tools.markdown import prose_lines


def test_lines_inside_a_fence_are_code_and_line_numbers_are_kept() -> None:
    assert prose_lines("one\n```python\ncode\n```\nfive\n") == [(1, "one"), (5, "five")]


def test_a_longer_fence_holds_a_shorter_one() -> None:
    assert prose_lines("````\n```\nstill code\n```\n````\nprose\n") == [(6, "prose")]


def test_tildes_close_only_a_tilde_fence() -> None:
    assert prose_lines("~~~\n```\ncode\n~~~\nprose\n") == [(5, "prose")]


def test_a_fence_line_with_text_after_it_does_not_close_a_fence() -> None:
    assert prose_lines("```\n``` not a close\ncode\n```\nprose\n") == [(5, "prose")]


def test_a_fence_indented_inside_a_list_item_is_code() -> None:
    text = "- a step:\n\n    ```bash\n    [x](missing.md)\n    ```\n- next\n"
    assert [number for number, _ in prose_lines(text)] == [1, 2, 6]
