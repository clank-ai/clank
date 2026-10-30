"""Design 0016 §16 and §7 (revised after approval 2026-10-29, the owner's request): `clank preset change PRESET
[--output N] [--context N] [--reasoning R] [--json]` changes a cloud preset's settings through the service, by its id or
its title, and prints the service's words: what changed, where it applies, and, while the main slot runs it, that
OpenCode windows open now keep the limits they started with until they start again; `--json` prints the service's
answer. A refusal is the service's own
words and exits 1, a local preset's saying where its options change; with no setting to change, it says what to give."""

import json

from click.testing import CliRunner, Result

from clank.cli.main import main
from tests.support.cloud import CloudBench

WINDOWS = (
    "OpenCode windows open now keep the limits they started with until they start again; the next one started gets "
    "these."
)


def run(*arguments: str) -> Result:
    return CliRunner().invoke(main, ["preset", "change", *arguments])


def written(cloud: CloudBench) -> None:
    cloud.add()
    cloud.write_preset(context=65536)


def test_change_raises_the_most_output_and_prints_the_services_words(cloud_api: CloudBench) -> None:
    written(cloud_api)
    cloud_api.run("cloud-example-coder")
    changed = run("cloud: Example Coder", "--output", "32768")
    assert changed.exit_code == 0, changed.output
    lines = changed.output.splitlines()
    assert lines[:3] == ["cloud: Example Coder: most output 32,768 tokens (was 16,384).",
                         "The main slot runs it and follows the change from the next request.", WINDOWS]  # fmt: skip
    assert cloud_api.presets["cloud-example-coder"]["options"]["max_output"] == 32768
    assert [body for method, _, body in cloud_api.calls if method == "PATCH"] == [{"max_output": 32768}]


def test_change_with_json_prints_the_services_answer(cloud_api: CloudBench) -> None:
    written(cloud_api)
    changed = run("cloud-example-coder", "--context", "131072", "--reasoning", "low", "--json")
    assert changed.exit_code == 0, changed.output
    found = json.loads(changed.output)
    assert (found["changed"], found["was"]) == (["context", "reasoning"], {"context": 65536, "reasoning": "default"})
    assert found["preset"]["options"]["context"] == 131072


def test_a_refusal_is_the_services_words_and_exits_1(cloud_api: CloudBench) -> None:
    written(cloud_api)
    beyond = run("cloud-example-coder", "--output", "99999")
    assert beyond.exit_code == 1
    assert "max_output is at most 32,768 for example-vendor/example-coder, not 99,999" in beyond.output
    local = run("daily 262K", "--output", "8192")
    assert local.exit_code == 1
    assert "daily 262K is a local preset: its options are in its file" in local.output
    assert "o on Presets, then e on Launch options" in local.output


def test_with_nothing_to_change_it_says_what_to_give(cloud_api: CloudBench) -> None:
    written(cloud_api)
    nothing = run("cloud-example-coder")
    assert nothing.exit_code == 2
    assert "give --output, --context or --reasoning" in nothing.output
    assert not [call for call in cloud_api.calls if call[0] == "PATCH"]
