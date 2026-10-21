"""Design 0004 §2 (the loop guard; decision 0040): an answer's part that repeats itself is found soon after its newest
stretch fills (closing tags again and again, a number written again and again), a paragraph of prose said again by the
long stretch only; a tool call's arguments are read on the short stretch only, so a file written from a template is
not taken for a loop; Clank's own code, documents and most repetitive file never are; each tool call is read apart
from the others; the share and the stretches are its settings; the words say which part repeated, over which stretch
and how far it compresses, and its brief words (the ones an agent is sent) carry no numbers, since an agent may retry
an error by the numbers in its words; and the guard trips once. Design 0012 §5.4: it keeps each part's newest reading,
the lowest share and over which stretch, for the Monitor to show against its ratio, and lists each part it was fed in
the order it was first fed, one not yet as long as its shortest stretch without a share."""

import json
import random
from pathlib import Path

from clank.components.gateway.loops import LoopGuard, share_of

ROOT = Path(__file__).resolve().parents[3]
TAGS = "</f>\n</invoke>\n</functions>\n"  # the loop of 2026-10-18, as its shape
PROSE = (ROOT / "docs/PRINCIPLES.md").read_text(encoding="utf-8")


def streamed(guard: LoopGuard, part: str, text: str, name: str = "", piece: int = 7) -> tuple[int | None, str | None]:
    """The text fed in small pieces, as an engine streams it: how many characters were fed when the guard tripped (None:
    never), and what it said."""
    for start in range(0, len(text), piece):
        said = guard.feed(part, text[start : start + piece], name)
        if said is not None:
            return min(start + piece, len(text)), said
    return None, None


def excerpt(characters: int) -> str:
    """Ordinary prose of that many characters: Clank's principles, after their title."""
    start = PROSE.index("\n\n") + 2
    return PROSE[start : start + characters]


def test_closing_tags_said_again_and_again_are_found_soon_after_the_short_stretch_fills() -> None:
    at, said = streamed(LoopGuard(), "answer", TAGS * 400)
    assert said is not None
    assert at is not None
    assert 2000 <= at <= 2300, at


def test_a_thinking_that_writes_the_same_number_again_and_again_is_found() -> None:
    at, _ = streamed(LoopGuard(), "thinking", "Let me tabulate the rates first. " + "0.0 " * 3000)
    assert at is not None
    assert at <= 2400, at


def test_a_paragraph_of_prose_said_again_and_again_is_found_by_the_long_stretch_only() -> None:
    again = excerpt(600) * 14
    assert streamed(LoopGuard(windows=(2000,)), "thinking", again) == (None, None)
    at, said = streamed(LoopGuard(), "thinking", again)
    assert said is not None
    assert at is not None
    assert 8000 <= at <= 8300, at
    assert "8,000" in said


def test_a_file_a_tool_call_writes_from_a_template_is_not_taken_for_a_loop() -> None:
    seats = "\n".join(
        json.dumps({"id": index, "kind": "seat", "row": "A", "price": 25, "free": True}) for index in range(400)
    )
    services = "".join(
        f"  worker-{index}:\n    image: app:latest\n    command: python -m worker --queue jobs\n    restart: always\n"
        for index in range(90)
    )
    for text in (seats, services):
        assert len(text) > 8000
        assert streamed(LoopGuard(), "tool 0", text, name="write") == (None, None)


def test_clanks_own_code_documents_and_its_most_repetitive_file_are_never_taken_for_a_loop() -> None:
    texts = {
        "code": (ROOT / "clank/components/gateway/server.py").read_text(encoding="utf-8"),
        "a design": (ROOT / "docs/design/0004-working-in-a-folder.md").read_text(encoding="utf-8"),
        "an engine's log": (ROOT / "tests/fixtures/kvmem-llamacpp/v0.16.0-rc1/program.json").read_text(
            encoding="utf-8"
        ),
        "counting": " ".join(f"w{index}" for index in range(4000)),
        "similar tests": "\n\n".join(
            f"def test_case_{index}():\n    result = run(n={index}, p=0.0{index % 9 + 1})\n    assert result.ok\n"
            f"    assert result.value == pytest.approx({random.Random(index).random():.6f})"
            for index in range(80)
        ),
    }
    for name, text in texts.items():
        assert len(text) > 8000, name
        for part in ("answer", "tool 0", "thinking"):
            assert streamed(LoopGuard(), part, text) == (None, None), f"{name}, as {part}"


def test_each_tool_call_is_read_apart_from_the_others() -> None:
    guard = LoopGuard()
    assert streamed(guard, "tool 0", TAGS * 64, name="bash") == (None, None), "1,792 characters: not yet a stretch"
    assert streamed(guard, "tool 1", TAGS * 64, name="bash") == (None, None), "another call starts afresh"
    at, _ = streamed(guard, "tool 0", TAGS * 20, name="bash")
    assert at is not None, "the first call, past 2,000 characters of the same tags, repeats itself"


def test_the_share_and_the_stretches_are_its_settings() -> None:
    at, said = streamed(LoopGuard(ratio=0.02), "answer", TAGS * 400)
    assert said is not None
    assert at is not None
    assert 8000 <= at <= 8300, "the tags compress to about 2.4% over 2,000 characters and 0.9% over 8,000"
    at, said = streamed(LoopGuard(windows=(4000,)), "answer", TAGS * 400)
    assert said is not None
    assert "4,000" in said
    at, said = streamed(LoopGuard(tool_windows=(4000,)), "tool 0", TAGS * 400, name="bash")
    assert at is not None
    assert 4000 <= at <= 4300, at


def test_the_words_say_which_part_repeated_over_which_stretch_and_how_far_it_compresses() -> None:
    guard = LoopGuard()
    guard.feed("tool 0", '{"command": "ls ', "bash")
    _, said = streamed(guard, "tool 0", TAGS * 100)
    assert said is not None
    assert said.startswith("its tool call bash repeated itself (its newest 2,000 characters compress to ")
    assert said.endswith("% of their size)")
    _, thought = streamed(LoopGuard(), "thinking", "0.0 " * 1000)
    assert thought is not None
    assert thought.startswith("its thinking repeated itself")
    _, answered = streamed(LoopGuard(), "answer", TAGS * 100)
    assert answered is not None
    assert answered.startswith("its answer repeated itself")


def test_its_brief_words_carry_no_numbers_so_no_agent_retries_by_them() -> None:
    guard = LoopGuard(tool_windows=(2500,))  # "2,500" holds "500", which OpenCode retries an error for
    _, said = streamed(guard, "tool 0", TAGS * 120, name="bash")
    assert said is not None
    assert "2,500 characters" in said
    assert guard.brief == "its tool call bash repeated itself"
    assert not any(character.isdigit() for character in guard.brief)


def test_the_guard_trips_once_and_then_keeps_what_it_found() -> None:
    guard = LoopGuard()
    assert guard.tripped is None
    _, said = streamed(guard, "answer", TAGS * 100)
    assert said is not None
    assert guard.tripped == said
    assert guard.feed("answer", TAGS) is None, "it said so once"
    assert guard.feed("thinking", "0.0 " * 1000) is None
    assert guard.tripped == said


def test_the_guard_keeps_each_parts_newest_share_and_its_stretch() -> None:
    guard = LoopGuard()
    prose = (ROOT / "docs/GLOSSARY.md").read_text(encoding="utf-8")[:8000]  # ordinary prose, long enough
    assert len(prose) == 8000
    guard.feed("thinking", prose[:1000])
    assert guard.newest() == [{"part": "thinking", "name": "", "share": None, "stretch": None}], "watched, no share yet"
    guard.feed("thinking", prose[1000:2000])
    guard.feed("tool 0", prose[:2000], "bash")
    share = round(share_of(prose[:2000]), 3)
    assert guard.newest() == [
        {"part": "thinking", "name": "", "share": share, "stretch": 2000},
        {"part": "tool 0", "name": "bash", "share": share, "stretch": 2000},
    ]
    guard.feed("thinking", prose[2000:])
    lowest = min((share_of(prose[-2000:]), 2000), (share_of(prose), 8000))
    assert guard.newest()[0] == {"part": "thinking", "name": "", "share": round(lowest[0], 3), "stretch": lowest[1]}
    assert 0.06 < lowest[0] < 1, "prose keeps most of its size"
    streamed(guard, "answer", TAGS * 100)
    assert guard.tripped is not None
    looped = guard.newest()[2]
    assert (looped["part"], looped["stretch"]) == ("answer", 2000)
    assert looped["share"] < 0.06, "the reading that tripped it"


def test_a_part_fed_first_but_not_yet_as_long_as_its_shortest_stretch_is_listed_first_without_a_share() -> None:
    guard = LoopGuard()
    guard.feed("thinking", "x" * 130)  # read once, at 128 characters, over no stretch
    guard.feed("tool 0", "", "bash")  # a call's name alone: nothing of it is fed yet
    guard.feed("answer", (ROOT / "docs/GLOSSARY.md").read_text(encoding="utf-8")[:2100])
    shown = guard.newest()
    assert [(part["part"], part["share"], part["stretch"]) for part in shown[:1]] == [("thinking", None, None)]
    assert [(part["part"], part["stretch"]) for part in shown[1:]] == [("answer", 2000)]
    assert 0.06 < shown[1]["share"] < 1
