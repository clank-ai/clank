"""The QR code the console shows for the phone's pair link (design 0025 §2, decision 0144), drawn as text.

`qr_lines` makes the code's modules with segno (error correction M) and draws two module rows a line: `▀` where the
upper module is dark and the lower light, `▄` the other way, `█` both dark, a space neither; a quiet zone of one
character around it (the standard asks for four modules; a terminal's cells are tall, and phones read one fine). The
console shows the lines in its monospace cells; `clank remote pair` prints them too.
"""

import segno

UPPER, LOWER, BOTH, NEITHER = "▀", "▄", "█", " "


def qr_lines(text: str) -> list[str]:
    """The QR code of `text` as lines of text, two modules a character, a quiet zone of one character around."""
    code = segno.make(text, error="m")
    rows = [[bool(module) for module in row] for row in code.matrix]
    size = len(rows)
    blank = [False] * size
    lines = [NEITHER * (size + 2)]
    for upper_at in range(0, size, 2):
        upper = rows[upper_at]
        lower = rows[upper_at + 1] if upper_at + 1 < size else blank
        line = "".join(
            BOTH if up and low else UPPER if up else LOWER if low else NEITHER
            for up, low in zip(upper, lower, strict=True)
        )
        lines.append(NEITHER + line + NEITHER)
    lines.append(NEITHER * (size + 2))
    return lines
