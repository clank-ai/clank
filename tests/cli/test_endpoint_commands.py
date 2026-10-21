"""Design 0016 §4 and §16: `clank endpoint`, the cloud provider's commands, each a client of the service saying what
the service says. `add` asks the agreement (the guide's words), or takes `--agree` from a script; `key` reads the key
without echo, or one line of standard input with `--stdin` (refused at a terminal, which would echo it), sends it once
and prints only its last four, and no option
of any command takes a key; a refused key says why and exits 1; `list`, `show` and `models` print the service's views;
`preset` writes a cloud preset and tests it; `check` prints each item; `remove` in use names what uses it."""

import json

import pytest
from click.testing import CliRunner, Result

from clank.cli.main import main
from clank.components.runtime import cloudcli
from clank.components.runtime.cloudcli import endpoint
from tests.fakes.openrouter import KEY
from tests.support.cloud import CloudBench


def run(*arguments: str, given: str | None = None) -> Result:
    return CliRunner().invoke(main, ["endpoint", *arguments], input=given)


def test_add_asks_the_agreement_in_the_services_words_and_n_adds_nothing(cloud_api: CloudBench) -> None:
    refused = run("add", "openrouter", given="n\n")
    assert refused.exit_code == 1
    assert "What never goes: Notion pages" in refused.output
    assert "Clank asks only for providers that do not keep your data (data_collection deny)." in refused.output
    assert cloud_api.endpoint is None
    added = run("add", "openrouter", given="y\n")
    assert added.exit_code == 0, added.output
    assert "Added OpenRouter (openrouter), agreed. Next: clank endpoint key openrouter" in added.output
    assert cloud_api.endpoint is not None


def test_add_with_agree_asks_nothing(cloud_api: CloudBench) -> None:
    added = run("add", "openrouter", "--agree", "--json")
    assert added.exit_code == 0, added.output
    assert json.loads(added.output)["agreed"]


def test_key_with_stdin_sends_the_line_and_prints_only_its_last_four(cloud_api: CloudBench) -> None:
    cloud_api.add(key=False)
    taken = run("key", "openrouter", "--stdin", given=f"{KEY}\n")
    assert taken.exit_code == 0, taken.output
    assert "OpenRouter took the key; Clank keeps it (ends …-key)." in taken.output
    assert 'key "made-up key label" (ends …-key): its own limit $20.00, $18.71 left' in taken.output
    assert KEY not in taken.output
    assert KEY[:-4] not in taken.output
    assert cloud_api.key() == KEY


def test_key_asked_without_echo_never_prints_it(cloud_api: CloudBench) -> None:
    cloud_api.add(key=False)
    taken = run("key", "openrouter", given=f"{KEY}\n")
    assert taken.exit_code == 0, taken.output
    assert KEY[:-4] not in taken.output, "the prompt does not echo it"
    assert cloud_api.key() == KEY


def test_no_option_of_any_command_takes_a_key() -> None:
    for command in endpoint.commands.values():
        names = {name for param in command.params for name in param.opts}
        assert not any("key" in name and name != "key" for name in names if name.startswith("-")), command.name
    key_params = [param.name for param in endpoint.commands["key"].params]
    assert key_params == ["provider", "from_stdin", "as_json"], "the provider, --stdin and --json: never the key"


def test_a_refused_key_says_why_and_exits_one(cloud_api: CloudBench) -> None:
    cloud_api.add(key=False)
    refused = run("key", "openrouter", "--stdin", given="made-up-wrong-key\n")
    assert refused.exit_code == 1
    assert "OpenRouter refused the key" in refused.output
    assert "made-up-wrong" not in refused.output
    assert cloud_api.key() is None


def test_list_show_and_models_print_the_services_views(cloud_api: CloudBench) -> None:
    cloud_api.add()
    cloud_api.write_preset()
    listed = run("list")
    assert "openrouter  OpenRouter  agreed" in listed.output
    assert "key ends …-key  presets: cloud-example-coder" in listed.output
    shown = run("show", "openrouter")
    assert shown.exit_code == 0, shown.output
    assert "Clank asks only for providers that do not keep your data" in shown.output
    assert 'account  key "made-up key label"' in shown.output
    models = run("models", "openrouter", "--sort", "price")
    assert models.output.splitlines()[0] == "2 that take tool calls, cheapest first. Prices per million tokens."
    assert (
        "Example Coder  example-vendor/example-coder\n    262K window · $0.30 in, $1.20 out · thinks" in models.output
    )
    assert "Example Chat" not in models.output
    assert "Example Chat" in run("models", "openrouter", "--all").output


def test_preset_writes_a_cloud_preset_and_tests_it(cloud_api: CloudBench) -> None:
    cloud_api.add()
    written = run("preset", "openrouter", "example-vendor/example-coder", "--context", "131072")
    assert written.exit_code == 0, written.output
    assert "Wrote cloud: Example Coder (cloud-example-coder): cloud openrouter · example-vendor/example-coder" in (
        written.output
    )
    assert "Its test: OK in " in written.output
    assert written.output.rstrip().endswith(", $0.000021")
    assert cloud_api.presets["cloud-example-coder"]["options"]["context"] == 131072
    refused = run("preset", "openrouter", "example-vendor/example-small:free", "--context", "999999999")
    assert refused.exit_code == 1
    assert "context is at most 32,768 for example-vendor/example-small:free, not 999,999,999" in refused.output


def test_check_prints_each_item(cloud_api: CloudBench) -> None:
    cloud_api.add()
    checked = run("check", "openrouter")
    assert checked.exit_code == 0, checked.output
    assert "  warn  limits    no daily or monthly limit in Clank" in checked.output


def test_remove_in_use_names_what_uses_it(cloud_api: CloudBench) -> None:
    cloud_api.add()
    cloud_api.write_preset()
    refused = run("remove", "openrouter")
    assert refused.exit_code == 1
    assert "openrouter is in use: the preset cloud-example-coder names it" in refused.output
    (cloud_api.kernel.home.config / "presets" / "cloud-example-coder.json").unlink()
    cloud_api.kernel.settings.reload_changed()
    assert run("remove", "openrouter").output.strip() == "Removed openrouter, with its key"


def test_stdin_at_a_terminal_is_refused_since_the_terminal_would_echo_the_key(
    cloud_api: CloudBench, monkeypatch: pytest.MonkeyPatch
) -> None:
    cloud_api.add(key=False)
    monkeypatch.setattr(cloudcli, "at_terminal", lambda: True)
    refused = run("key", "openrouter", "--stdin", given=f"{KEY}\n")
    assert refused.exit_code == 2
    assert "--stdin reads a key piped in" in refused.output
    assert cloud_api.key() is None


def test_a_cloud_preset_says_its_provider_where_an_engine_would_be(cloud_api: CloudBench) -> None:
    cloud_api.add()
    cloud_api.write_preset()
    listed = CliRunner().invoke(main, ["preset", "list"])
    line = next(each for each in listed.output.splitlines() if each.startswith("cloud: Example Coder"))
    assert "cloud openrouter" in line
    assert "example-vendor/example-coder" in line
    shown = CliRunner().invoke(main, ["preset", "show", "cloud-example-coder"])
    assert shown.exit_code == 0, shown.output
    assert "  provider       cloud openrouter: $0.30 in, $1.20 out per million tokens" in shown.output
    assert "serving setup" not in shown.output
