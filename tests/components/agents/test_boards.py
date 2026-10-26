"""Design 0022 §1, §2 and §4: a board is a `.board` file of the folder, JSON: its title, settings and items. `new`
makes one (refused when it exists); `list` finds the folder's. The agent adds a figure (sized from its file, its
aspect kept, its caption under it), LaTeX, a note, a slot, a frame (around items it names) or an arrow, each placed by
where; a figure in a slot takes the slot; a frame grows to hold what is placed in it. `update` changes an item's words
or place, `remove` takes it away. Every change of the agent's keeps the board before it in the board's history and
records `agents.board_changed`. The board is said in words for the model: each item with its id, kind, place and what
it shows, what each frame holds, the open slots, and the owner's annotations by what they are over ("a pen loop around
the upper middle of fig-1"). A figure that is not a file of the folder, a kind the agent may not add, or an item that
is not on the board, is refused, saying why. The routes answer the same."""

import json
import struct
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.agents.boards import BoardError, Boards, image_size
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

YOU = Actor(kind="user", via="console")
HEADERS = {"Authorization": "Bearer t"}


def png(path: Path, width: int, height: int) -> None:
    """A real PNG of one gray row repeated, `width` by `height`."""
    raw = b"".join(b"\x00" + b"\x80" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    head = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def folder(kernel: Kernel, tmp_path: Path) -> Path:
    folder = tmp_path / "resonance"
    (folder / "figures").mkdir(parents=True)
    png(folder / "figures" / "amp.png", 800, 600)
    png(folder / "figures" / "phase.png", 600, 600)
    (folder / "figures" / "wide.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100"></svg>',
                                                 encoding="utf-8")  # fmt: skip
    kernel.settings.write("workspace", "resonance", {"path": str(folder)}, base=None, actor=YOU)
    return folder


def boards_of(kernel: Kernel) -> Boards:
    found: Boards = kernel.parts["agents"].boards
    return found


def on_disk(folder: Path, board: str = "figures/fig3.board") -> dict[str, Any]:
    found: dict[str, Any] = json.loads((folder / board).read_text(encoding="utf-8"))
    return found


def test_images_are_measured_from_their_files(folder: Path) -> None:
    assert image_size(folder / "figures" / "amp.png") == (800, 600)
    assert image_size(folder / "figures" / "wide.svg") == (400, 100)
    (folder / "notes.txt").write_text("not an image", encoding="utf-8")
    assert image_size(folder / "notes.txt") is None


def test_a_new_board_is_a_file_of_the_folder_and_is_listed(kernel: Kernel, folder: Path) -> None:
    made = boards_of(kernel).new("resonance", "fig3", folder="figures", title="Fig 3")
    assert made["board"] == "figures/fig3.board"
    assert on_disk(folder) == {"board": 1, "title": "Fig 3", "settings": {"grid": 20, "preamble": ""}, "items": []}
    assert [each["board"] for each in boards_of(kernel).boards("resonance")] == ["figures/fig3.board"]
    with pytest.raises(BoardError, match="already"):
        boards_of(kernel).new("resonance", "fig3", folder="figures")


def test_the_agent_adds_figures_latex_notes_slots_and_frames_each_placed_by_where(kernel: Kernel, folder: Path) -> None:
    boards = boards_of(kernel)
    boards.new("resonance", "fig3", folder="figures")
    first = boards.add(
        "resonance", "fig3", "figure", {"file": "/workspace/figures/amp.png", "caption": "(a) Amplitude"}
    )
    assert first["id"] == "fig-1"
    fig = on_disk(folder)["items"][0]
    assert (fig["x"], fig["y"], fig["w"], fig["h"]) == (80, 80, 360, 298), (
        "360 wide at its aspect, its caption under it"
    )
    assert fig["file"] == "figures/amp.png"
    assert fig["by"] == "agent"
    boards.add("resonance", "fig3", "latex", {"source": r"A(f) = \frac{F_0}{\sqrt{x}}"}, at={"below": "fig-1"})
    boards.add("resonance", "fig3", "slot", {"label": "phase vs frequency"}, at={"right_of": "fig-1"})
    boards.add("resonance", "fig3", "note", {"text": "**Why Q is about 25**"}, at={"below": "latex-2"})
    framed = boards.add("resonance", "fig3", "frame", {"name": "Figure 3", "around": ["fig-1", "latex-2", "slot-3"]})
    items = {each["id"]: each for each in on_disk(folder)["items"]}
    assert items["latex-2"]["mode"] == "math"
    assert (items["latex-2"]["x"], items["latex-2"]["y"]) == (80, 420)
    assert (items["slot-3"]["x"], items["slot-3"]["y"]) == (480, 80)
    frame = items[framed["id"]]
    assert (frame["x"], frame["y"]) == (60, 40), "around the items, its name above them"
    assert on_disk(folder)["items"][0]["kind"] == "frame", "a frame is drawn under what it holds"
    filled = boards.add("resonance", "fig3", "figure", {"file": "figures/phase.png"}, at={"slot": "slot-3"})
    items = {each["id"]: each for each in on_disk(folder)["items"]}
    assert "slot-3" not in items, "the slot is taken"
    placed = items[filled["id"]]
    assert (placed["x"], placed["w"], placed["h"]) == (530, 220, 220), "square, centered in the 320 by 220 slot"
    assert "slot-3" in filled["said"]


def test_update_moves_and_rewords_and_remove_takes_away_each_kept_in_history(kernel: Kernel, folder: Path) -> None:
    boards = boards_of(kernel)
    boards.new("resonance", "fig3", folder="figures")
    boards.add("resonance", "fig3", "figure", {"file": "figures/amp.png"})
    boards.add("resonance", "fig3", "figure", {"file": "figures/wide.svg"}, at={"below": "fig-1"})
    boards.update("resonance", "fig3", "fig-2", {"caption": "(b) Wide"}, at={"right_of": "fig-1"})
    moved = {each["id"]: each for each in on_disk(folder)["items"]}["fig-2"]
    assert (moved["x"], moved["y"], moved["caption"]) == (480, 80, "(b) Wide")
    assert moved["h"] == 118, "its caption made room for: 90 high at 360 wide, and 28 for the caption"
    boards.remove("resonance", "fig3", "fig-1")
    assert [each["id"] for each in on_disk(folder)["items"]] == ["fig-2"]
    history = sorted((folder / ".clank" / "boards" / "figures-fig3" / "history").iterdir())
    assert len(history) == 4, "the board before each of the agent's four changes"
    assert json.loads(history[-1].read_text(encoding="utf-8"))["items"][0]["id"] == "fig-1"
    changes = kernel.events.latest(10, types=["agents.board_changed"])
    assert [each.data["change"] for each in reversed(changes)] == ["new", "add", "add", "update", "remove"]


def test_the_board_is_said_in_words_with_the_owners_annotations_by_what_they_are_over(
    kernel: Kernel, folder: Path
) -> None:
    boards = boards_of(kernel)
    boards.new("resonance", "fig3", folder="figures")
    boards.add("resonance", "fig3", "figure", {"file": "figures/amp.png", "caption": "(a) Amplitude"})
    boards.add("resonance", "fig3", "note", {"text": "Why Q is about 25"}, at={"right_of": "fig-1"})
    boards.add("resonance", "fig3", "frame", {"name": "Figure 3", "around": ["fig-1"]})
    boards.add("resonance", "fig3", "slot", {"label": "phase"}, at={"below": "frame-3"})
    board = on_disk(folder)
    board["items"] += [
        {"id": "pen-5", "kind": "pen", "points": [[230, 100], [290, 110], [260, 150], [228, 104]]},
        {"id": "arrow-6", "kind": "arrow", "from": {"item": "note-2"}, "to": {"item": "fig-1"}},
        {"id": "pin-7", "kind": "pin", "x": 400, "y": 300, "text": "Mark Q here", "open": True},
    ]
    (folder / "figures" / "fig3.board").write_text(json.dumps(board), encoding="utf-8")
    said = boards.describe("resonance", "fig3")
    assert 'fig-1: figure figures/amp.png, "(a) Amplitude", at (80, 80), 360 by 298' in said
    assert 'frame-3: frame "Figure 3", holds fig-1' in said
    assert 'slot-4: slot "phase", open, waits to be filled' in said
    assert "pen-5: a pen loop around the upper middle of fig-1" in said
    assert "arrow-6: an arrow from note-2 to fig-1" in said
    assert 'pin-7: a pin on the lower right of fig-1, open: "Mark Q here"' in said


def test_what_cannot_be_on_a_board_is_refused_saying_why(kernel: Kernel, folder: Path) -> None:
    boards = boards_of(kernel)
    boards.new("resonance", "fig3", folder="figures")
    with pytest.raises(BoardError, match="not a file of the folder"):
        boards.add("resonance", "fig3", "figure", {"file": "../elsewhere.png"})
    with pytest.raises(BoardError, match="the agent adds"):
        boards.add("resonance", "fig3", "pen", {"points": [[0, 0]]})
    with pytest.raises(BoardError, match="no item fig-9"):
        boards.update("resonance", "fig3", "fig-9", {"caption": "x"})
    with pytest.raises(BoardError, match="no board"):
        boards.describe("resonance", "missing")


def test_the_routes_make_read_and_change_a_board(kernel: Kernel, folder: Path) -> None:
    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as client:
        wanted = {"workspace": "resonance", "name": "fig3", "folder": "figures"}
        made = client.post("/api/v1/agents/boards", json=wanted, headers=HEADERS).json()
        added = client.post("/api/v1/agents/boards/add", headers=HEADERS, json={
            "workspace": "resonance", "board": "fig3", "kind": "figure", "fields": {"file": "figures/amp.png"},
        }).json()  # fmt: skip
        read = client.get("/api/v1/agents/boards/read", params={"workspace": "resonance", "board": "fig3"},
                          headers=HEADERS).json()  # fmt: skip
        listed = client.get("/api/v1/agents/boards", params={"workspace": "resonance"}, headers=HEADERS).json()
        refused = client.post("/api/v1/agents/boards/remove", headers=HEADERS,
                              json={"workspace": "resonance", "board": "fig3", "id": "fig-9"})  # fmt: skip
    assert made["board"] == "figures/fig3.board"
    assert added["id"] == "fig-1"
    assert "fig-1: figure figures/amp.png" in read["said"]
    assert read["items"][0]["id"] == "fig-1"
    assert listed["boards"][0]["items"] == 1
    assert refused.status_code == 409


def test_clank_board_makes_lists_and_shows_a_folders_boards(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from clank.cli import common
    from clank.cli.main import main
    from clank.client import Client

    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7727", "t", name="cli", http=http))
        made = CliRunner().invoke(main, ["board", "new", "fig3", str(folder), "--in", "figures", "--title", "Figure 3"])
        boards_of(kernel).add("resonance", "fig3", "figure", {"file": "figures/amp.png"})
        listed = CliRunner().invoke(main, ["board", "list", str(folder)])
        shown = CliRunner().invoke(main, ["board", "show", "fig3", str(folder)])
    assert made.exit_code == 0, made.output
    assert "Made figures/fig3.board" in made.output
    assert "figures/fig3.board  Figure 3  (1 item)" in listed.output
    assert "fig-1: figure figures/amp.png" in shown.output
