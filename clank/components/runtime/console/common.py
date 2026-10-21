"""What the runtime's pages share: a preset's fit as a few words, its last start, and a preset's check in a window (its
items read off the screen's thread). The presets to pick from are `clank.console.pick.preset_choices`."""

from typing import Any
from urllib.parse import quote

from clank.console.details import DetailsScreen
from clank.console.pages import Page
from clank.console.text import time_of

MARKS = {"passed": "ok  ", "failed": "FAIL", "unknown": "?   "}


def fit_text(preset: dict[str, Any], plan: dict[str, Any] | None) -> str:
    """Whether a preset fits in the GPU's memory now, or why it cannot run."""
    if preset["problems"]:
        return f"cannot run: {'; '.join(preset['problems'])}"
    if plan is None:
        return "fit: being read"
    if plan["problem"]:
        return f"cannot run: {plan['problem']}"
    verdict, spare = plan["fit"]["verdict"], plan["fit"]["spare_mib"]
    if verdict == "unknown":
        return "fit unknown: the GPU's memory cannot be read"
    if verdict == "on the CPU":
        return "on the CPU: none of the GPU's memory"
    if verdict == "does not fit":
        return f"does not fit, {-spare:,} MiB short"
    return f"{verdict}, {spare:,} MiB to spare"


def last_start(preset: str, launches: list[dict[str, Any]], zone: Any) -> str:
    """When the preset last started, and how it went; empty when it never did."""
    launch = next((each for each in launches if each["preset"] == preset), None)
    if launch is None:
        return ""
    how = f"ready in {launch['seconds']:.0f} s" if launch["seconds"] is not None else launch["outcome"]
    if launch["measured_mib"] is not None:
        how += f", {launch['measured_mib']:,} MiB"
    if launch["outcome"] == "failed":
        how = "failed"
    return f"last started {time_of(launch['started_at'], zone)}, {how}"


def show_check(page: Page, preset: str, title: str) -> None:
    """Check a preset (it starts nothing) and show each item in a window; a refusal on the message line."""
    console = page.console
    client = console.client

    def work() -> None:
        try:
            items = client.post(f"runtime/presets/{quote(preset, safe='')}/check")
        except Exception as error:
            console.call_from_thread(console.say, str(error), True)
            return
        lines = [f"{MARKS[item['status']]}  {item['name']:<9}  {item['detail']}" for item in items]
        console.call_from_thread(console.push_screen, DetailsScreen(f"Check of {title}", lines))

    page.run_worker(work, thread=True, group="check", exit_on_error=False)
