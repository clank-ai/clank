"""Design 0001 §5: the console's lists change without flicker (`clank/console/lists.py`): the same lines again change
nothing, a changed line is updated in its item, colors count as a change, the items are made again only when their
number changes, and the highlight follows its row's key."""

import pytest
from textual.app import App, ComposeResult
from textual.content import Content
from textual.widgets import Label, ListView

from clank.console.lists import LineItem, refill, relabel

pytestmark = pytest.mark.anyio


class Lists(App[None]):
    def compose(self) -> ComposeResult:
        yield ListView(id="listed")
        yield Label("head", id="head")


def texts(listed: ListView) -> list[str]:
    return [str(item.query_one(Label).content) for item in listed.query(LineItem)]


async def test_a_list_changes_only_what_changed_and_keeps_its_highlight() -> None:
    app = Lists()
    async with app.run_test() as pilot:
        listed = app.query_one("#listed", ListView)
        refill(listed, ["alpha", "beta", "gamma"], ["a", "b", "c"])
        await pilot.pause()
        listed.index = 1
        items = list(listed.query(LineItem))
        refill(listed, ["alpha", "beta", "gamma"], ["a", "b", "c"], keep="b")
        await pilot.pause()
        assert list(listed.query(LineItem)) == items, "the same lines made nothing again"
        refill(listed, ["new", "alpha", "beta"], ["n", "a", "b"], keep="b")
        await pilot.pause()
        assert list(listed.query(LineItem)) == items, "a changed line is updated in its item"
        assert texts(listed) == ["new", "alpha", "beta"]
        assert listed.index == 2, "the highlight followed its row"
        refill(listed, [Content.assemble(("new", "bold red")), "alpha", "beta"], ["n", "a", "b"])
        await pilot.pause()
        assert isinstance(items[0].line, Content), "a change of colors is a change"
        refill(listed, ["one"], ["o"])
        await pilot.pause()
        assert texts(listed) == ["one"]
        assert listed.index == 0


async def test_a_label_is_updated_only_when_its_text_or_colors_change(monkeypatch: pytest.MonkeyPatch) -> None:
    app = Lists()
    async with app.run_test():
        head = app.query_one("#head", Label)
        updates: list[object] = []
        original = Label.update

        def counted(self: Label, text: object = "") -> None:
            updates.append(text)
            original(self, text)  # type: ignore[arg-type]

        monkeypatch.setattr(Label, "update", counted)
        relabel(head, "head")
        relabel(head, "other")
        relabel(head, Content.assemble(("other", "bold")))
        assert updates == ["other", Content.assemble(("other", "bold"))]
