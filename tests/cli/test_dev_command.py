"""Design 0016 §16 (decision 0149): `clank dev` says whether dev mode is on in the service's words, and `clank dev on`
or `off` turns it so, recorded as the command's; `--json` prints the service's answer."""

import json

from click.testing import CliRunner

from clank.cli.main import main
from tests.support.cloud import CloudBench


def test_dev_says_whether_it_is_on_and_on_or_off_turns_it_so(cloud_api: CloudBench) -> None:
    runtime = cloud_api.kernel.parts["runtime"]
    shown = CliRunner().invoke(main, ["dev"])
    assert shown.exit_code == 0, shown.output
    assert shown.output.startswith("Dev mode is off: each cloud provider is asked as its record says")
    on = CliRunner().invoke(main, ["dev", "on"])
    assert on.exit_code == 0, on.output
    assert on.output.startswith("Dev mode is on: Clank asks every cloud provider for any of a model's providers")
    assert runtime.settings().dev_mode is True
    assert ("PUT", "runtime/dev", {"on": True}) in cloud_api.calls
    [changed] = [event for event in cloud_api.kernel.events.latest(types=["settings.changed"])
                 if event.data["kind"] == "runtime"]  # fmt: skip
    assert changed.actor.via == "cli"
    off = CliRunner().invoke(main, ["dev", "off", "--json"])
    assert off.exit_code == 0, off.output
    assert json.loads(off.output)["on"] is False
    assert runtime.settings().dev_mode is False
