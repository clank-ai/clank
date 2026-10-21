"""Design 0016 §14 and decision 0105: Add a model, the console's guided first step, one panel at a time, Esc back one
screen. Its first screen asks how Clank should run its model: Cloud (`c`), or Local (`l`) with this machine's GPU and
memory. Cloud names OpenRouter and where to get a key; the agreement says what goes to OpenRouter, where, what never
goes (the MCP servers marked local, each already added marked, Space unmarking one), that each workspace asks once, and
that each request costs money; `o` changes the data policy, `n` and Esc go back writing nothing, and `y` writes the
record with the servers marked as shown (none named when none is listed), and Esc from the key then skips the
agreement done; an agreement whose words were not read cannot be agreed to. A provider already added starts at its key,
or at the model once its key is set. Every screen fits at 128, 88 and 60 columns, its keys bar at 60 keeping the keys
the step needs.

Design 0016 §11 and §14, screens 4 to 6: the key typed into the hidden field is sent once; accepted, the next screen
says its account (its label, its own limit and what is left); refused, the service's words, the field cleared; no frame
holds the key either way. The model list is OpenRouter's (a model without tool calls is never offered): `/` searches,
`s` sorts, `f` shows the free ones with their limits; Enter on a model fills its settings, and Enter there writes the
preset and a limit changed; a setting out of range is said, and nothing is written.

Design 0016 §14, screens 7 and 8, and Local: from an empty main slot the preset is loaded, and Ready shows its answer,
time and cost; with a local model running, the provider's short test comes first, then "load it now?", `n` keeping the
local model and `y` switching; each failure says what to do, `b` back to the model and `k` back to the key. Local lists
Clank's presets for the main slot with what each needs here, and Enter asks before its first step. Every word the
steps say is the service's (its guide, its models' and its account's words): the page works out none of them."""

from datetime import UTC, datetime
from typing import Any

import pytest
from textual import events
from textual.widgets import ContentSwitcher, Input, Label

from clank.client import Client
from clank.components.runtime.console.addmodel import AddModelPage
from clank.console.app import ClankConsole
from clank.console.confirm import ConfirmScreen
from clank.console.form import SecretField
from clank.console.snapshot import render_text
from clank.kernel.access import client_actor
from clank.kernel.api import ApiError
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.console.frames import FOLDER, assert_frame, frame_when, settle
from tests.fakes.openrouter import KEY
from tests.support.cloud import CloudBench

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 21, 9, 14, tzinfo=UTC)
CHOICE = "How should Clank run its model?"
AGREEMENT = "What never goes"
KEY_SCREEN = "paste your OpenRouter key"
MODELS = "that take tool calls"
HIDDEN = KEY[:-4]  # the part of the key no frame may hold


def make(client: Client, home: Home, page: str = "addmodel") -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page=page)
    app.folder = FOLDER
    return app


def page_of(app: ClankConsole) -> AddModelPage:
    return app.query_one("#page-addmodel", AddModelPage)


def servers(kernel: Kernel, *names: str) -> None:
    for name in names:
        kernel.parts["tools"].add(name, {"command": f"{name}-mcp"}, scope="user", folder="", actor=client_actor("cli"))


async def on_screen(pilot: Any, app: ClankConsole, *words: str) -> str:
    """The frame once the console has loaded (its meters read), shows these words, and nothing it started still runs
    (the header's spinner gone)."""
    await settle(pilot, lambda: bool(app.data.meters) and app.data.usable is not None)
    for _ in range(50):  # an operation may start just after the words show: its spinner then joins the frame
        await settle(pilot, lambda: all(word in render_text(app) for word in words) and not busy(render_text(app)))
        frame = await frame_when(pilot, app, *words)
        if not busy(frame):
            return frame
    raise AssertionError("the header's spinner never went away")


def busy(text: str) -> bool:
    """Whether the header's spinner shows: "working", or "work…" where the header is narrow."""
    header = text.splitlines()[0] if text else ""
    return "working" in header or "work…" in header


def said(app: ClankConsole) -> str:
    """What the page's labels say, its lines joined: words a narrow panel wraps are found whole."""
    labels = page_of(app).query(Label).results(Label)
    return " ".join(" ".join(str(label.content).split()) for label in labels if label.display)


async def test_the_first_screen_asks_cloud_or_local_with_this_machines_gpu_and_memory(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    app = make(client, home)
    async with app.run_test(size=(88, 34)) as pilot:
        frame = await on_screen(pilot, app, "NVIDIA GeForce RTX 5080")
        assert CHOICE in frame
        assert_frame(frame, "add-model-choice")


async def test_cloud_names_openrouter_and_where_to_get_a_key(client: Client, home: Home, cloud_api: CloudBench) -> None:
    app = make(client, home)
    async with app.run_test(size=(88, 34)) as pilot:
        await on_screen(pilot, app, CHOICE)
        await pilot.press("c")
        frame = await on_screen(pilot, app, "openrouter.ai")
        assert_frame(frame, "add-model-provider")


async def test_the_agreement_says_what_goes_where_and_what_never_goes_each_server_marked_local(
    client: Client, home: Home, kernel: Kernel, cloud_api: CloudBench
) -> None:
    servers(kernel, "lit", "web")
    app = make(client, home)
    async with app.run_test(size=(88, 44)) as pilot:
        await on_screen(pilot, app, CHOICE)
        await pilot.press("c", "enter")
        frame = await on_screen(pilot, app, AGREEMENT, "web")
        assert_frame(frame, "add-model-agreement")


async def test_n_and_esc_go_back_and_write_nothing(client: Client, home: Home, cloud_api: CloudBench) -> None:
    app = make(client, home)
    async with app.run_test(size=(88, 34)) as pilot:
        await on_screen(pilot, app, CHOICE)
        await pilot.press("c", "enter")
        await on_screen(pilot, app, AGREEMENT)
        await pilot.press("n")
        await on_screen(pilot, app, "openrouter.ai")
        assert AGREEMENT not in render_text(app)
        await pilot.press("enter")
        await on_screen(pilot, app, AGREEMENT)
        await pilot.press("escape")
        await on_screen(pilot, app, "openrouter.ai")
        await pilot.press("escape")
        await on_screen(pilot, app, CHOICE)
        await pilot.press("escape")
        await settle(pilot, lambda: app.query_one("#pages").current == "page-folder")  # type: ignore[attr-defined]
    assert cloud_api.endpoint is None
    assert cloud_api.calls == []


async def test_y_writes_the_record_with_the_servers_marked_as_shown_and_the_policy_chosen(
    client: Client, home: Home, kernel: Kernel, cloud_api: CloudBench
) -> None:
    servers(kernel, "lit", "web")
    app = make(client, home)
    async with app.run_test(size=(88, 44)) as pilot:
        await on_screen(pilot, app, CHOICE)
        await pilot.press("c", "enter")
        await on_screen(pilot, app, "web")
        await pilot.press("down", "space", "o")
        frame = await on_screen(pilot, app, "data_collection allow")
        assert "web  may go to the cloud" in frame
        await pilot.press("y")
        await on_screen(pilot, app, KEY_SCREEN)
        await settle(pilot, lambda: cloud_api.endpoint is not None and len(cloud_api.calls) == 2)
    agreed = {"id": "openrouter", "adapter": "openrouter", "agree": True, "local_mcp": ["lit"]}
    assert cloud_api.calls[0] == ("POST", "runtime/endpoints", agreed)
    assert cloud_api.calls[1] == ("PATCH", "runtime/endpoints/openrouter", {"options": {"data_collection": "allow"}})
    assert cloud_api.local == {"lit": True, "web": False}
    assert cloud_api.endpoint is not None
    assert cloud_api.endpoint["options"]["data_collection"] == "allow"


async def test_an_added_provider_starts_at_its_key(client: Client, home: Home, cloud_api: CloudBench) -> None:
    cloud_api.add(key=False)
    app = make(client, home)
    async with app.run_test(size=(88, 34)) as pilot:
        await on_screen(pilot, app, CHOICE)
        await pilot.press("c")
        await on_screen(pilot, app, KEY_SCREEN)
        await pilot.press("escape")
        await on_screen(pilot, app, CHOICE)
    assert cloud_api.calls == []


async def test_the_first_three_screens_fit_at_128_and_60_columns(
    client: Client, home: Home, kernel: Kernel, cloud_api: CloudBench
) -> None:
    servers(kernel, "lit")
    for width in (128, 60):
        app = make(client, home)
        async with app.run_test(size=(width, 50)) as pilot:
            assert_frame(await on_screen(pilot, app, CHOICE), f"add-model-choice-{width}")
            await pilot.press("c")
            assert_frame(await on_screen(pilot, app, "openrouter.ai"), f"add-model-provider-{width}")
            await pilot.press("enter")
            assert_frame(await on_screen(pilot, app, AGREEMENT), f"add-model-agreement-{width}")


async def to_key(pilot: Any, app: ClankConsole, cloud: CloudBench) -> None:
    """Add a model's key screen, the provider added without its key."""
    await on_screen(pilot, app, CHOICE)
    await pilot.press("c")
    await on_screen(pilot, app, KEY_SCREEN)


async def to_models(pilot: Any, app: ClankConsole) -> str:
    """The model screen, the provider added with its key."""
    await on_screen(pilot, app, CHOICE)
    await pilot.press("c")
    return await on_screen(pilot, app, MODELS, "Example Coder")


async def test_a_key_accepted_shows_its_account_and_no_frame_holds_the_key(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add(key=False)
    app = make(client, home)
    async with app.run_test(size=(88, 44)) as pilot:
        await to_key(pilot, app, cloud_api)
        app.post_message(events.Paste(KEY))
        await settle(pilot, lambda: "…-key" in render_text(app))
        assert HIDDEN not in render_text(app)
        await pilot.press("enter")
        frame = await on_screen(pilot, app, "made-up key label", "Example Coder")
        assert HIDDEN not in frame
        assert_frame(frame, "add-model-models")
    assert cloud_api.key() == KEY


async def test_a_key_refused_shows_the_services_words_and_clears_the_field(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add(key=False)
    app = make(client, home)
    async with app.run_test(size=(88, 34)) as pilot:
        await to_key(pilot, app, cloud_api)
        app.post_message(events.Paste("made-up-wrong-key"))
        await settle(pilot, lambda: "…-key" in render_text(app))
        await pilot.press("enter")
        frame = await on_screen(pilot, app, "OpenRouter refused the key")
        assert not app.query_one("#add-key-field", SecretField).filled
        assert "made-up-wrong" not in frame
        assert_frame(frame, "add-model-key-refused")
    assert cloud_api.key() is None


async def test_search_sort_and_free_change_the_list(client: Client, home: Home, cloud_api: CloudBench) -> None:
    cloud_api.add()
    app = make(client, home)
    async with app.run_test(size=(88, 44)) as pilot:
        frame = await to_models(pilot, app)
        assert frame.index("Example Coder") < frame.index("Example Small (free)")
        await pilot.press("s")
        frame = await on_screen(pilot, app, "cheapest first")
        assert frame.index("Example Small (free)") < frame.index("Example Coder")
        await pilot.press("f")
        frame = await on_screen(pilot, app, "free ones only")
        assert "Example Coder" not in frame
        assert "20 a minute, 50 a day" in frame
        await pilot.press("f", "slash", *"small", "enter")
        frame = await on_screen(pilot, app, "names with small")
        assert "Example Small" in frame
        assert "Example Coder" not in frame
    asked = [body for method, path, body in cloud_api.calls if path.endswith("/models")]
    assert (asked[-1]["search"], asked[-1]["sort"]) == ("small", "price")


async def test_enter_on_a_model_fills_its_settings_and_enter_writes_the_preset_and_the_limits(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    app = make(client, home)
    async with app.run_test(size=(88, 44)) as pilot:
        await to_models(pilot, app)
        await pilot.press("enter")
        frame = await on_screen(pilot, app, "Its settings", "262144")
        assert_frame(frame, "add-model-settings")
        app.query_one("#add-day_usd", Input).focus()
        await settle(pilot, lambda: app.focused is app.query_one("#add-day_usd", Input))
        await pilot.press("5", "enter")
        await settle(pilot, lambda: "cloud-example-coder" in cloud_api.presets and cloud_api.limits["day_usd"] == 5)
    written = [body for method, path, body in cloud_api.calls if path.endswith("/presets")]
    typed = {"model": "example-vendor/example-coder", "title": "cloud: Example Coder", "context": "262144",
             "max_output": "16384", "reasoning": "default"}  # fmt: skip
    assert written == [typed], "as typed: the service checks them"
    assert ("PUT", "gateway/cost/limits", {"day_usd": 5.0}) in cloud_api.calls


async def test_a_setting_out_of_range_is_said_and_nothing_is_written(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    app = make(client, home)
    async with app.run_test(size=(88, 44)) as pilot:
        await to_models(pilot, app)
        await pilot.press("enter")
        await on_screen(pilot, app, "Its settings")
        context = app.query_one("#add-context", Input)
        context.value = "999999999"
        context.focus()
        await settle(pilot, lambda: app.focused is context)
        await pilot.press("enter")
        await on_screen(pilot, app, "at most 262,144")
    assert cloud_api.presets == {}


async def test_the_key_the_models_and_the_settings_fit_at_128_and_60_columns(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add(key=False)
    for width in (128, 60):
        app = make(client, home)
        async with app.run_test(size=(width, 50)) as pilot:
            await to_key(pilot, app, cloud_api)
            app.post_message(events.Paste(KEY))
            await settle(pilot, lambda shown=app: "…-key" in render_text(shown))  # type: ignore[misc]
            assert_frame(await on_screen(pilot, app, "Paste your OpenRouter key", "…-key"), f"add-model-key-{width}")
            await pilot.press("enter")
            assert_frame(await on_screen(pilot, app, "made-up key label", "Example Coder"), f"add-model-models-{width}")
            await pilot.press("enter")
            assert_frame(await on_screen(pilot, app, "Its settings", "262144"), f"add-model-settings-{width}")
        cloud_api.kernel.secrets.remove("endpoint/openrouter", actor=client_actor("cli"))


async def to_test(pilot: Any, app: ClankConsole) -> None:
    """From the model screen: the first model picked, its settings taken as filled: the test starts."""
    await to_models(pilot, app)
    await pilot.press("enter")
    await on_screen(pilot, app, "Its settings", "262144")
    await pilot.press("enter")


async def test_a_load_from_an_empty_slot_ends_on_ready_with_the_answer_and_its_cost(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    app = make(client, home)
    async with app.run_test(size=(88, 40)) as pilot:
        await to_test(pilot, app)
        frame = await on_screen(pilot, app, "Ready", "enter this folder", "● cloud: Example Coder  ● gateway")
        assert "cloud: Example Coder runs in the main slot. Its test: it answered a tiny request: OK in " in said(app)
        assert_frame(frame, "add-model-ready")
        await pilot.press("enter")
        await settle(pilot, lambda: app.query_one("#pages", ContentSwitcher).current == "page-folder")
    main = client.get("runtime/slots")[0]
    assert (main["status"], main["preset"]) == ("ready", "cloud-example-coder")


async def test_with_a_local_model_running_the_test_comes_first_then_the_question_and_n_keeps_it(
    client: Client, home: Home, kernel: Kernel, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    cloud_api.run("daily-262k")
    app = make(client, home)
    async with app.run_test(size=(88, 40)) as pilot:
        await to_test(pilot, app)
        frame = await on_screen(pilot, app, "n keep it")
        assert "It answered: OK in " in said(app)
        assert "Load it now? This stops daily 262K in the main slot" in said(app)
        assert_frame(frame, "add-model-test-asking")
        await pilot.press("n")
        await on_screen(pilot, app, "Ready", "enter this folder")
        assert "daily 262K keeps the main slot" in said(app)
    assert ("POST", "runtime/endpoints/openrouter/test", {"preset": "cloud-example-coder"}) in cloud_api.calls
    assert client.get("runtime/slots")[0]["preset"] == "daily-262k", "n keeps the local model running"


async def test_y_switches_the_main_slot_to_the_cloud_model(client: Client, home: Home, cloud_api: CloudBench) -> None:
    cloud_api.add()
    cloud_api.run("daily-262k")
    app = make(client, home)
    async with app.run_test(size=(88, 40)) as pilot:
        await to_test(pilot, app)
        await on_screen(pilot, app, "n keep it")
        await pilot.press("y")
        await on_screen(pilot, app, "Ready", "enter this folder")
        assert "cloud: Example Coder runs in the main slot" in said(app)
    assert client.get("runtime/slots")[0]["preset"] == "cloud-example-coder"


async def test_each_failure_says_what_to_do_and_b_and_k_go_back_to_the_model_and_the_key(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    cloud_api.run("daily-262k")
    words = {  # OpenRouter's refusal, as the recording has it: what the service says to do
        "key refused": "refused the key",
        "no credits": "credits",
        "no model": "model",
        "no provider": "data",
        "budget": "budget",
    }
    app = make(client, home)
    async with app.run_test(size=(88, 40)) as pilot:
        for number, code in enumerate(words):
            cloud_api.openrouter.play(code)
            if number == 0:
                await to_test(pilot, app)
            else:
                await pilot.press("b")
                await on_screen(pilot, app, MODELS, "Example Coder")
                await pilot.press("enter")
                await on_screen(pilot, app, "Its settings")
                await pilot.press("enter")
            await on_screen(pilot, app, "b back to the model")
            assert "It failed:" in said(app), code
            assert words[code] in said(app).lower(), (code, said(app))
        await pilot.press("k")
        await on_screen(pilot, app, KEY_SCREEN)


async def test_a_load_that_fails_says_why(client: Client, home: Home, cloud_api: CloudBench) -> None:
    cloud_api.add()
    cloud_api.openrouter.play("key refused")  # the load's one short request
    app = make(client, home)
    async with app.run_test(size=(88, 40)) as pilot:
        await to_test(pilot, app)
        await on_screen(pilot, app, "b back to the model")
        assert "It failed: " in said(app)
        assert "refused the key" in said(app)


async def test_local_lists_the_presets_with_their_needs_and_enter_asks_before_the_first_step(
    client: Client, home: Home, kernel: Kernel, cloud_api: CloudBench
) -> None:
    kernel.parts["runtime"].recipes = {("kvmem-llamacpp", "v0.16.0-rc1"): object()}  # Clank ships none yet
    app = make(client, home)
    async with app.run_test(size=(88, 44)) as pilot:
        await on_screen(pilot, app, CHOICE)
        await pilot.press("l")
        frame = await on_screen(pilot, app, "Local: a model on this computer", "daily 262K", "install")
        assert_frame(frame, "add-model-local")
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        asked = render_text(app)
        assert "Install the engine?" in asked
        assert "by its recipe" in asked
        await pilot.press("escape")
        await on_screen(pilot, app, "Local: a model on this computer")
    assert cloud_api.calls == []


async def test_an_engine_without_a_recipe_here_says_what_to_do_instead(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    app = make(client, home)
    async with app.run_test(size=(220, 44)) as pilot:  # the message line says it whole
        await on_screen(pilot, app, CHOICE)
        await pilot.press("l")
        await on_screen(pilot, app, "Clank has no recipe for it")
        await pilot.press("enter")
        await on_screen(pilot, app, "clank engine adopt")
        assert not isinstance(app.screen, ConfirmScreen)


async def test_the_test_ready_and_local_fit_at_60_columns(client: Client, home: Home, cloud_api: CloudBench) -> None:
    cloud_api.add()
    cloud_api.run("daily-262k")
    app = make(client, home)
    async with app.run_test(size=(60, 50)) as pilot:
        await to_test(pilot, app)
        assert_frame(await on_screen(pilot, app, "n keep it"), "add-model-test-asking-60")
        await pilot.press("n")
        assert_frame(await on_screen(pilot, app, "Ready", "enter this folder"), "add-model-ready-60")
        page_of(app).start()
        await on_screen(pilot, app, CHOICE)
        await pilot.press("l")
        assert_frame(await on_screen(pilot, app, "Local: a model on this", "install"), "add-model-local-60")


async def test_an_agreement_not_read_cannot_be_agreed_to(
    client: Client, home: Home, cloud_api: CloudBench, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(preset: str = "", folder: str = "") -> dict[str, object]:
        raise ApiError(503, "unavailable", "the guide cannot be read now")

    monkeypatch.setattr(cloud_api.kernel.parts["agents"], "add_model_guide", down)
    app = make(client, home)
    async with app.run_test(size=(88, 34)) as pilot:
        await settle(pilot, lambda: app.data.usable is not None)
        await pilot.press("c", "enter")
        await settle(pilot, lambda: page_of(app).screen_name == "agreement")
        await pilot.press("y")
        await on_screen(pilot, app, "the agreement is not read yet")
    assert cloud_api.endpoint is None
    assert cloud_api.calls == []


async def test_with_no_server_listed_the_agreement_leaves_the_servers_to_the_service(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    app = make(client, home)
    async with app.run_test(size=(88, 44)) as pilot:
        await on_screen(pilot, app, CHOICE)
        await pilot.press("c", "enter")
        await on_screen(pilot, app, AGREEMENT, "No MCP server is added")
        await pilot.press("y")
        await on_screen(pilot, app, KEY_SCREEN)
    assert cloud_api.calls[0] == ("POST", "runtime/endpoints", {"id": "openrouter", "adapter": "openrouter",
                                                                 "agree": True})  # fmt: skip


async def test_once_agreed_esc_from_the_key_skips_the_agreement_done(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    app = make(client, home)
    async with app.run_test(size=(88, 34)) as pilot:
        await on_screen(pilot, app, CHOICE)
        await pilot.press("c", "enter")
        await on_screen(pilot, app, AGREEMENT)
        await pilot.press("y")
        await settle(pilot, lambda: page_of(app).screen_name == "key")
        await pilot.press("escape")
        await settle(pilot, lambda: page_of(app).screen_name == "choice")


async def test_at_60_columns_the_keys_bar_keeps_the_keys_each_step_needs(
    client: Client, home: Home, kernel: Kernel, cloud_api: CloudBench
) -> None:
    servers(kernel, "lit")
    app = make(client, home)
    async with app.run_test(size=(60, 40)) as pilot:
        await on_screen(pilot, app, CHOICE)
        await pilot.press("c", "enter")
        await on_screen(pilot, app, AGREEMENT)
        bar = render_text(app).splitlines()[-1]
        assert all(key in bar for key in ("y agree", "n back", "space mark", "o policy")), bar
        await pilot.press("y")
        await settle(pilot, lambda: page_of(app).screen_name == "key")
        cloud_api.kernel.secrets.put("endpoint/openrouter", "key", KEY, actor=client_actor("cli"))
        page_of(app).start("model")
        await on_screen(pilot, app, "Example Coder")
        bar = render_text(app).splitlines()[-1]
        assert all(key in bar for key in ("/ search", "s sort", "f free", "esc back")), bar
        await pilot.press("enter")
        await on_screen(pilot, app, "Its settings")
        bar = render_text(app).splitlines()[-1]
        assert all(key in bar for key in ("enter take", "tab next", "esc back")), bar
