"""Design 0016 §14 and §16: `clank model add` is the console's Add a model in the terminal, in its order and the
service's words: the whole pass with its answers on standard input writes the provider's record once agreed, keeps the
key (read without echo, never printed), writes the preset from the model picked with the settings as the service fills
them, and loads it into the empty main slot, saying its answer and cost; a refused key is said and asked again, and so
is a mistyped limit, the preset already written then taken as it is, as a second pass takes it; Local lists the main
slot's presets and says what to do when a step cannot be done from here. Design 0028 §4: `--cloud` and `--local` skip
the choice, for `clank setup`'s model step, which asks it once."""

from click.testing import CliRunner, Result

from clank.cli.main import main
from tests.fakes.openrouter import KEY
from tests.support.cloud import CloudBench

KEEP_SETTINGS = "\n" * 6  # each of the model's settings kept as the service filled it


def run(given: str, *arguments: str) -> Result:
    return CliRunner().invoke(main, ["model", "add", *arguments], input=given)


def test_the_whole_pass_on_standard_input_agrees_keeps_the_key_writes_the_preset_and_loads_it(
    cloud_api: CloudBench,
) -> None:
    done = run("c\ny\ny\n" + f"{KEY}\n" + "1\n" + KEEP_SETTINGS)
    assert done.exit_code == 0, done.output
    assert "What never goes: Notion pages" in done.output
    assert cloud_api.endpoint is not None
    assert cloud_api.endpoint["options"]["data_collection"] == "deny"
    assert cloud_api.key() == KEY
    assert KEY[:-4] not in done.output, "the key is never printed"
    assert "OpenRouter took the key; Clank keeps it (ends …-key)." in done.output
    assert "Wrote cloud: Example Coder (cloud-example-coder)." in done.output
    assert "cloud: Example Coder runs in the main slot. Its test: it answered a tiny request: OK in " in done.output
    main = cloud_api.kernel.parts["runtime"].state.slot("main")
    assert (main.status, main.preset) == ("ready", "cloud-example-coder")


def test_cloud_and_local_skip_the_choice(cloud_api: CloudBench) -> None:
    cloud_api.add()
    done = run("1\n" + KEEP_SETTINGS, "--cloud")
    assert done.exit_code == 0, done.output
    assert "How should Clank run its model?" not in done.output, "the choice is skipped"
    assert "cloud: Example Coder runs in the main slot." in done.output
    local = run("1\n", "--local")
    assert "How should Clank run its model?" not in local.output
    assert "daily 262K" in local.output


def test_a_refused_key_is_said_and_asked_again(cloud_api: CloudBench) -> None:
    cloud_api.add(key=False)
    done = run("c\n" + "made-up-wrong-key\n" + f"{KEY}\n" + "2\n" + KEEP_SETTINGS)
    assert done.exit_code == 0, done.output
    assert "OpenRouter refused the key" in done.output
    assert "The field is cleared: paste the key again." in done.output
    assert "cloud: Example Small (free) runs in the main slot." in done.output


def test_with_a_local_model_running_it_tests_then_asks_and_no_keeps_it(cloud_api: CloudBench) -> None:
    cloud_api.add()
    cloud_api.run("daily-262k")
    done = run("c\n1\n" + KEEP_SETTINGS + "n\n")
    assert done.exit_code == 0, done.output
    assert "It answered: OK in " in done.output
    assert "Load it now? This stops daily 262K in the main slot" in done.output
    assert "daily 262K keeps the main slot" in done.output
    assert cloud_api.kernel.parts["runtime"].state.slot("main").preset == "daily-262k"


def test_local_lists_the_presets_and_says_what_to_do_when_a_step_cannot_be_done(cloud_api: CloudBench) -> None:
    done = run("l\n1\n")
    assert "daily 262K" in done.output
    assert done.exit_code == 1
    assert "build it, then adopt it where it is (clank engine adopt); or choose Cloud" in done.output


def test_a_mistyped_limit_is_asked_again_and_the_preset_already_written_is_taken(cloud_api: CloudBench) -> None:
    cloud_api.add()
    four_settings = "\n" * 4  # title, context, output and thinking kept
    done = run("c\n1\n" + four_settings + "five\n\n" + four_settings + "5\n\n")
    assert done.exit_code == 0, done.output
    assert "five is not an amount: type US dollars, such as 5 or 12.50, or none" in done.output
    assert cloud_api.limits["day_usd"] == 5.0
    assert list(cloud_api.presets) == ["cloud-example-coder"]
    assert "cloud: Example Coder runs in the main slot" in done.output


def test_a_rerun_after_a_preset_was_written_takes_it_and_goes_on(cloud_api: CloudBench) -> None:
    cloud_api.add()
    cloud_api.write_preset()
    done = run("c\n1\n" + KEEP_SETTINGS)
    assert done.exit_code == 0, done.output
    assert "Took cloud: Example Coder (cloud-example-coder), written before." in done.output
    assert cloud_api.kernel.parts["runtime"].state.slot("main").preset == "cloud-example-coder"
