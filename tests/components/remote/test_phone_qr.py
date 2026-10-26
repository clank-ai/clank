"""Design 0025 §2 (decision 0144): the QR the console shows for the pair link, drawn as text, two modules a character
(`▀` the upper one dark, `▄` the lower, `█` both, a space neither), with a quiet zone of one character around it, from
the modules segno makes; a link of the usual length fits a small code."""

import segno

from clank.components.remote.qr import qr_lines

LINK = "https://desk.tail0.ts.net:8445/pair?code=ABCD2345"


def test_the_qr_is_drawn_as_text_two_modules_a_character_from_segnos_modules() -> None:
    lines = qr_lines(LINK)
    code = segno.make(LINK, error="m")
    modules = [list(row) for row in code.matrix]
    size = len(modules)
    assert len(lines) == (size + 2 + 1) // 2 + 1, "two modules a line, a quiet zone above and below"
    assert all(len(line) == size + 2 for line in lines), "a quiet zone left and right"
    assert set("".join(lines)) <= {"▀", "▄", "█", " "}
    assert lines[0] == " " * (size + 2), "the quiet zone above"
    assert lines[-1].strip() == "", "the quiet zone below"
    # the first two module rows: the upper of each pair is row 0, the lower row 1
    top = lines[1]
    for column in range(size):
        upper, lower = bool(modules[0][column]), bool(modules[1][column])
        want = {(True, True): "█", (True, False): "▀", (False, True): "▄", (False, False): " "}[(upper, lower)]
        assert top[column + 1] == want, column
    assert size <= 33, "a pair link fits version 4 or smaller"
