"""Design 0011 §4 and §5 (decision 0045: text never spills out of a panel), decision 0027 (the console's frames compared
as text): the stand-ins a frame's changing parts are replaced by (a version, a port, an id) keep each line's width, so
a panel's right border stands in the snapshot where the console drew it. A version of more digits than the stand-in
("v0.16.0-rc1") had shortened its line by a cell, and the border of every line that named it stood one cell left."""

from tests.console.frames import normalized


def test_a_frames_stand_ins_keep_each_lines_width() -> None:
    frame = "\n".join([
        "│ figures from KVMem/llama.cpp v0.16.0-rc1, “daily 262K” · Qwen3.8-27B │",
        "│ Clank v0.1.1 · service at 127.0.0.1:51234 · q-1a2b3c · op-0a1b2c3d     │",
        "│ a line without any                                                   │",
    ])  # fmt: skip
    shown = normalized(frame).splitlines()
    assert [len(line) for line in shown] == [len(line) for line in frame.splitlines()]
    assert "v0.00.0-rc1" in shown[0], "the version's digits stood in for, each by a 0"
    assert "v0.0.0" in shown[1]
    assert "127.0.0.1:47720" in shown[1]
