"""A model's files on a host (design 0003 §7.2 and §7.4, design 0001 §7.5): downloading one of the catalog's files,
adopting one the user already has, and removing them again.

- `runtime.download`, under the lock `model:<model>@<host>`: plan (the catalog's file for a format and role, refused
  when its revision is no longer known; where it goes, the host's models folder laid out as
  `<repository>/<revision>/<file>`; what is already there; the host's free disk; asked first unless told `yes`), fetch
  (by the host's own Python, so the file goes straight to the host's disk, into `<file>.part`, resuming from what the
  `.part` has, its progress in the log every few seconds, at most `limit` MB/s when one is given) and verify (its
  SHA-256 must be the catalog's: then it becomes the file, else it is kept aside as `<file>.bad`, refused, and never
  used). A file already there at its name was verified when it got that name, and is not fetched again.
- `runtime.verify`, the same lock: a file the user already has, anywhere on the host, is adopted where it is once its
  size and SHA-256 are the catalog's: a `model-file` record says where it is, and launches use it there.
- `runtime.remove`, the same lock: a model's files on a host (all of them, or those of one format or role) are taken
  off it. What Clank put in the host's models folder is deleted (the file, and a `.part` or `.bad` left of it), with
  the folders that leave empty, after a question that says each file, what it frees and how to bring it back; a file
  the user keeps elsewhere is only forgotten (its `model-file` record), never deleted, and needs no question. The
  catalog keeps the model and every preset stays, so `clank model download` brings each file back. A model that a
  slot on the host runs (or one whose preset is gone, so nothing says what it uses) is refused: unload it first.

The time a download will take is not guessed before it starts: its progress lines say the speed as it goes.
"""

from datetime import timedelta
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.catalog import ModelEntry, ModelFileEntry, size_text
from clank.components.runtime.hosts.host import EngineHost
from clank.components.runtime.installing import canceled, reading
from clank.components.runtime.kinds import ModelFile, Preset
from clank.components.runtime.launching import clank_folder, default_path, model_record, models, running_on
from clank.kernel.adapters import AdapterError
from clank.kernel.operations import Canceled, OperationContext, OperationType, StepSpec
from clank.kernel.questions import Option, QuestionDraft
from clank.kernel.settings import Loaded, SettingsError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from clank.components.runtime.service import Runtime

HUB_URL = "https://huggingface.co/{repository}/resolve/{revision}/{path}"
QUESTION_MINUTES = 30
DOWNLOAD = """\
import os, sys, time, urllib.request
url, part, size, limit = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
have = os.path.getsize(part) if os.path.exists(part) else 0
if have > size:
    os.remove(part)
    have = 0
def said(note=''):
    print(f'{have:,} of {size:,} bytes ({100 * have // size}%){note}', flush=True)
if have == size:
    said(', all of it fetched before')
    sys.exit(0)
headers = {'User-Agent': 'clank'}
if have:
    headers['Range'] = f'bytes={have}-'
    said(', going on from there')
try:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as answer:
        if have and answer.status != 206:
            have = 0
        with open(part, 'ab' if have else 'wb') as out:
            started = last = time.monotonic()
            got = 0
            while chunk := answer.read(1 << 20):
                out.write(chunk)
                have += len(chunk)
                got += len(chunk)
                now = time.monotonic()
                if now - last >= 5:
                    last = now
                    said(f', {got / max(now - started, 0.001) / 1e6:.0f} MB/s')
                if limit:
                    ahead = got / (limit * 1e6) - (time.monotonic() - started)
                    if ahead > 0:
                        time.sleep(ahead)
except Exception as error:
    print(f'stopped at {have:,} of {size:,} bytes: {error}', flush=True)
    sys.exit(1)
if have != size:
    print(f'stopped at {have:,} of {size:,} bytes: the server sent no more', flush=True)
    sys.exit(1)
said()
"""
FREE = """\
import os, shutil, sys
place = sys.argv[1]
while not os.path.exists(place) and os.path.dirname(place) != place:
    place = os.path.dirname(place)
print(shutil.disk_usage(place).free)
"""
MOVE = "import os, sys; os.replace(sys.argv[1], sys.argv[2])"
REMOVE = """import os, sys
stop = os.path.normpath(sys.argv[1])
freed = 0
for path in map(os.path.normpath, sys.argv[2:]):
    if not path.startswith(stop + os.sep):
        print(f'refused: {path} is not in {stop}', flush=True)
        sys.exit(2)
    if os.path.isfile(path):
        freed += os.path.getsize(path)
        os.remove(path)
        print(f'removed {path}', flush=True)
    folder = os.path.dirname(path)
    while folder.startswith(stop + os.sep) and os.path.isdir(folder) and not os.listdir(folder):
        os.rmdir(folder)
        folder = os.path.dirname(folder)
print(f'freed {freed}', flush=True)
"""


class ModelFileError(Exception):
    """A model file that cannot be fetched or adopted, and why."""


def model_lock(params: "Mapping[str, Any]") -> list[str]:
    """The lock of a model's files on a host."""
    return [f"model:{params.get('model')}@{params.get('host')}"]


def operation_types(runtime: "Runtime") -> list[OperationType]:
    """Downloading a model's file, adopting one the user has, and removing a model's files."""
    files = ModelFiles(runtime)
    return [
        OperationType(
            "runtime.download",
            "Download a model file",
            (StepSpec("plan"), StepSpec("fetch"), StepSpec("verify")),
            files.download,
            locks=model_lock,
            owner="runtime",
        ),
        OperationType(
            "runtime.verify",
            "Adopt a model file",
            (StepSpec("check"), StepSpec("record")),
            files.verify,
            locks=model_lock,
            owner="runtime",
        ),
        OperationType(
            "runtime.remove",
            "Remove a model's files",
            (StepSpec("plan"), StepSpec("remove")),
            files.remove,
            locks=model_lock,
            owner="runtime",
        ),
    ]


class ModelFiles:
    """What a download, an adoption and a removal do."""

    def __init__(self, runtime: "Runtime") -> None:
        self.runtime = runtime

    async def download(self, context: OperationContext) -> dict[str, Any]:
        """Plan (and ask), fetch into the `.part`, verify and keep it."""
        host_name = str(context.params["host"])
        async with context.step("plan"):
            model, file = self._file(context)
            if not file.revision:
                raise ModelFileError(
                    f"{file.path}: its revision is no longer known, so Clank does not download it; adopt the copy you"
                    f" have: `clank model adopt {model.id} --format {file.format} --role {file.role} --host {host_name}"
                    " --path PATH`"
                )
            host = self.runtime.host(host_name)
            target = await context.run_blocking(default_path, self.runtime, file, host_name, host)
            folder = target.replace("\\", "/").rpartition("/")[0]
            name = PurePosixPath(file.path).name
            there = await context.run_blocking(host.size, target)
            if there == file.size:
                context.log(f"{file.path} is already on {host_name} at {target}, verified when it was fetched")
                return {"model": model.id, "file": file.path, "host": host_name, "path": target, "fetched": False}
            if there is not None:
                raise ModelFileError(
                    f"another file is at {target} ({there:,} bytes, not the {file.size:,} of {file.path}): move it away"
                )
            have = await context.run_blocking(host.size, f"{target}.part") or 0
            answer = await context.run_blocking(host.output, [host.PYTHON, "-c", FREE, folder])
            free = int(answer.strip()) if answer and answer.strip().isdigit() else None
            if free is not None and free < file.size - have:
                raise ModelFileError(
                    f"{file.path} needs {size_text(file.size - have)} more on {host_name},"
                    f" which has {size_text(free)} free"
                )
            url = self.runtime.model_url.format(repository=file.repository, revision=file.revision, path=file.path)
            context.log(f"{file.path} ({size_text(file.size)}) from {url} into {target}")
            if not context.params.get("yes"):
                await self._ask(context, file, host_name, url, target, have, free)
        async with context.step("fetch"):
            limit = float(context.params.get("limit") or 0)
            argv = [host.PYTHON, "-c", DOWNLOAD, url, f"{name}.part", str(file.size), str(limit)]
            lines: list[str] = []

            def heard(text: str) -> None:
                lines.append(text)
                context.log(text)

            status = await context.run_blocking(host.run_step, argv, {}, folder, heard, lambda: canceled(context))
            context.check_canceled()
            if status != 0:
                raise ModelFileError(
                    f"the download of {file.path} {reading(lines[-5:])}; downloading it again goes on from what it has"
                )
        async with context.step("verify"):
            context.log("reading its SHA-256 (a minute or two for a large file)")
            digest = await context.run_blocking(host.sha256, f"{target}.part")
            if digest != file.sha256:
                await self._move(context, host, folder, f"{name}.part", f"{name}.bad")
                raise ModelFileError(
                    f"{file.path}'s SHA-256 is {(digest or 'unreadable')[:12]}…, not the catalog's {file.sha256[:12]}…:"
                    f" kept aside as {name}.bad, and nothing will use it"
                )
            await self._move(context, host, folder, f"{name}.part", name)
            context.log(f"verified: {file.path} is the catalog's (SHA-256 {file.sha256[:12]}…), at {target}")
        return {"model": model.id, "file": file.path, "host": host_name, "path": target, "fetched": True}

    async def verify(self, context: OperationContext) -> dict[str, Any]:
        """Check a file the user has against the catalog; record where it is."""
        host_name = str(context.params["host"])
        given = str(context.params["path"])
        async with context.step("check"):
            model, file = self._file(context)
            host = self.runtime.host(host_name)
            path = await context.run_blocking(host.expand, given)
            size = await context.run_blocking(host.size, path)
            if size is None:
                raise ModelFileError(f"{path} is not on {host_name}")
            if size != file.size:
                raise ModelFileError(f"{path} has {size:,} bytes, not the {file.size:,} of {file.path}")
            context.log("its size is the catalog's; reading its SHA-256 (a minute or two for a large file)")
            digest = await context.run_blocking(host.sha256, path)
            if digest != file.sha256:
                raise ModelFileError(
                    f"{path}'s SHA-256 is {(digest or 'unreadable')[:12]}…, not the catalog's {file.sha256[:12]}… for"
                    f" {file.path}"
                )
            context.log(f"verified: it is the catalog's {file.path} (SHA-256 {file.sha256[:12]}…)")
        async with context.step("record"):
            id = f"{model.id}-{file.format}-{file.role}-{host_name}"
            try:
                base: str | None = self.runtime.kernel.settings.get("model-file", id).revision
            except SettingsError:
                base = None
            values = {"model": model.id, "file": file.path, "host": host_name, "path": given}
            self.runtime.kernel.settings.write("model-file", id, values, base=base, actor=context.actor)
            context.log(f"recorded: launches on {host_name} use it at {path}")
        return {"model": model.id, "file": file.path, "host": host_name, "path": path}

    async def remove(self, context: OperationContext) -> dict[str, Any]:
        """Plan (and ask, when something is to be deleted), then delete Clank's copies and forget the user's."""
        host_name = str(context.params["host"])
        async with context.step("plan"):
            model, files = self._files(context)
            host = self.runtime.host(host_name)
            formats = {file.format for file in files}
            for slot, running, preset in running_on(self.runtime, host_name):
                reads = _reads(preset, model)
                if reads is None:
                    raise ModelFileError(
                        f"{slot} runs {running}, and nothing says what it uses: unload it first"
                        f" (`clank model unload --slot {slot}`)"
                    )
                if reads in formats:
                    raise ModelFileError(
                        f"{slot} runs {running}, which uses {model.name}'s {reads} files on {host_name}:"
                        f" unload it first (`clank model unload --slot {slot}`)"
                    )
            folder = await context.run_blocking(host.expand, f"{clank_folder(self.runtime, host_name)}/models")
            doomed: list[tuple[ModelFileEntry, str, int]] = []
            kept: list[tuple[Loaded, str]] = []
            for file in files:
                target = await context.run_blocking(default_path, self.runtime, file, host_name, host)
                for path in (target, f"{target}.part", f"{target}.bad"):
                    size = await context.run_blocking(host.size, path)
                    if size is not None:
                        doomed.append((file, path, size))
                record = model_record(self.runtime, model, file, host_name)
                if record is not None:
                    given = ModelFile.model_validate(record.record.model_dump()).path
                    kept.append((record, await context.run_blocking(host.expand, given)))
            removed = [path for _, path, _ in doomed]
            gone: list[ModelFileEntry] = []
            for file, _, _ in doomed:
                if file not in gone:
                    gone.append(file)
            result: dict[str, Any] = {
                "model": model.id,
                "name": model.name,
                "host": host_name,
                "removed": removed,
                "freed": sum(size for _, _, size in doomed),
                "forgotten": [where for _, where in kept if where not in removed],
                "restore": [_restore(model, file, host_name) for file in gone],
            }
            if not removed and not kept:
                context.log(f"nothing of {model.name} is on {host_name}")
                return result
            if removed and not context.params.get("yes"):
                await self._ask_remove(context, model, host_name, doomed, result)
        async with context.step("remove"):
            if removed:
                lines: list[str] = []

                def heard(text: str) -> None:
                    lines.append(text)
                    context.log(text)

                argv = [host.PYTHON, "-c", REMOVE, folder, *removed]
                status = await context.run_blocking(host.run_step, argv, {}, folder, heard, lambda: False)
                if status != 0:
                    raise ModelFileError(f"could not remove {model.name}'s files on {host_name}: {reading(lines[-5:])}")
                said = [line for line in lines if line.startswith("freed ")]
                if said:
                    result["freed"] = int(said[-1].split()[1])
            for record, where in kept:
                self.runtime.kernel.settings.delete("model-file", record.id, base=record.revision, actor=context.actor)
                context.log(f"forgot {where}: it is yours, and stays where it is")
        return result

    def _model(self, context: OperationContext) -> ModelEntry:
        """The catalog's model asked for."""
        model_id = str(context.params["model"])
        known = models(self.runtime)
        if model_id not in known:
            raise ModelFileError(f"the catalog has no model {model_id!r}; it has {', '.join(sorted(known)) or 'none'}")
        return known[model_id]

    def _files(self, context: OperationContext) -> tuple[ModelEntry, list[ModelFileEntry]]:
        """The catalog's model and its files: all of them, or those of the format and role asked for."""
        model = self._model(context)
        form, role = context.params.get("format"), context.params.get("role")
        files = [file for file in model.files if (not form or file.format == form) and (not role or file.role == role)]
        if not files:
            kind = " ".join(part for part in (form, role) if part)
            raise ModelFileError(f"{model.id} has no {kind} file")
        return model, files

    def _file(self, context: OperationContext) -> tuple[ModelEntry, ModelFileEntry]:
        """The catalog's model and its file for the format and role asked for."""
        model = self._model(context)
        form = str(context.params["format"])
        role = str(context.params.get("role") or "weights")
        file = model.file(form, role)
        if file is None:
            raise ModelFileError(f"{model.id} has no {role} file in the {form} format")
        return model, file

    async def _ask(
        self,
        context: OperationContext,
        file: ModelFileEntry,
        host_name: str,
        url: str,
        target: str,
        have: int,
        free: int | None,
    ) -> None:
        """Ask whether to download; any answer but "download" cancels it with nothing fetched."""
        lines = [f"{file.path}, {size_text(file.size)}, from {url}", f"Into {target} on {host_name}."]
        if have:
            lines.append(f"{size_text(have)} of it is already there; the download goes on from there.")
        if free is not None:
            lines.append(f"{size_text(free)} free on {host_name}; {size_text(free - file.size + have)} after it.")
        lines.append("It is used only once its SHA-256 is the catalog's.")
        draft = QuestionDraft(
            type="approval",
            title=f"Download {file.path} ({size_text(file.size)}) to {host_name}?",
            detail="\n".join(lines),
            options=[
                Option(id="download", label="Download it", key="y", effect=f"fetches {size_text(file.size - have)}"),
                Option(id="cancel", label="Not now", key="n", effect="nothing is fetched"),
            ],
            default="cancel",
            expires=self.runtime.state.now() + timedelta(minutes=QUESTION_MINUTES),
        )
        answer = await context.ask(draft)
        if answer.option != "download":
            raise Canceled(f"not downloaded: {answer.by.describe()} chose not to")

    async def _ask_remove(
        self,
        context: OperationContext,
        model: ModelEntry,
        host_name: str,
        doomed: list[tuple[ModelFileEntry, str, int]],
        result: dict[str, Any],
    ) -> None:
        """Ask whether to remove: each file, what it frees, how to bring it back; any answer but "remove" cancels it
        with nothing removed."""
        count, freed = len(doomed), sum(size for _, _, size in doomed)
        lines = [f"{path} ({size_text(size)})" for _, path, size in doomed]
        lines += [f"Clank forgets {path}, which is yours: it stays where it is." for path in result["forgotten"]]
        lines.append(f"The catalog keeps {model.name}, and every preset that uses it stays. To bring it back:")
        lines += result["restore"]
        draft = QuestionDraft(
            type="approval",
            title=f"Remove {_files_text(count)} of {model.name} ({size_text(freed)}) from {host_name}?",
            detail="\n".join(lines),
            options=[
                Option(
                    id="remove",
                    label="Remove it" if count == 1 else "Remove them",
                    key="y",
                    effect=f"frees {size_text(freed)}",
                ),
                Option(id="cancel", label="Not now", key="n", effect="nothing is removed"),
            ],
            default="cancel",
            expires=self.runtime.state.now() + timedelta(minutes=QUESTION_MINUTES),
        )
        answer = await context.ask(draft)
        if answer.option != "remove":
            raise Canceled(f"not removed: {answer.by.describe()} chose not to")

    async def _move(self, context: OperationContext, host: EngineHost, folder: str, source: str, name: str) -> None:
        """Rename a file in its folder on the host."""
        status = await context.run_blocking(
            host.run_step, [host.PYTHON, "-c", MOVE, source, name], {}, folder, context.log, lambda: False
        )
        if status != 0:
            raise ModelFileError(f"could not rename {source} to {name} in {folder} (exit {status})")


def _files_text(count: int) -> str:
    """A count of files as people say it: 1 file, 2 files."""
    return "1 file" if count == 1 else f"{count} files"


def _reads(preset: Preset | None, model: ModelEntry) -> str | None:
    """The format of a model's files that a preset's engine reads: "" when the preset runs another model; None when
    nothing says (its preset is gone, or its engine is one Clank no longer knows)."""
    if preset is None:
        return None
    if preset.model != model.id:
        return ""
    try:
        return ENGINES.get(preset.engine).FORMAT
    except AdapterError:
        return None


def _restore(model: ModelEntry, file: ModelFileEntry, host_name: str) -> str:
    """How to bring a removed file back: its download, or why there is none."""
    if not file.revision:
        return f"{file.path} cannot be downloaded again: its revision is no longer known"
    return f"`clank model download {model.id} --format {file.format} --role {file.role} --host {host_name}`"
