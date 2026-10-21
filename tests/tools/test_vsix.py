"""Design 0002 §3.2 (decision 0028): the VS Code extension is packaged as a `.vsix` by Clank's own tool: the manifest
naming the extension, its version, its publisher and the VS Code it needs, the content types, and the extension's
manifest, its README and its compiled files; nothing of its tests or its tools; and nothing at all before it is
compiled."""

import json
import zipfile
from pathlib import Path

import pytest

from tools.vsix import VsixError, build_vsix

PACKAGE = {
    "name": "clank",
    "displayName": "Clank",
    "description": "Clank in VS Code: the service & Docker in the status bar.",
    "version": "0.1.0",
    "publisher": "clank",
    "engines": {"vscode": "^1.138.0"},
    "extensionKind": ["ui", "workspace"],
}


def extension(tmp_path: Path, compiled: bool = True) -> Path:
    folder = tmp_path / "vscode"
    files = {
        "package.json": json.dumps(PACKAGE),
        "README.md": "# Clank for VS Code\n",
        "node_modules/typescript/index.js": "",
        "src/extension.ts": "",
    }
    if compiled:
        files |= {"out/src/extension.js": "", "out/src/core/client.js": "", "out/test/client.test.js": "",
                  "media/annotator.html": "<!doctype html>", "media/annotator.css": ""}  # fmt: skip
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def test_the_package_holds_the_manifests_the_compiled_extension_and_its_media_only(tmp_path: Path) -> None:
    """Design 0008 §6: the annotator's page, style and scripts go with it (`media/`)."""
    built = build_vsix(extension(tmp_path), tmp_path / "clank.vsix")
    with zipfile.ZipFile(built) as package:
        names = sorted(package.namelist())
    assert names == [
        "[Content_Types].xml",
        "extension.vsixmanifest",
        "extension/README.md",
        "extension/media/annotator.css",
        "extension/media/annotator.html",
        "extension/out/src/core/client.js",
        "extension/out/src/extension.js",
        "extension/package.json",
    ]


def test_the_manifest_names_the_extension_its_version_and_the_vs_code_it_needs(tmp_path: Path) -> None:
    built = build_vsix(extension(tmp_path), tmp_path / "clank.vsix")
    with zipfile.ZipFile(built) as package:
        manifest = package.read("extension.vsixmanifest").decode("utf-8")
        types = package.read("[Content_Types].xml").decode("utf-8")
    assert '<Identity Language="en-US" Id="clank" Version="0.1.0" Publisher="clank" />' in manifest
    assert '<Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.138.0" />' in manifest
    assert '<Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="ui,workspace" />' in manifest
    assert "the service &amp; Docker" in manifest
    assert 'Path="extension/package.json"' in manifest
    assert ('Extension=".js"' in types, 'Extension=".html"' in types, 'Extension=".css"' in types) == (True, True, True)


def test_a_package_is_refused_before_the_extension_is_compiled(tmp_path: Path) -> None:
    with pytest.raises(VsixError, match="npm run build"):
        build_vsix(extension(tmp_path, compiled=False), tmp_path / "clank.vsix")
