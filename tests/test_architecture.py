"""Decision 0019 and design 0002 §2.1: the kernel uses no component; a component uses another only through that one's
`service.py`, only if its declaration names it, and never in a cycle; every component has the same shape; and the
service never loads the console's library (a component's pages are imported only by the console). Every kind of adapter
has its contract tests and every adapter its recordings (design 0002 §2.10): an endpoint's are of HTTP (design 0016
§18)."""

import ast
import subprocess
import sys
from pathlib import Path

from clank import registry

PACKAGE = Path(__file__).resolve().parents[1] / "clank"
OUTSIDE_THE_KERNEL = ("clank.components", "clank.cli", "clank.console", "clank.registry", "clank.client")
SHAPE = ("component.py", "kinds.py", "service.py", "api.py", "cli.py")


def module_name(path: Path) -> str:
    parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = module_name(path).rsplit(".", 1)[0] if path.name != "__init__.py" else module_name(path)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join([*anchor, base] if base else anchor)
            found += [base] + [f"{base}.{alias.name}" for alias in node.names]
    return found


def component_folders() -> list[Path]:
    folder = PACKAGE / "components"
    return sorted(path for path in folder.iterdir() if path.is_dir() and not path.name.startswith("_"))


def test_the_kernel_uses_no_component_and_no_client() -> None:
    crossings = {
        path.relative_to(PACKAGE).as_posix(): bad
        for path in (PACKAGE / "kernel").rglob("*.py")
        if (bad := [name for name in imports(path) if name.startswith(OUTSIDE_THE_KERNEL)])
    }
    assert crossings == {}


def test_a_component_uses_another_only_through_its_service_and_only_if_it_declares_it() -> None:
    declared = {component.name: set(component.uses) for component in registry.components()}
    crossings = []
    for folder in component_folders():
        for path in folder.rglob("*.py"):
            for name in imports(path):
                parts = name.split(".")
                if len(parts) < 3 or parts[:2] != ["clank", "components"] or parts[2] == folder.name:
                    continue
                allowed = parts[3:4] == ["service"] and parts[2] in declared.get(folder.name, set())
                if not allowed:
                    crossings.append(f"{path.relative_to(PACKAGE).as_posix()}: {name}")
    assert crossings == []


def test_the_uses_between_components_have_no_cycle() -> None:
    uses = {component.name: tuple(component.uses) for component in registry.components()}
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(name: str, path: tuple[str, ...]) -> None:
        assert name not in visiting, f"a cycle: {' -> '.join((*path, name))}"
        if name in done:
            return
        visiting.add(name)
        for used in uses.get(name, ()):
            visit(used, (*path, name))
        visiting.discard(name)
        done.add(name)

    for name in uses:
        visit(name, ())


def test_every_component_has_the_same_shape_and_is_listed() -> None:
    listed = {component.name for component in registry.components()}
    for folder in component_folders():
        assert folder.name in listed, f"{folder.name} is not in clank/components/__init__.py"
        missing = [name for name in SHAPE if not (folder / name).is_file()]
        assert missing == [], f"{folder.name} lacks {', '.join(missing)}"


TESTS = Path(__file__).resolve().parent


RECORDINGS = {
    "endpoint": "http.json"
}  # an endpoint's recordings are of HTTP (design 0016 §18); any other's, of a program


def test_every_kind_of_adapter_has_its_contract_tests_and_every_adapter_its_recordings() -> None:
    missing = []
    for kind in registry.adapter_kinds():
        if not (TESTS / "contract" / f"test_{kind.name}.py").is_file():
            missing.append(f"tests/contract/test_{kind.name}.py")
        recorded = RECORDINGS.get(kind.name, "program.json")
        for adapter in kind.all():
            if adapter.RECORDED and not list((TESTS / "fixtures" / adapter.NAME).glob(f"*/{recorded}")):
                missing.append(f"tests/fixtures/{adapter.NAME}/<version>/{recorded}")
    assert missing == []


def test_the_endpoint_kind_of_adapter_is_the_runtimes() -> None:
    kinds = {kind.name for kind in registry.adapter_kinds()}
    assert {"engine", "endpoint"} <= kinds


def test_the_service_never_loads_the_console() -> None:
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, clank.registry, clank.kernel.service, clank.kernel.api; "
            "[component.build for component in clank.registry.components()]; "
            "print('textual' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert loaded.stdout.strip() == "False"
