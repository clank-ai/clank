"""The phone app's Home Screen icon as a PNG (design 0025 §3), drawn here with the standard library: iOS takes a PNG
for a Home Screen app's icon (not an SVG), and Clank keeps no binary in its package. The mark is the console's: a
diamond in orange over a blue cursor, on the console's ground; `icon_png` draws it at any size, once per size."""

import functools
import struct
import zlib

GROUND = (0x16, 0x16, 0x1E)
DIAMOND = (0xFF, 0x9E, 0x64)
CURSOR = (0x7A, 0xA2, 0xF7)


@functools.lru_cache(maxsize=4)
def icon_png(size: int = 180) -> bytes:
    """The icon, `size` pixels square, as a PNG (RGB, no alpha: iOS fills a transparent corner black anyway)."""
    rows = []
    center = size / 2
    half = size * 0.255  # the diamond's half width; its top sits a sixth down
    top, bottom = size * 0.17, size * 0.68
    cursor_top, cursor_bottom = size * 0.71, size * 0.79
    cursor_left, cursor_right = size * 0.27, size * 0.73
    for y in range(size):
        row = bytearray([0])  # the filter byte: none
        for x in range(size):
            color = GROUND
            if cursor_top <= y < cursor_bottom and cursor_left <= x < cursor_right:
                color = CURSOR
            elif top <= y < bottom:
                reach = half * (1 - abs((y - (top + bottom) / 2) / ((bottom - top) / 2)))
                if abs(x + 0.5 - center) <= reach:
                    color = DIAMOND
            row += bytes(color)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8 bits a channel, color type 2 (RGB)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
