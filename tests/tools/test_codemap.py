"""Design 0002 §3.2 (M0.1): the code map lists every module of `clank/` and `tools/` with the first line of its
docstring, and refuses a module that has none."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from tools.codemap import CodeMapError, render

Write = Callable[[dict[str, str]], Path]


def test_each_module_gets_one_line_from_its_docstring(write_files: Write) -> None:
    root = write_files(
        {
            "clank/__init__.py": '"""Clank itself.\n\nMore detail that the map leaves out."""\n',
            "clank/cli/main.py": '"""The command line."""\n',
            "tools/codemap.py": '"""Writes the map."""\n',
        }
    )
    text = render(root)
    assert "| `clank/__init__.py` | Clank itself. |" in text
    assert "| `clank/cli/main.py` | The command line. |" in text
    assert "| `tools/codemap.py` | Writes the map. |" in text
    assert "More detail" not in text


def test_paths_use_forward_slashes_and_a_stable_order(write_files: Write) -> None:
    root = write_files({"clank/b.py": '"""B."""\n', "clank/a/z.py": '"""Z."""\n', "clank/a.py": '"""A."""\n'})
    rows = [line for line in render(root).splitlines() if line.startswith("| `")]
    assert rows == ["| `clank/a.py` | A. |", "| `clank/a/z.py` | Z. |", "| `clank/b.py` | B. |"]


def test_every_module_without_a_docstring_is_named_in_one_error(write_files: Write) -> None:
    root = write_files({"clank/good.py": '"""Fine."""\n', "clank/bad.py": "x = 1\n", "tools/worse.py": ""})
    with pytest.raises(CodeMapError) as caught:
        render(root)
    assert "clank/bad.py" in str(caught.value)
    assert "tools/worse.py" in str(caught.value)
    assert "clank/good.py" not in str(caught.value)


def test_a_module_that_is_not_valid_python_is_reported_not_crashed_on(write_files: Write) -> None:
    root = write_files({"clank/broken.py": '"""Half a module.\n'})
    with pytest.raises(CodeMapError, match=r"clank/broken\.py"):
        render(root)


def test_a_pipe_in_a_docstring_does_not_break_the_table(write_files: Write) -> None:
    root = write_files({"clank/pipes.py": '"""Reads a | b."""\n'})
    assert "| `clank/pipes.py` | Reads a \\| b. |" in render(root)


def test_the_extensions_typescript_modules_get_their_line_from_their_leading_comment(write_files: Write) -> None:
    root = write_files(
        {
            "clank/__init__.py": '"""Clank itself."""\n',
            "vscode/src/core/client.ts": "// The client of the API.\n// More that the map leaves out.\n\nexport {};\n",
            "vscode/test/client.test.ts": "// Design 0002 §2.7: the client sends the token.\nimport x;\n",
            "vscode/node_modules/x/index.ts": "export {};\n",
            "vscode/out/src/client.ts": "export {};\n",
        }
    )
    text = render(root)
    assert "| `vscode/src/core/client.ts` | The client of the API. |" in text
    assert "| `vscode/test/client.test.ts` | Design 0002 §2.7: the client sends the token. |" in text
    assert "node_modules" not in text
    assert "vscode/out" not in text


def test_a_typescript_module_without_a_leading_comment_is_named(write_files: Write) -> None:
    root = write_files({"clank/__init__.py": '"""Clank itself."""\n', "vscode/src/bare.ts": "export {};\n"})
    with pytest.raises(CodeMapError, match=r"vscode/src/bare\.ts"):
        render(root)


def test_a_module_git_ignores_is_not_in_the_map(write_files: Write) -> None:
    root = write_files(
        {".gitignore": "clank/scratch.py\n", "clank/a.py": '"""A."""\n', "clank/scratch.py": '"""S."""\n'}
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    text = render(root)
    assert "clank/a.py" in text
    assert "scratch" not in text


def test_the_phone_apps_javascript_modules_get_their_line_from_their_leading_comment(write_files: Write) -> None:
    root = write_files(
        {
            "clank/__init__.py": '"""Clank itself."""\n',
            "clank/components/remote/page/model.mjs": "// The app's logic.\n// More.\n\nexport {};\n",
            "clank/components/remote/page/sw.js": "// The service worker: the shell kept for the offline screen.\n",
            "clank/components/remote/page/app.js": "// The app on the stream.\nimport {} from './model.mjs';\n",
        }
    )
    text = render(root)
    assert "| `clank/components/remote/page/model.mjs` | The app's logic. |" in text
    assert (
        "| `clank/components/remote/page/sw.js` | The service worker: the shell kept for the offline screen. |" in text
    )
    assert "| `clank/components/remote/page/app.js` | The app on the stream. |" in text


def test_a_javascript_module_of_the_phone_app_without_a_leading_comment_is_named(write_files: Write) -> None:
    root = write_files(
        {"clank/__init__.py": '"""Clank itself."""\n', "clank/components/remote/page/bare.js": "export {};\n"}
    )
    with pytest.raises(CodeMapError, match=r"clank/components/remote/page/bare\.js"):
        render(root)
