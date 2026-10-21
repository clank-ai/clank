"""Installing an engine on a host by its recipe (design 0003 §7.1, design 0001 §7.4, decision 0032): the operation
`runtime.install`, under the lock `install:<setup>@<version>@<host>`, so a second install of the same engine there is
refused as busy while the first runs.

- plan: the recipe for the setup's version (`recipes.py`), the host, and the engine's folder there
  (`<Clank folder>/engines/<setup>/<version>`). The install is asked first (unless it was asked for with `yes`), with
  what it fetches, each step's command, and that nothing is installed with root or written outside that folder; any
  answer but "install" leaves nothing done.
- run: each step, in the engine's folder. A step whose result (`makes`) is already there is skipped, and said; any
  other runs with each line of its output in the operation's log. A step that fails stops the install with its exit
  status and its last lines that say what went wrong, and the next install goes on from that step. Canceling the
  install ends the step's command with every process it started.
- verify: the program the recipe made answers `--help`, listing every flag the engine's adapter can give it, so what
  was built is the version Clank knows.
- record: the install, how "recipe", with the recipe's deviations from the engine's own release as its detail.

An engine already built is adopted where it is (`runtime.adopt`, the same lock): nothing is fetched, built or moved.
- check: its program is there; its `--help` lists every flag the adapter can give; and the checkout it was built from
  (its folder, unless another is named) is at the commit the adapter's version names. Another commit, or a missing
  flag, is refused saying what differs; local changes in the checkout are said.
- record: the install, how "adopted", with the commit and the local changes as its detail.

An engine comes off a host again by `runtime.uninstall` (design 0003 §7.4, the same lock): one Clank built by its recipe
is deleted with its folder (`<Clank folder>/engines/<setup>/<version>`, and the folders that leaves empty) after a
question that says the folder, what it frees and how to build it again; one adopted where it was, a test's, or one whose
folder is anywhere else is only forgotten, its folder kept, with no question. An engine a slot on the host runs (or one
whose preset is gone, so nothing says what it runs) is refused: unload it first. Nothing outside the host's engines
folder is ever deleted: the host's own script refuses any other path.
"""

import collections
import re
import shlex
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.adapters.engine import EngineAdapter, flags
from clank.components.runtime.catalog import size_text
from clank.components.runtime.hosts.host import EngineHost
from clank.components.runtime.launching import clank_folder, running_on
from clank.components.runtime.recipes import Recipe, RecipeStep, fill
from clank.components.runtime.state import InstallRecord
from clank.kernel.adapters import AdapterError
from clank.kernel.operations import Canceled, OperationContext, OperationType, StepSpec
from clank.kernel.questions import Option, QuestionDraft

if TYPE_CHECKING:
    from clank.components.runtime.service import Runtime

QUESTION_MINUTES = 30
KEPT_LINES = 40
TROUBLE = re.compile(r"error|failed|fatal|cannot|not found|no such|denied|out of", re.IGNORECASE)
COMMIT = re.compile(r"[0-9a-f]{40}")
Planned = tuple[RecipeStep, list[str], dict[str, str]]
TREE = """\
import os, shutil, stat, sys
mode, stop, folder = sys.argv[1], os.path.normpath(sys.argv[2]), os.path.normpath(sys.argv[3])
if not folder.startswith(stop + os.sep):
    print(f'refused: {folder} is not in {stop}', flush=True)
    sys.exit(2)
size = 0
for place, folders, names in os.walk(folder):
    for name in names:
        try:
            size += os.lstat(os.path.join(place, name)).st_size
            if mode == 'remove' and os.name == 'nt':
                os.chmod(os.path.join(place, name), stat.S_IWRITE)
        except OSError:
            pass
if mode == 'remove' and os.path.isdir(folder):
    shutil.rmtree(folder)
    parent = os.path.dirname(folder)
    while parent.startswith(stop + os.sep) and os.path.isdir(parent) and not os.listdir(parent):
        os.rmdir(parent)
        parent = os.path.dirname(parent)
print(f'size {size}', flush=True)
"""


class InstallError(Exception):
    """An install that cannot go on, and why."""


def install_lock(params: Mapping[str, Any]) -> list[str]:
    """The lock of the engine an install puts on a host."""
    return [f"install:{params.get('setup')}@{params.get('version')}@{params.get('host')}"]


def operation_types(runtime: "Runtime") -> list[OperationType]:
    """Installing an engine by its recipe, adopting one already built, and removing one."""
    installs = Installs(runtime)
    steps = (StepSpec("plan"), StepSpec("run"), StepSpec("verify"), StepSpec("record"))
    return [
        OperationType(
            "runtime.install", "Install an engine", steps, installs.install, locks=install_lock, owner="runtime"
        ),
        OperationType(
            "runtime.adopt",
            "Adopt an engine already built",
            (StepSpec("check"), StepSpec("record")),
            installs.adopt,
            locks=install_lock,
            owner="runtime",
        ),
        OperationType(
            "runtime.uninstall",
            "Remove an engine",
            (StepSpec("plan"), StepSpec("remove")),
            installs.uninstall,
            locks=install_lock,
            owner="runtime",
        ),
    ]


class Installs:
    """What an install does."""

    def __init__(self, runtime: "Runtime") -> None:
        self.runtime = runtime

    async def install(self, context: OperationContext) -> dict[str, Any]:
        """Plan (and ask), run each step, verify the program, record the install."""
        setup, version, host_name = (str(context.params[key]) for key in ("setup", "version", "host"))
        async with context.step("plan"):
            recipe = self._recipe(setup, version)
            engine = ENGINES.get(setup)(version)
            title = f"{engine.LABEL} {version}"
            host = self.runtime.host(host_name)
            folder = await context.run_blocking(
                host.expand, f"{clank_folder(self.runtime, host_name)}/engines/{setup}/{version}"
            )
            common = {name: fill(value, folder) for name, value in recipe.env.items()}
            steps: list[Planned] = [
                (
                    step,
                    [fill(part, folder) for part in step.run],
                    {**common, **{name: fill(value, folder) for name, value in step.env.items()}},
                )
                for step in recipe.steps
            ]
            context.log(f"{title} into {folder} on {host_name}, in {len(steps)} steps")
            if not context.params.get("yes"):
                await self._ask(context, recipe, title, host_name, folder, steps)
        async with context.step("run"):
            for step, argv, env in steps:
                await self._run(context, host, folder, step, argv, env)
        program = [_placed(host, part, folder) for part in recipe.program]
        async with context.step("verify"):
            await self._verify(context, host, engine, title, program, (common, folder))
        async with context.step("record"):
            record = InstallRecord(
                setup=setup,
                version=version,
                host=host_name,
                program=program,
                folder=folder,
                library_path=":".join(_placed(host, part, folder) for part in recipe.library_path),
                how="recipe",
                detail=f"deviations: {'; '.join(recipe.deviations)}" if recipe.deviations else "",
            )
            installed = self.runtime.state.add_install(record, self.runtime.state.now())
            context.log(f"installed: {installed.title}")
        return {"install": installed.id, "title": title, "host": host_name, "folder": folder, "program": program}

    async def adopt(self, context: OperationContext) -> dict[str, Any]:
        """Check the program, its flags and the commit it was built from; record it where it is."""
        setup, version, host_name = (str(context.params[key]) for key in ("setup", "version", "host"))
        given = [str(part) for part in context.params["program"]]
        async with context.step("check"):
            engine = ENGINES.get(setup)(version)
            title = f"{engine.LABEL} {version}"
            host = self.runtime.host(host_name)
            program = [await context.run_blocking(host.expand, given[0]), *given[1:]]
            folder = await context.run_blocking(host.expand, str(context.params["folder"]))
            source = await context.run_blocking(host.expand, str(context.params.get("source") or folder))
            library_path = ":".join(
                [
                    await context.run_blocking(host.expand, part)
                    for part in str(context.params.get("library_path") or "").split(":")
                    if part
                ]
            )
            if not await context.run_blocking(host.exists, program[0]):
                raise InstallError(f"{program[0]} is not on {host_name}")
            await self._verify(context, host, engine, title, program)
            detail = await self._built_from(context, host, engine, title, source)
        async with context.step("record"):
            record = InstallRecord(
                setup=setup,
                version=version,
                host=host_name,
                program=program,
                folder=folder,
                library_path=library_path,
                how="adopted",
                detail=detail,
            )
            installed = self.runtime.state.add_install(record, self.runtime.state.now())
            context.log(f"adopted where it is: {installed.title}")
        return {"install": installed.id, "title": title, "host": host_name, "folder": folder, "program": program}

    async def _built_from(
        self, context: OperationContext, host: EngineHost, engine: EngineAdapter, title: str, source: str
    ) -> str:
        """The checkout's commit, which must be the one the adapter's version names; its local changes, said."""
        wanted = engine.version.source.removeprefix("commit ")
        if not COMMIT.fullmatch(wanted):
            context.log(f"{title}'s adapter names no commit to check the build against")
            return f"adopted from {source}"
        answer = await context.run_blocking(host.output, ["git", "-C", source, "rev-parse", "HEAD"])
        head = (answer or "").strip()
        if not COMMIT.fullmatch(head):
            said = head.splitlines()[0] if head else "git did not answer"
            raise InstallError(
                f"cannot tell which commit it was built from: {source} is not a git checkout ({said}); name its source,"
                " the checkout it was built from"
            )
        if head != wanted:
            raise InstallError(
                f"{source} is at commit {head[:7]}, not {wanted[:7]}, the commit of {title}: build that commit, or "
                "adopt it as the version it is"
            )
        detail = f"built from {wanted[:7]}, the commit of {title}"
        context.log(detail)
        status = await context.run_blocking(host.output, ["git", "-C", source, "status", "--porcelain"])
        changed = [line[3:].strip() for line in (status or "").splitlines() if line.strip()]
        if changed:
            detail += f"; with local changes in {', '.join(changed)}"
            context.log(f"its checkout has local changes in {', '.join(changed)}")
        return detail

    async def uninstall(self, context: OperationContext) -> dict[str, Any]:
        """Plan (and ask, when a folder is to be deleted), then delete Clank's build, or forget one it did not make."""
        setup, version, host_name = (str(context.params[key]) for key in ("setup", "version", "host"))
        async with context.step("plan"):
            title = f"{_label(setup)} {version}"
            host = self.runtime.host(host_name)
            install = self.runtime.state.install(setup, version, host_name)
            if install is None:
                raise InstallError(f"{title} is not installed on {host_name}")
            for slot, running, preset in running_on(self.runtime, host_name):
                if preset is None or (preset.engine, preset.engine_version) == (setup, version):
                    raise InstallError(
                        f"{slot} runs {running} on {host_name}: unload it first (`clank model unload --slot {slot}`)"
                    )
            engines = await context.run_blocking(host.expand, f"{clank_folder(self.runtime, host_name)}/engines")
            folder = await context.run_blocking(host.expand, f"{engines}/{setup}/{version}")
            ours = install.how == "recipe" and install.folder.rstrip("/\\") == folder.rstrip("/\\")
            if ours:
                answer = await context.run_blocking(host.output, [host.PYTHON, "-c", TREE, "size", engines, folder])
                size = _said_size((answer or "").splitlines())
                context.log(f"{folder} holds {size_text(size)}")
                if not context.params.get("yes"):
                    await self._ask_uninstall(context, title, (setup, version, host_name), folder, size)
            else:
                why = {"adopted": "was adopted where it was", "test": "is a test's"}.get(
                    install.how, f"is in {install.folder}, not in {host_name}'s engines folder"
                )
                context.log(f"{title} on {host_name} {why}: Clank forgets it, and its folder stays where it is")
        async with context.step("remove"):
            freed = 0
            if ours:
                lines: list[str] = []

                def heard(text: str) -> None:
                    lines.append(text)
                    context.log(text)

                argv = [host.PYTHON, "-c", TREE, "remove", engines, folder]
                status = await context.run_blocking(host.run_step, argv, {}, engines, heard, lambda: False)
                if status != 0:
                    raise InstallError(f"could not remove {folder} on {host_name}: {reading(lines[-5:])}")
                freed = _said_size(lines)
            self.runtime.state.remove_install(setup, version, host_name)
            context.log(f"{title} is no longer installed on {host_name}")
        return {
            "install": install.id,
            "title": title,
            "host": host_name,
            "folder": install.folder,
            "freed": freed,
            "kept": not ours,
        }

    async def _ask_uninstall(
        self, context: OperationContext, title: str, where: tuple[str, str, str], folder: str, size: int
    ) -> None:
        """Ask whether to remove an engine Clank built; any answer but "remove" cancels it with nothing removed."""
        setup, version, host_name = where
        again = (
            f"`clank engine install {setup} --version {version} --host {host_name}` builds it again by Clank's recipe."
            if (setup, version) in self.runtime.recipes
            else "Clank has no recipe for it now, so Clank cannot build it again."
        )
        lines = [
            f"Its folder {folder} ({size_text(size)}) is deleted, with everything in it.",
            "Every preset that uses it stays, and starts again once it is installed again.",
            again,
        ]
        draft = QuestionDraft(
            type="approval",
            title=f"Remove {title} from {host_name}?",
            detail="\n".join(lines),
            options=[
                Option(id="remove", label="Remove it", key="y", effect=f"frees {size_text(size)}"),
                Option(id="cancel", label="Not now", key="n", effect="nothing is removed"),
            ],
            default="cancel",
            expires=self.runtime.state.now() + timedelta(minutes=QUESTION_MINUTES),
        )
        answer = await context.ask(draft)
        if answer.option != "remove":
            raise Canceled(f"not removed: {answer.by.describe()} chose not to")

    def _recipe(self, setup: str, version: str) -> Recipe:
        found = self.runtime.recipes.get((setup, version))
        if found is None:
            known = ", ".join(f"{name} {at}" for name, at in sorted(self.runtime.recipes)) or "none"
            raise InstallError(f"Clank has no recipe for {setup} {version}; it has recipes for: {known}")
        return found

    async def _ask(
        self,
        context: OperationContext,
        recipe: Recipe,
        title: str,
        host_name: str,
        folder: str,
        steps: Sequence[Planned],
    ) -> None:
        """Ask whether to install; any answer but "install" cancels it with nothing done."""
        lines = [
            recipe.summary,
            f"It fetches {recipe.download}.",
            f"Everything goes into {folder} on {host_name}: nothing is installed with root, and nothing is written "
            "outside that folder.",
            *(f"{step.name}: {_shown(argv)}" for step, argv, _ in steps),
        ]
        if recipe.deviations:
            lines.append(f"Deviations from the engine's own release: {'; '.join(recipe.deviations)}")
        draft = QuestionDraft(
            type="approval",
            title=f"Install {title} on {host_name}?",
            detail="\n".join(lines),
            options=[
                Option(id="install", label="Install it", key="y", effect=f"fetches and builds {title} on {host_name}"),
                Option(id="cancel", label="Not now", key="n", effect="nothing is fetched or built"),
            ],
            default="cancel",
            expires=self.runtime.state.now() + timedelta(minutes=QUESTION_MINUTES),
        )
        answer = await context.ask(draft)
        if answer.option != "install":
            raise Canceled(f"not installed: {answer.by.describe()} chose not to")

    async def _run(
        self,
        context: OperationContext,
        host: EngineHost,
        folder: str,
        step: RecipeStep,
        argv: list[str],
        env: dict[str, str],
    ) -> None:
        """One step: skipped when what it makes is there, else run with its output in the log."""
        made = bool(step.makes) and await context.run_blocking(host.exists, f"{folder}/{step.makes}")
        if made:
            context.log(f"{step.name}: already made ({step.makes})")
            return
        context.log(f"== {step.name}")
        context.log(f"$ {_shown(argv)}")
        kept: collections.deque[str] = collections.deque(maxlen=KEPT_LINES)

        def heard(text: str) -> None:
            kept.append(text)
            context.log(text)

        status = await context.run_blocking(host.run_step, argv, env, folder, heard, lambda: canceled(context))
        context.check_canceled()
        if status != 0:
            raise InstallError(f"{step.name} failed (exit {status}): {reading(list(kept))}")

    async def _verify(
        self,
        context: OperationContext,
        host: EngineHost,
        engine: EngineAdapter,
        title: str,
        program: list[str],
        within: tuple[dict[str, str], str] | None = None,
    ) -> None:
        """The program answers --help with every flag the adapter can give it; run as a step, `within` a recipe's
        environment and its engine's folder, for a program an install made."""
        wanted = sorted({flag for option in engine.options() for flag in flags(option)})
        text: str | None
        if within is None:
            text = await context.run_blocking(host.output, [*program, "--help"])
        else:
            heard: list[str] = []
            env, folder = within
            argv = [*program, "--help"]
            await context.run_blocking(host.run_step, argv, env, folder, heard.append, lambda: False)
            text = "\n".join(heard) or None
        if text is None:
            raise InstallError(f"{program[0]} does not run: the install made no program that answers --help")
        missing = [flag for flag in wanted if re.search(re.escape(flag) + r"(?![\w-])", text) is None]
        if missing:
            raise InstallError(
                f"its --help does not list {', '.join(missing)}: what was installed is not {title} as Clank knows it"
            )
        context.log(f"its --help lists all {len(wanted)} flags Clank can give {title}")


def _placed(host: EngineHost, part: str, folder: str) -> str:
    """A recipe's path in the engine's folder, as the host writes paths; any other part as it is."""
    return host.expand(fill(part, folder)) if "{folder}" in part else part


def _shown(argv: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in argv)


def canceled(context: OperationContext) -> bool:
    """Whether the user canceled the operation (for a check that must not raise)."""
    try:
        context.check_canceled()
    except Canceled:
        return True
    return False


def reading(lines: list[str]) -> str:
    """The step's own words for what went wrong: its last lines that say so, else its last lines."""
    trouble = [line.strip() for line in lines if TROUBLE.search(line)]
    chosen = trouble[-3:] if trouble else [line.strip() for line in lines[-3:] if line.strip()]
    return " / ".join(chosen) if chosen else "it wrote nothing"


def _label(setup: str) -> str:
    """A serving setup's name as people know it, or its id when Clank no longer has its adapter."""
    try:
        return ENGINES.get(setup).LABEL
    except AdapterError:
        return setup


def _said_size(lines: Sequence[str]) -> int:
    """The size the tree script said last, in bytes; 0 when it said none."""
    said = [line.split()[1] for line in lines if line.startswith("size ") and line.split()[1].isdigit()]
    return int(said[-1]) if said else 0
