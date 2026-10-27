"""Design 0002 §2.5, §2.7 and §3.2: the home page shows what runs, what waits for the user and the latest history.
An option's key answers the first waiting question as you (console), and so does its button under it (design 0011
§12.1); a question answered in another client leaves the
list, and the history says who answered; `s` asks Docker to stop (its question appears, since containers Clank did
not start run); a call the service refuses is said in a message and the console stays usable; presence is sent on a
key press, at most once a minute. Design 0016 §11: once a cloud provider is added, Home and the header say the cloud's
spending today and this month against the limits, and a pause, in the service's words."""

from datetime import UTC, datetime

import pytest
from textual.widgets import Label

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.buttons import Buttons
from clank.console.details import DetailsScreen
from clank.console.pages.home import folder_line, gateway_line, gpu_line, now_lines, workspaces_line
from clank.console.snapshot import render_text
from clank.kernel.core import Kernel
from clank.kernel.events import CLANK, Actor
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from tests.console.frames import FOLDER, assert_frame, frame_when, settle
from tests.support.cloud import CloudBench
from tests.support.served import free_port

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 11, 13, 54, tzinfo=UTC)
STOP = QuestionDraft(
    type="approval",
    title="Stop Docker Desktop?",
    detail="2 containers that Clank did not start are running: another-model-relay, toolbox-sandbox-017.",
    options=[Option(id="stop", label="Stop them and Docker", key="y"), Option(id="cancel", label="Cancel", key="n")],
    default="cancel",
)


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    return app


def happening(app: ClankConsole) -> str:
    return " ".join(str(label.content) for label in app.query("#now Label").results(Label))


def waiting(app: ClankConsole) -> str:
    return " ".join(str(label.content) for label in app.query("#waiting Label").results(Label))


async def test_home_shows_what_runs_what_waits_and_the_latest_history(
    client: Client, kernel: Kernel, home: Home
) -> None:
    kernel.questions.ask(STOP, asked_by=CLANK)
    app = make(client, home)
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "Stop Docker Desktop?" in render_text(app) and "(console)" in render_text(app))
        frame = await frame_when(pilot, app, "Stop Docker Desktop?")
        assert "y Stop them and Docker" in frame
        assert "Clank asks: Stop Docker Desktop?" in frame
        assert_frame(frame, "home-question")


async def test_an_options_key_answers_the_first_waiting_question_as_you_through_the_console(
    client: Client, kernel: Kernel, home: Home
) -> None:
    asked = kernel.questions.ask(STOP, asked_by=CLANK)
    app = make(client, home)
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "Stop Docker Desktop?" in waiting(app))
        await pilot.press("n")
        await settle(pilot, lambda: kernel.questions.get(asked.id).answer is not None)
        await settle(pilot, lambda: "Stop Docker Desktop?" not in waiting(app))
    answer = kernel.questions.get(asked.id).answer
    assert answer is not None
    assert (answer.option, answer.by.via) == ("cancel", "console")


async def test_the_first_questions_options_are_buttons_under_it_that_answer_it_as_its_keys_do(
    client: Client, kernel: Kernel, home: Home
) -> None:
    asked = kernel.questions.ask(STOP, asked_by=CLANK)
    app = make(client, home)
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "Stop Docker Desktop?" in waiting(app))
        options = app.query_one("#waiting-options", Buttons)
        assert [(each.label, each.said) for each in options.buttons] == [
            ("y", "Stop them and Docker"),
            ("n", "Cancel"),
            ("v", "the question whole"),
        ]
        await pilot.click("#waiting-options", offset=(len(" y Stop them and Docker  n"), 0))
        await settle(pilot, lambda: kernel.questions.get(asked.id).answer is not None)
    answer = kernel.questions.get(asked.id).answer
    assert answer is not None
    assert (answer.option, answer.by.via) == ("cancel", "console")


async def test_v_shows_the_first_question_whole_until_esc_and_an_answer_from_it_closes_it(
    client: Client, kernel: Kernel, home: Home
) -> None:
    asked = kernel.questions.ask(STOP, asked_by=CLANK)
    app = make(client, home)
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "Stop Docker Desktop?" in waiting(app))
        await pilot.press("v")
        await pilot.pause(0.3)
        assert isinstance(app.screen, DetailsScreen), "the window a key opened stays open"
        assert app.screen.heading == "Stop Docker Desktop?"
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, DetailsScreen))
        await pilot.press("v")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        await pilot.press("n")
        await settle(pilot, lambda: kernel.questions.get(asked.id).answer is not None)
        await settle(pilot, lambda: not isinstance(app.screen, DetailsScreen))


async def test_a_question_answered_elsewhere_leaves_the_list_and_the_history_says_who(
    client: Client, kernel: Kernel, home: Home
) -> None:
    asked = kernel.questions.ask(STOP, asked_by=CLANK)
    app = make(client, home)
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "Stop Docker Desktop?" in waiting(app))
        kernel.questions.answer(asked.id, by=Actor(kind="user", via="vscode"), option="stop")
        await settle(pilot, lambda: "Stop Docker Desktop?" not in waiting(app))
        await settle(pilot, lambda: f"you (vscode) answered {asked.id}" in render_text(app))


BRACKETS = QuestionDraft(
    type="approval",
    title="Delete [/tmp] and [bold]x[/bold]?",
    detail="It holds [/tmp]/cache and [red]the logs[/red].",
    options=[Option(id="delete", label="Delete [/tmp]", key="y"), Option(id="cancel", label="Cancel", key="n")],
    default="cancel",
)


async def test_a_question_whose_words_look_like_markup_is_shown_as_written_in_waiting_for_you_and_the_history(
    client: Client, kernel: Kernel, home: Home
) -> None:
    kernel.questions.ask(BRACKETS, asked_by=CLANK)
    app = make(client, home)
    async with app.run_test(size=(120, 34)) as pilot:
        frame = await frame_when(pilot, app, "Clank asks: Delete [/tmp] and [bold]x[/bold]?")
        assert "Delete [/tmp] and [bold]x[/bold]?" in waiting(app)
        assert "It holds [/tmp]/cache and [red]the logs[/red]." in waiting(app)
        assert "y Delete [/tmp]" in frame


async def test_s_asks_docker_to_stop_and_its_question_appears(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "Fake Docker · running" in render_text(app))
        await pilot.press("s")
        await settle(pilot, lambda: "Stop Fake Docker?" in waiting(app))
        assert "toolbox-sandbox-017" in waiting(app)
        await settle(pilot, lambda: "waiting: it asks you, below" in happening(app))


async def test_a_call_the_service_refuses_is_said_and_the_console_stays_usable(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: app.data.connected)
        app.data.questions = [
            {
                "id": "q-000000",
                "title": "A question the service never asked",
                "detail": "",
                "options": [{"id": "stop", "label": "Stop", "key": "y", "effect": ""}],
                "default": None,
                "asked": "2026-10-11T13:50:00.000Z",
                "asked_by": {"kind": "clank", "via": "test"},
            }
        ]
        app.show_page("home")
        await pilot.press("y")
        await settle(pilot, lambda: "there is no question q-000000" in render_text(app))
        await pilot.press("2")
        await settle(pilot, lambda: app.query_one("#pages").current == "page-questions")  # type: ignore[attr-defined]


async def test_presence_is_sent_on_a_key_press_at_most_once_a_minute(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: app.data.connected)
        for key in ("x", "z", "x", "z", "x"):
            await pilot.press(key)
        await settle(pilot, lambda: "console" in client.get("service")["presence"])
        assert app.presence_sent == 1


async def test_presence_failing_is_not_said_the_header_already_says_the_service_is_down(home: Home) -> None:
    app = make(Client(f"http://127.0.0.1:{free_port()}", "t", name="console"), home)
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "service not running" in render_text(app))
        await pilot.press("x")
        await pilot.pause(4.0)  # a refused connection takes Windows about two seconds to report
        assert app.presence_sent == 1
        assert str(app.query_one("#message", Label).content) == ""


LAST = {
    "id": "r-0", "time": "2026-10-11T13:50:02.000000Z", "role": "agent", "slot": "main", "status": 200, "seconds": 14.2,
    "tokens": 812, "per_second": 57.1, "prompt_tokens": 9120, "error": "", "left": False,
}  # fmt: skip
GATEWAY = {"state": "running", "port": 18210, "problem": "", "served": 3, "requests": [], "last": None}


def test_happening_now_shows_each_operation_its_step_and_last_line_each_model_request_and_the_last() -> None:
    operations = [
        {"id": "op-3", "title": "Load a model", "status": "running", "planned_steps": 3,
         "steps": [{"number": 2, "name": "start the engine", "status": "running"}]},
        {"id": "op-2", "title": "Stop Docker", "status": "waiting", "planned_steps": 2, "steps": []},
        {"id": "op-1", "title": "Build the image", "status": "queued", "planned_steps": 1, "steps": []},
        {"id": "op-0", "title": "Download", "status": "done", "planned_steps": 1, "steps": []},
    ]  # fmt: skip
    requests = [
        {"id": "r-1", "role": "agent", "slot": "main", "phase": "answering", "seconds": 12.4, "tokens": 340,
         "per_second": 52.3},
        {"id": "r-2", "role": "agent", "slot": "", "phase": "waiting for its slot", "seconds": 3.0, "tokens": 0,
         "per_second": None},
    ]  # fmt: skip
    activity = {**GATEWAY, "requests": requests, "last": LAST}
    lines = [line.plain for line in now_lines(operations, {"op-3": "loading tensors: 62%"}, activity, UTC, frame=1)]
    assert lines == [
        "⣽ Load a model · running · step 2 of 3: start the engine",
        "    loading tensors: 62%",
        "? Stop Docker · waiting: it asks you, below",
        "· Build the image · queued",
        "⣽ Model request (agent, main slot) · answering · 12s · 340 tokens, 52.3 per second",
        "⣽ Model request (agent) · waiting for its slot · 3s",
        "Last model request at 13:50:02 (agent, main slot): 812 tokens in 14.2 s, 57.1 per second, after a prompt of "
        "9,120 tokens",
    ]


def test_with_nothing_running_happening_now_says_so_and_how_the_last_model_request_went() -> None:
    assert [line.plain for line in now_lines([], {}, None, UTC)] == ["Nothing runs right now."]
    refused = {**LAST, "status": 503, "error": "no engine runs", "tokens": 0, "per_second": None, "prompt_tokens": None}
    assert [line.plain for line in now_lines([], {}, {**GATEWAY, "last": refused}, UTC)] == [
        "Nothing runs right now.",
        "Last model request at 13:50:02 (agent, main slot): failed (503): no engine runs",
    ]
    left = {**LAST, "left": True, "tokens": 40, "per_second": 20.0, "prompt_tokens": None}
    assert now_lines([], {}, {**GATEWAY, "last": left}, UTC)[1].plain == (
        "Last model request at 13:50:02 (agent, main slot): its client left after 40 tokens in 14.2 s, 20 per second"
    )


def test_the_rows_for_the_gateway_the_gpu_the_workspaces_and_this_folder() -> None:
    assert gateway_line({**GATEWAY, "requests": [{}]}).plain == (
        "gateway    ● running on port 18210 · 1 request in flight · 3 requests served"
    )
    idle = gateway_line({**GATEWAY, "served": 0}).plain
    assert idle == "gateway    ● running on port 18210 · idle · 0 requests served"
    assert gateway_line({**GATEWAY, "state": "stopped"}).plain == "gateway    ○ stopped   F4, then g, starts it"
    assert gateway_line(None).plain == "gateway    … not read yet"
    gpu = {"name": "NVIDIA GeForce RTX 5080", "use": 3.0, "memory_used": 2041 << 20, "memory_total": 16303 << 20,
           "temperature": 34, "power": 18.0, "power_limit": 360.0}  # fmt: skip
    assert gpu_line([{"gpus": [gpu]}]).plain == "gpu        RTX 5080 · 3% busy · 2.0 GB of 15.9 GB in use · 34°C"
    assert gpu_line([{"gpus": []}]).plain == "gpu        none: no NVIDIA GPU answered"
    assert gpu_line([]).plain == "gpu        not read yet"

    def made(record: str, state: str, status: str = "Up 2 hours") -> dict[str, object]:
        labels = {"clank.component": "workspaces", "clank.record": record}
        return {"name": f"clank-h1-{record}", "state": state, "status": status, "owner": "clank", "clank": labels}

    containers = [made("paper", "running"), made("edge", "running", "Up 3 minutes"), made("notes", "exited", "")]
    containers.append({"name": "toolbox-sandbox-017", "state": "running", "owner": "other", "clank": {}})
    docker = {"state": "running", "containers": containers}
    shown = workspaces_line(docker).plain
    assert shown == "workspace  ● paper: running   F6 lists them", "the edge is not a workspace"
    containers.append(made("website", "running", "Up 24 minutes"))
    newest = workspaces_line(docker).plain
    assert newest == "workspace  ● website: running · 1 more running   F6 lists them", "the newest"
    assert workspaces_line({"state": "running", "containers": []}).plain == "workspace  ○ none running   F6 lists them"
    assert workspaces_line({"state": "stopped", "containers": []}).plain == "workspace  ○ none: Docker is stopped"
    assert workspaces_line(None).plain == "workspace  … not read yet"
    assert folder_line("C:/work/paper").plain == "folder     C:/work/paper   F4: get ready and work here"


async def test_home_and_the_header_say_the_clouds_spending_and_a_pause_in_the_services_words(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    cloud_api.set_limits(day_usd=5.0)
    cloud_api.spend(0.42, requests=31)
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "$0.42 today" in render_text(app))
        frame = render_text(app)
        assert "● cloud $0.42 today · $0.42 this month" in frame.splitlines()[0]
        assert "$0.42 today · $0.42 this month · today's limit $5.00; no monthly limit" in " ".join(frame.split())
        cloud_api.reach("day", 5.02)
        paused = "cloud paused: today's limit of $5.00 reached ($5.44 spent) · L raise"
        await settle(pilot, lambda: paused in render_text(app))
        assert paused in render_text(app).splitlines()[0]


def test_a_slot_that_does_not_run_reads_not_loaded_with_its_reason_only_when_it_says_more() -> None:
    """The owner's Home said "fast: stopped (unloaded (stopped))" (the end-to-end test, 2026-10-26)."""
    from clank.console.pages.home import slot_words

    assert slot_words("stopped", "unloaded (stopped)") == "not loaded"
    assert slot_words("stopped", "never started") == "not loaded (never started)"
    assert slot_words("stopped", "") == "not loaded"
    assert slot_words("failed", "out of memory") == "failed (out of memory)"
