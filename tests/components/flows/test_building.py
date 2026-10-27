"""Design 0013 §9 and §15 (decisions 0097, 0099 and 0101): a planning, the owner's talk with the model that builds a
flow. Its first message, kept beside it, names the workspace, the flow, each preset of the main slot with its window,
the owner's three answers, the brief, `flow_draft`, the template's model and Clank's template without its plan's gate;
one planning is open in a workspace at a time, a newer one setting the older aside only when told (else refused, the
open one never overwritten, through the API too); a name an existing flow has is
refused. A draft (`flow_draft`) that breaks a rule is refused naming each problem with its field, with the check's
warnings; one that keeps them is written as the flow's file with Clank's settings, and the owner is asked "flow built:
look, then r to run" with the next flow's answers; a draft again replaces it and asks again, unless the owner changed it
since; with no planning open, or once its flow ran, a draft is refused; *Run it now* starts the flow, and a run started
otherwise withdraws the question. A draft reaches the service as the agent's, its refusal a 409 in the model's words.
The planning's session is started on the workspace's OpenCode window, sent to the planner with the first message and
titled after the flow, once that window answers: here, the window whose command the planning gives; in VS Code, the
window running, else the one VS Code's extension prepares; a window that never answers fails the planning, said. The
owner opens a planning through the API; the agent cannot. A workspace whose container runs an older sandbox image is
refused, naming the fix, when a planning opens and when it is attached. A session the window does not show stands, the
planning saying to pick it from its list. Each draft is kept with its number, time, state and problems, the latest's
values beside the planning in Clank's state; a new planning starts with none, though the one before of its name had
drafts. A planning opened to attach takes no window running; attach prepares its window (another closed first, said),
the waiting planning starting there, a talking one shown there, none started; one that failed, with no run since, tried
again there; one whose session is still starting refused, saying to wait, no other window prepared; with none open,
refused saying how to open one."""

import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient

from clank.components.flows import building as building_module
from clank.components.flows.building import BuildError, Building, Planning
from clank.components.flows.kinds import Flow
from clank.components.flows.verdicts import AGENT
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import OWNER, Rig, make_rig, question, study, until
from tests.components.flows.test_flow_built import drafted

pytestmark = pytest.mark.anyio


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    return make_rig(home, clock, tmp_path, monkeypatch, None)


def building(rig: Rig) -> Building:
    found: Building = rig.kernel.parts["flows"].building
    return found


def example_of(text: str) -> dict[str, Any]:
    """The JSON example the first message holds."""
    block = text.split("```json\n", 1)[1].split("\n```", 1)[0]
    found: dict[str, Any] = json.loads(block)
    return found


def test_a_plannings_first_message_names_the_flow_the_presets_the_answers_and_the_template(rig: Rig) -> None:
    planning = building(rig).begin("myproject", "", "here", actor=OWNER)
    assert (planning.flow, planning.status) == ("myproject/flow", "waiting")
    folder = rig.kernel.home.state / "flows" / "myproject" / "flow"
    kept = json.loads((folder / "building.json").read_text(encoding="utf-8"))
    assert (kept["flow"], kept["where"], kept["status"]) == ("myproject/flow", "here", "waiting")
    text = (folder / "first-message.md").read_text(encoding="utf-8")
    assert text == building(rig).first_message(planning)
    assert "`myproject/flow`" in text
    assert "the workspace `myproject`" in text
    for title in ("frontier 262K", "daily 262K"):
        assert f"- {title}:" in text, f"each preset of the main slot is named: {title}"
    assert "vision 4B" not in text, "a preset of another slot is not"
    assert "completion 0.5B" not in text
    assert "tokens of context" in text, "with its window"
    assert "it stops only at the end" in text
    assert "Once built, the user looks, then runs it" in text
    assert "`BRIEF.md`" in text
    assert "`flow_draft`" in text
    assert "These instructions override your instructions as the Planner" in text, "planner.md says otherwise"
    assert "no file with a `kind: plan` header" in text
    assert "never tell the user to `/implement`" in " ".join(text.split())
    assert "Every box runs on what the main slot runs when the box starts" in text, "the template names no model"
    example = example_of(text)
    titles = [box["title"] for box in example["boxes"]]
    assert "You approve the plan" not in titles, "the template's plan's gate taken out"
    assert titles[-1] == "You review the whole"
    assert {"from": "check", "to": "split", "when": "pass"} in example["lines"]
    assert example.get("defaults", {}).get("model", "") == "", "the template names no model"
    assert "$" not in text.replace("$ARGUMENTS", ""), "every placeholder filled in"


def test_a_newer_planning_in_the_workspace_sets_the_older_aside(rig: Rig) -> None:
    first = building(rig).begin("myproject", "study", "here", actor=OWNER)
    second = building(rig).begin("myproject", "", "vscode", actor=OWNER, aside=True)
    assert building(rig).open_in("myproject") == second
    older = building(rig).planning(first.flow)
    assert older is not None
    assert older.status == "set aside"
    assert "myproject/flow" in older.why
    said = [event.summary for event in rig.events("flows.building")]
    assert any("set aside" in each for each in said)


def test_a_name_an_existing_flow_has_is_refused(rig: Rig) -> None:
    rig.write_flow(study())
    with pytest.raises(BuildError, match="myproject/study exists"):
        building(rig).begin("myproject", "study", "here", actor=OWNER)
    assert building(rig).begin("myproject", "", "here", actor=OWNER).name == "flow"
    with pytest.raises(BuildError, match="no workspace"):
        building(rig).begin("elsewhere", "", "here", actor=OWNER)


BRIEF = "# A new simulation study\n\n- at most 48 CPU-hours\n- about 60 grid points\n"
BUILT = "flow built: look, then r to run"


def opened(rig: Rig, name: str = "") -> str:
    """A planning opened, the brief written with the model: its flow's id."""
    planning = building(rig).begin("myproject", name, "here", actor=OWNER)
    rig.write("BRIEF.md", f"{BRIEF}\n<!-- written with the model for {planning.flow} -->\n")
    return planning.flow


def test_a_draft_that_breaks_a_rule_is_refused_naming_each_problem_with_its_field_and_the_warnings(rig: Rig) -> None:
    flow = opened(rig)
    draft = drafted()
    draft["boxes"][1]["model"] = "no such model"
    draft["boxes"][1]["sees"] = ["BRIEF.md", "data/grid.csv"]
    draft["boxes"].insert(3, {"id": "approve", "type": "gate", "title": "You approve the plan", "shows": ["PLAN.md"]})
    draft["lines"][2] = {"from": "check", "to": "approve", "when": "pass"}
    draft["lines"].append({"from": "approve", "to": "split"})
    with pytest.raises(BuildError) as refused:
        building(rig).draft("myproject", draft, actor=AGENT)
    said = str(refused.value)
    assert said.startswith("Not written. Fix each, then call flow_draft again:")
    assert "- boxes.1.model: names the preset 'no such model', which does not exist" in said
    assert "- boxes.3.type: a built flow waits for the user only at its end" in said
    assert "Warnings of Clank's check" in said
    assert "plan sees data/grid.csv, which is not in the folder" in said
    planning = building(rig).planning(flow)
    assert planning is not None
    assert (planning.status, planning.drafts, planning.written) == ("waiting", 1, 0)
    assert len(planning.problems) == 2
    assert not (rig.kernel.home.config / "flows" / "myproject" / "flow.json").exists(), "nothing written"
    assert [event.data["action"] for event in rig.events("flows.building")][-1] == "refused"

    broken = drafted()
    broken["lines"].append({"from": "join", "to": "nowhere"})
    with pytest.raises(BuildError, match=r"- lines\.6\.to: names no box of the flow: nowhere"):
        building(rig).draft("myproject", broken, actor=AGENT)
    with pytest.raises(BuildError, match="send the whole flow as an object"):
        building(rig).draft("myproject", ["not", "a", "flow"], actor=AGENT)


def test_a_brief_left_from_before_the_planning_is_refused_until_it_is_written_with_the_owner(rig: Rig) -> None:
    rig.write("BRIEF.md", BRIEF)  # an old brief, there before the planning began
    building(rig).begin("myproject", "", "here", actor=OWNER)
    with pytest.raises(BuildError, match=r"BRIEF.md is as it was when the planning began"):
        building(rig).draft("myproject", drafted(), actor=AGENT)
    rig.write("BRIEF.md", BRIEF + "- about 60 grid points, as we said\n")
    building(rig).draft("myproject", drafted(), actor=AGENT)
    made = rig.kernel.settings.get("flow", "myproject/flow").record
    assert isinstance(made, Flow)
    assert made.built is not None
    assert made.built.before, "the brief's fingerprint when the planning began, kept for the run"


def test_a_field_the_draft_should_not_have_is_named_with_the_fields_of_what_it_is_in(rig: Rig) -> None:
    opened(rig)
    draft = drafted()
    draft["boxes"][1]["deliverable"] = ["PLAN.md"]  # flow_propose_box's word, not a box's field
    draft["lines"][0]["kind"] = "then"
    draft["defaults"] = {"modle": "frontier 262K"}
    with pytest.raises(BuildError) as refused:
        building(rig).draft("myproject", draft, actor=AGENT)
    said = str(refused.value)
    assert "- boxes.1.deliverable: is not a field of a box (its fields: id, type, title," in said
    assert "writes, holds, accept_when" in said
    assert "- lines.0.kind: is not a field of a line (its fields: from, to, when)" in said
    assert "- defaults.modle: is not a field of the defaults (its fields: model, tries, limits" in said


def test_a_draft_that_keeps_the_rules_is_written_with_clanks_settings_and_the_owner_is_told(rig: Rig) -> None:
    flow = opened(rig)
    answer = building(rig).draft("myproject", {**drafted(), "auto_accept": False}, actor=AGENT)
    said = answer["said"]
    assert said.startswith("Written as myproject/flow: 6 boxes")
    assert "auto_accept to true (yours: false)" in said
    assert "Tell the user" in said
    assert "clank console --page monitor --view flow" in said, "the Flow view without F10, for a terminal over SSH"
    loaded = rig.kernel.settings.get("flow", flow).record
    assert isinstance(loaded, Flow)
    assert (loaded.auto_accept, loaded.wait_after_every_box, loaded.next_flow) == (True, False, "ask")
    assert loaded.defaults.model == "", "the draft named none, nor does the template: what the main slot runs"
    assert loaded.built is not None
    assert loaded.built.brief == "BRIEF.md"
    told = question(rig, BUILT)
    assert told is not None
    assert told.title == f"A new simulation study: {BUILT}"
    assert "clank console --page monitor --view flow" in told.detail
    assert {option.id for option in told.options} == {"run-next", "later"}
    assert told.about is not None
    assert told.about.id == flow
    planning = building(rig).planning(flow)
    assert planning is not None
    assert (planning.status, planning.written, planning.question) == ("built", 1, told.id)
    assert [event.data["action"] for event in rig.events("flows.building")][-1] == "written"


def test_a_draft_written_again_replaces_the_flow_and_asks_again_unless_the_owner_changed_it(rig: Rig) -> None:
    flow = opened(rig)
    building(rig).draft("myproject", drafted(), actor=AGENT)
    first = question(rig, BUILT)
    building(rig).draft("myproject", drafted(title="The study, smaller"), actor=AGENT)
    assert rig.kernel.settings.get("flow", flow).record.title == "The study, smaller"
    asked = [each for each in rig.waiting() if BUILT in each.title]
    assert [each.title for each in asked] == [f"The study, smaller: {BUILT}"]
    assert first is not None
    assert rig.kernel.questions.get(first.id).status == "withdrawn"

    changed = json.loads((rig.kernel.home.config / "flows" / "myproject" / "flow.json").read_text(encoding="utf-8"))
    changed["boxes"][1]["prompt"] = "Write the study plan, shorter."
    rig.write_flow(changed, "flow")  # the owner's edit, in the Flow view or by hand
    with pytest.raises(BuildError, match="the user changed myproject/flow since"):
        building(rig).draft("myproject", drafted(), actor=AGENT)


def test_a_draft_with_no_planning_open_or_once_its_flow_ran_is_refused(rig: Rig) -> None:
    with pytest.raises(BuildError, match="no flow is being built in myproject"):
        building(rig).draft("myproject", drafted(), actor=AGENT)
    flow = opened(rig)
    building(rig).draft("myproject", drafted(), actor=AGENT)
    rig.runner.start(flow, actor=OWNER)
    planning = building(rig).planning(flow)
    assert planning is not None
    assert planning.status == "ran"
    with pytest.raises(BuildError, match="no flow is being built in myproject"):
        building(rig).draft("myproject", drafted(), actor=AGENT)


async def test_run_it_now_starts_the_built_flow_and_a_run_started_otherwise_withdraws_the_question(rig: Rig) -> None:
    flow = opened(rig)
    building(rig).draft("myproject", drafted(), actor=AGENT)
    told = question(rig, BUILT)
    assert told is not None
    rig.kernel.questions.answer(told.id, by=OWNER, option="run-next")
    started = rig.runner.runs.latest(flow)
    assert started is not None
    assert started.started_by == OWNER

    other = opened(rig)
    building(rig).draft("myproject", drafted(), actor=AGENT)
    again = question(rig, BUILT)
    assert again is not None
    rig.runner.stop(flow, actor=OWNER)
    rig.runner.start(other, actor=OWNER)
    assert rig.kernel.questions.get(again.id).status == "withdrawn"


def test_the_draft_route_is_the_agents_its_refusal_a_409_in_the_models_words(rig: Rig) -> None:
    opened(rig)
    agent = {"Authorization": "Bearer t", "X-Clank-Client": "agent"}
    app = create_app(rig.kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as service:
        broken = drafted()
        broken["boxes"][1]["when_done"] = "wait"
        refused = service.post("/api/v1/flows/draft", headers=agent, json={"workspace": "myproject", "flow": broken})
        assert refused.status_code == 409, refused.text
        assert "- boxes.1.when_done: a built flow waits only at its end" in refused.json()["error"]["message"]
        given = service.post("/api/v1/flows/draft", headers=agent, json={"workspace": "myproject", "flow": drafted()})
        assert given.status_code == 200, given.text
        assert given.json()["said"].startswith("Written as myproject/flow")
    [written] = [event for event in rig.events("flows.building") if event.data["action"] == "written"]
    assert written.actor == AGENT


TITLE = "flow · building the flow"


def planning_of(rig: Rig, flow: str = "myproject/flow") -> Planning:
    found = building(rig).planning(flow)
    assert found is not None
    return found


async def test_here_the_planning_gives_the_windows_command_and_its_session_starts_on_that_window_once_it_answers(
    rig: Rig,
) -> None:
    answer = building(rig).open("myproject", "", "here", actor=OWNER)
    assert answer["flow"] == "myproject/flow"
    assert answer["where"] == "here"
    port = answer["port"]
    assert "opencode" in answer["argv"]
    assert answer["argv"][answer["argv"].index("--port") + 1] == str(port)
    assert planning_of(rig).status == "opening", "told the window's port by prepare"
    rig.bridge.window()  # OpenCode starts in the console's terminal, on that port
    prompt = await until(lambda: rig.bridge.prompted(TITLE))
    assert (prompt.port, prompt.agent) == (port, "planner")
    assert prompt.text == building(rig).first_message(planning_of(rig))
    talking = await until(lambda: planning_of(rig).status == "talking" and planning_of(rig))
    assert (talking.port, talking.session) == (port, prompt.session)
    actions = [event.data["action"] for event in rig.events("flows.building")]
    assert actions == ["opened", "opening", "talking"]


async def test_a_session_the_window_does_not_show_stands_and_the_planning_says_to_pick_it(rig: Rig) -> None:
    rig.bridge.show = False
    building(rig).open("myproject", "", "here", actor=OWNER)
    rig.bridge.window()
    prompt = await until(lambda: rig.bridge.prompted(TITLE))
    talking = await until(lambda: planning_of(rig).status == "talking" and planning_of(rig))
    assert talking.session == prompt.session
    assert f"pick “{TITLE}” from OpenCode's session list" in talking.why
    said = [event.summary for event in rig.events("flows.building")][-1]
    assert f"pick “{TITLE}”" in said
    rig.write("BRIEF.md", BRIEF)
    assert building(rig).draft("myproject", drafted(), actor=AGENT)["said"].startswith("Written as"), "it drafts"


async def test_in_vs_code_the_window_running_takes_the_session(rig: Rig) -> None:
    port = rig.bridge.window()  # OpenCode runs in Clank's VS Code window already
    answer = building(rig).open("myproject", "", "vscode", actor=OWNER)
    assert (answer["where"], answer["window"], answer["port"]) == ("vscode", "running", port)
    assert "argv" not in answer
    prompt = await until(lambda: rig.bridge.prompted(TITLE))
    assert (prompt.port, prompt.agent) == (port, "planner")


async def test_in_vs_code_with_no_window_the_planning_waits_for_the_one_vs_code_prepares(rig: Rig) -> None:
    answer = building(rig).open("myproject", "", "vscode", actor=OWNER)
    assert answer["window"] == "waits"
    assert planning_of(rig).status == "waiting"
    await anyio.sleep(0.2)
    assert rig.bridge.prompted(TITLE) is None, "nothing started until a window is"
    prepared = rig.kernel.parts["agents"].prepare("myproject")  # VS Code's extension starts OpenCode in its terminal
    rig.bridge.window()
    prompt = await until(lambda: rig.bridge.prompted(TITLE))
    assert prompt.port == prepared["port"]


async def test_a_window_that_never_answers_fails_the_planning_said(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(building_module, "WINDOW_SECONDS", 0.3)
    building(rig).open("myproject", "", "here", actor=OWNER)
    failed = await until(lambda: planning_of(rig).status == "failed" and planning_of(rig))
    assert "no OpenCode window answered" in failed.why
    # Said, though not necessarily last: on a slow machine the planning's own "opening" line can come after it.
    assert "failed" in [event.data["action"] for event in rig.events("flows.building")]


async def test_a_planning_opened_to_attach_takes_no_window_running_and_waits_for_attach(rig: Rig) -> None:
    rig.bridge.window()  # an OpenCode window open in the workspace already: on the PC's own screen, perhaps
    answer = building(rig).open("myproject", "", "attach", actor=OWNER)
    assert (answer["where"], answer["window"]) == ("attach", "waits")
    assert answer["attach"] == f"cd {rig.folder} then clank flow attach"
    await anyio.sleep(0.2)
    assert rig.bridge.prompted(TITLE) is None, "the window running is not taken"
    assert planning_of(rig).status == "waiting"
    [opened] = [event for event in rig.events("flows.building") if event.data["action"] == "opened"]
    assert opened.summary.endswith("opened a planning of myproject/flow, beside the console (clank flow attach)")
    assert opened.data["where"] == "attach"


async def test_attach_prepares_the_window_closing_another_first_and_the_waiting_planning_starts_there(
    rig: Rig,
) -> None:
    rig.bridge.window()  # another OpenCode window in the workspace: one at a time
    building(rig).open("myproject", "", "attach", actor=OWNER)
    answer = building(rig).attach("myproject", actor=OWNER)
    assert answer["flow"] == "myproject/flow"
    assert answer["closed"] == 1
    assert any("closed the OpenCode window open in myproject first" in note for note in answer["notes"])
    assert answer["title"] == TITLE
    rig.bridge.window()  # OpenCode starts in the attaching terminal
    prompt = await until(lambda: rig.bridge.prompted(TITLE))
    assert (prompt.port, prompt.agent) == (answer["port"], "planner")


async def test_attach_to_a_planning_already_talking_shows_its_session_and_starts_no_other(rig: Rig) -> None:
    building(rig).open("myproject", "", "attach", actor=OWNER)
    building(rig).attach("myproject", actor=OWNER)
    rig.bridge.window()
    first = await until(lambda: rig.bridge.prompted(TITLE))
    talking = await until(lambda: planning_of(rig).status == "talking" and planning_of(rig))
    before = len(rig.events("flows.building"))
    again = building(rig).attach("myproject", actor=OWNER)  # its window closed meanwhile, or another terminal
    rig.bridge.window()
    await until(lambda: rig.bridge.done("show"))
    assert rig.bridge.done("show")[-1] == [str(again["port"]), talking.session]
    assert len([each for each in rig.bridge.prompts if each.title == TITLE]) == 1, "no second session"
    assert first.session == talking.session
    after = [event.data["action"] for event in rig.events("flows.building")[before:]]
    assert "attached" in after, "the planning's own status lines may come after it on a slow machine (CI, 2026-10-26)"
    acted = rig.events("agents.acted")[-1]
    assert (acted.data["action"], acted.data["session"]) == ("show", talking.session)
    assert "showed a session of myproject's agent" in acted.summary, "nothing started"


def test_attach_with_no_planning_open_is_refused_saying_how_to_open_one(rig: Rig) -> None:
    with pytest.raises(BuildError) as refused:
        building(rig).attach("myproject", actor=OWNER)
    said = str(refused.value)
    assert "no planning is open in myproject" in said
    assert "n on the console's Flow view" in said
    assert "clank flow new" in said


def test_the_owner_opens_a_planning_through_the_api_and_the_agent_cannot(rig: Rig) -> None:
    app = create_app(rig.kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as service:
        body = {"folder": str(rig.folder), "where": "vscode"}
        agent = {"Authorization": "Bearer t", "X-Clank-Client": "agent"}
        refused = service.post("/api/v1/flows/new", headers=agent, json=body)
        assert refused.status_code == 403
        attached = service.post("/api/v1/flows/attach", headers=agent, json={"folder": str(rig.folder)})
        assert attached.status_code == 403, "the agent attaches no window either"
        owner = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
        opened = service.post("/api/v1/flows/new", headers=owner, json=body)
        assert opened.status_code == 200, opened.text
        assert opened.json()["flow"] == "myproject/flow"
        shown = service.get("/api/v1/flows/building", headers=owner, params={"folder": str(rig.folder)})
        assert shown.json()["planning"]["status"] == "waiting"
        rig.write_flow(study())
        taken = service.post("/api/v1/flows/new", headers=owner, json={**body, "name": "study"})
        assert taken.status_code == 409
        assert "a flow myproject/study exists" in taken.json()["error"]["message"]


def test_the_flow_view_follows_a_flow_built_and_not_run_yet_with_its_drafts_warnings(rig: Rig) -> None:
    rig.write_flow(study())
    rig.write("BRIEF.md", "# The study before\n")
    rig.runner.start("myproject/study", actor=OWNER)
    rig.runner.stop("myproject/study", actor=OWNER)  # a flow that ran before
    rig.clock.advance(60)
    flow = opened(rig)
    draft = drafted()
    draft["boxes"][1]["sees"] = ["BRIEF.md", "data/grid.csv"]
    building(rig).draft("myproject", draft, actor=AGENT)
    shown = rig.kernel.parts["flows"].view(str(rig.folder))
    assert shown["flow"] == flow, "the flow built since the other ran"
    assert shown["run"] is None
    built = shown["built"]
    assert (built["status"], built["brief"]) == ("built", "BRIEF.md")
    assert any("data/grid.csv" in each for each in built["warnings"])
    assert built["question"]


def test_a_container_made_from_an_older_image_is_refused_naming_the_fix(rig: Rig) -> None:
    [made] = rig.platform.containers
    rig.platform.containers[0] = made.model_copy(update={"image": "clank-sandbox:000000000000"})
    with pytest.raises(BuildError) as refused:
        building(rig).open("myproject", "", "here", actor=OWNER)
    said = str(refused.value)
    assert "myproject's container runs an older sandbox image" in said
    assert "stop the workspace and open it again" in said
    assert "clank workspace stop" in said
    assert building(rig).open_in("myproject") is None, "no planning opened"


def test_attach_to_a_container_made_from_an_older_image_is_refused_naming_the_fix(rig: Rig) -> None:
    building(rig).open("myproject", "", "attach", actor=OWNER)
    [made] = rig.platform.containers
    rig.platform.containers[0] = made.model_copy(update={"image": "clank-sandbox:000000000000"})
    with pytest.raises(BuildError) as refused:
        building(rig).attach("myproject", actor=OWNER)
    assert "myproject's container runs an older sandbox image" in str(refused.value)
    assert "stop the workspace and open it again" in str(refused.value)
    assert planning_of(rig).status == "waiting", "no window prepared"


def test_each_draft_is_kept_with_its_number_time_state_and_problems_the_latest_beside_the_planning(rig: Rig) -> None:
    flow = opened(rig)
    with pytest.raises(BuildError):
        building(rig).draft("myproject", ["not", "a", "flow"], actor=AGENT)
    broken = drafted(title="The study, first")
    broken["boxes"][1]["when_done"] = "wait"
    with pytest.raises(BuildError):
        building(rig).draft("myproject", broken, actor=AGENT)
    rig.clock.advance(30)
    building(rig).draft("myproject", drafted(title="The study"), actor=AGENT)
    planning = planning_of(rig, flow)
    assert [(each.number, each.state) for each in planning.history] == [(1, "refused"), (2, "refused"), (3, "accepted")]
    assert "send the whole flow as an object" in planning.history[0].problems[0]
    assert any(problem.startswith("boxes.1.when_done:") for problem in planning.history[1].problems)
    assert planning.history[2].problems == []
    assert planning.history[2].at > planning.history[1].at
    kept = rig.kernel.home.state / "flows" / "myproject" / "flow" / "draft.json"
    assert json.loads(kept.read_text(encoding="utf-8"))["title"] == "The study", "the latest draft, as Clank wrote it"
    files = sorted(path.name for path in rig.folder.rglob("*") if path.is_file())
    assert files == ["BRIEF.md"], "nothing in the folder"


def test_a_new_planning_starts_with_no_draft_though_the_one_before_of_its_name_had_drafts(rig: Rig) -> None:
    flow = opened(rig)
    broken = drafted(title="The study, refused")
    broken["boxes"][1]["when_done"] = "wait"
    with pytest.raises(BuildError):
        building(rig).draft("myproject", broken, actor=AGENT)
    assert building(rig).plannings.draft(flow) is not None
    building(rig)._change(flow, status="set aside")
    again = building(rig).begin("myproject", "flow", "attach", actor=OWNER)  # the name of a planning set aside
    assert again.flow == flow
    assert building(rig).plannings.draft(flow) is None, "the draft before is not this planning's"
    shown = rig.kernel.parts["flows"].view(str(rig.folder))
    assert (shown["draft"], shown["boxes"]) == (None, [])


async def test_attach_tries_a_planning_that_failed_again_and_its_session_starts_on_the_new_window(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(building_module, "WINDOW_SECONDS", 0.3)
    building(rig).open("myproject", "", "attach", actor=OWNER)
    building(rig).attach("myproject", actor=OWNER)  # its window never answers
    await until(lambda: planning_of(rig).status == "failed")
    monkeypatch.setattr(building_module, "WINDOW_SECONDS", 5.0)
    answer = building(rig).attach("myproject", actor=OWNER)
    assert answer["flow"] == "myproject/flow"
    rig.bridge.window()
    prompt = await until(lambda: rig.bridge.prompted(TITLE))
    assert prompt.port == answer["port"]
    talking = await until(lambda: planning_of(rig).status == "talking" and planning_of(rig))
    assert talking.why == ""
    assert "again" in [event.data["action"] for event in rig.events("flows.building")]


def test_a_planning_that_failed_before_a_run_is_not_tried_again(rig: Rig) -> None:
    building(rig).open("myproject", "", "attach", actor=OWNER)
    building(rig)._failed("myproject/flow", "no OpenCode window answered")
    rig.clock.advance(60)
    rig.write_flow(study())
    rig.runner.start("myproject/study", actor=OWNER)
    with pytest.raises(BuildError, match="no planning is open in myproject"):
        building(rig).attach("myproject", actor=OWNER)


def test_a_draft_refused_since_its_flow_changed_or_ran_is_kept_in_the_history_too(rig: Rig) -> None:
    flow = opened(rig)
    building(rig).draft("myproject", drafted(), actor=AGENT)
    changed = json.loads((rig.kernel.home.config / "flows" / "myproject" / "flow.json").read_text(encoding="utf-8"))
    changed["boxes"][1]["prompt"] = "Write the study plan, shorter."
    rig.write_flow(changed, "flow")  # the owner's edit
    with pytest.raises(BuildError, match="the user changed myproject/flow since"):
        building(rig).draft("myproject", drafted(), actor=AGENT)
    rig.runner.start(flow, actor=OWNER)
    building(rig)._change(flow, status="built")  # the run's start not heard yet
    with pytest.raises(BuildError, match="myproject/flow has run"):
        building(rig).draft("myproject", drafted(), actor=AGENT)
    history = planning_of(rig, flow).history
    assert [(each.number, each.state) for each in history] == [(1, "accepted"), (2, "refused"), (3, "refused")]
    assert "the user changed myproject/flow since you drafted it" in history[1].problems[0]
    assert "myproject/flow has run" in history[2].problems[0]


async def test_attach_while_its_session_is_starting_says_to_wait_and_prepares_no_other_window(rig: Rig) -> None:
    building(rig).open("myproject", "", "attach", actor=OWNER)
    first = building(rig).attach("myproject", actor=OWNER)  # its window is still starting
    assert planning_of(rig).status == "opening"
    with pytest.raises(BuildError) as refused:
        building(rig).attach("myproject", actor=OWNER)
    said = str(refused.value)
    assert f"starting its session on the OpenCode window at port {first['port']}" in said
    assert "then `clank flow attach` shows it here, or tries it again if that window is gone" in said
    rig.bridge.window()  # the first window answers: the session starts there
    prompt = await until(lambda: rig.bridge.prompted(TITLE))
    assert prompt.port == first["port"]
    assert (await until(lambda: planning_of(rig).status == "talking" and planning_of(rig))).port == first["port"]


def test_a_planning_open_is_never_overwritten_a_new_one_sets_it_aside_only_when_told(rig: Rig) -> None:
    first = building(rig).begin("myproject", "", "attach", actor=OWNER)
    building(rig)._change(first.flow, status="talking", session="ses_plan", port=4096)
    with pytest.raises(BuildError) as refused:
        building(rig).begin("myproject", "", "attach", actor=OWNER)
    said = str(refused.value)
    assert "a planning is open in myproject: myproject/flow (talking)" in said
    assert "clank flow new --set-aside" in said
    assert planning_of(rig).session == "ses_plan", "not overwritten"
    with pytest.raises(BuildError, match="myproject/flow is the planning open: name another"):
        building(rig).begin("myproject", "flow", "attach", actor=OWNER, aside=True)
    second = building(rig).begin("myproject", "", "attach", actor=OWNER, aside=True)
    assert second.flow == "myproject/flow-2", "a name of its own"
    older = planning_of(rig, "myproject/flow")
    assert (older.status, older.session) == ("set aside", "ses_plan")
    assert [event.data["action"] for event in rig.events("flows.building")][-2:] == ["set aside", "opened"]


def test_the_api_sets_the_open_planning_aside_only_when_asked(rig: Rig) -> None:
    building(rig).begin("myproject", "", "attach", actor=OWNER)
    app = create_app(rig.kernel, token="t", port=7720)
    owner = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
    with TestClient(app, base_url="http://127.0.0.1:7720") as service:
        body = {"folder": str(rig.folder), "where": "attach"}
        refused = service.post("/api/v1/flows/new", headers=owner, json=body)
        assert refused.status_code == 409
        assert "a planning is open in myproject" in refused.json()["error"]["message"]
        opened = service.post("/api/v1/flows/new", headers=owner, json={**body, "aside": True})
        assert opened.status_code == 200, opened.text
        assert opened.json()["flow"] == "myproject/flow-2"
