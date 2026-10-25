"""Package the VS Code extension as a `.vsix`, the file `code --install-extension` installs (decision 0028).

A `.vsix` is a zip: `extension.vsixmanifest` (who the extension is, its version and the VS Code it needs),
`[Content_Types].xml`, and `extension/` with the extension's `package.json`, its README, its compiled files and its
`media/` (the pages its webviews show, design 0008), with the artifact libraries copied from Clank's folder into
`media/lib/` (decision 0135). Its
tests and its tools (`node_modules`) stay out. It is written from the compiled extension, so it is refused before
`npm run build` (or `tools.check`) has run. `uv run python -m tools.vsix` writes `vscode/clank-<version>.vsix`.
"""

import json
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

FOLDER = Path(__file__).resolve().parents[1] / "vscode"
LIBRARIES = Path(__file__).resolve().parents[1] / "clank" / "components" / "artifacts" / "lib"  # decision 0135
CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json" />
  <Default Extension=".js" ContentType="application/javascript" />
  <Default Extension=".html" ContentType="text/html" />
  <Default Extension=".css" ContentType="text/css" />
  <Default Extension=".md" ContentType="text/markdown" />
  <Default Extension=".txt" ContentType="text/plain" />
  <Default Extension=".woff2" ContentType="font/woff2" />
  <Default Extension=".vsixmanifest" ContentType="text/xml" />
</Types>
"""


class VsixError(Exception):
    """The extension cannot be packaged as it is."""


def manifest(package: dict[str, Any]) -> str:
    """The extension's `extension.vsixmanifest`, from its `package.json`."""
    identity = " ".join(
        f"{name}={quoteattr(str(value))}"
        for name, value in (
            ("Language", "en-US"),
            ("Id", package["name"]),
            ("Version", package["version"]),
            ("Publisher", package["publisher"]),
        )
    )
    properties = {
        "Microsoft.VisualStudio.Code.Engine": package["engines"]["vscode"],
        "Microsoft.VisualStudio.Code.ExtensionDependencies": "",
        "Microsoft.VisualStudio.Code.ExtensionPack": "",
        "Microsoft.VisualStudio.Code.ExtensionKind": ",".join(package.get("extensionKind", ["workspace"])),
        "Microsoft.VisualStudio.Code.LocalizedLanguages": "",
        "Microsoft.VisualStudio.Services.GitHubFlavoredMarkdown": "true",
    }
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">',
        "  <Metadata>",
        f"    <Identity {identity} />",
        f"    <DisplayName>{escape(package.get('displayName', package['name']))}</DisplayName>",
        f'    <Description xml:space="preserve">{escape(package.get("description", ""))}</Description>',
        f"    <Categories>{escape(','.join(package.get('categories', ['Other'])))}</Categories>",
        "    <Properties>",
        *[f"      <Property Id={quoteattr(name)} Value={quoteattr(value)} />" for name, value in properties.items()],
        "    </Properties>",
        "  </Metadata>",
        "  <Installation>",
        '    <InstallationTarget Id="Microsoft.VisualStudio.Code" />',
        "  </Installation>",
        "  <Dependencies />",
        "  <Assets>",
        '    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />',
        '    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md"'
        ' Addressable="true" />',
        "  </Assets>",
        "</PackageManifest>",
    ]
    return "\n".join(lines) + "\n"


def build_vsix(folder: Path = FOLDER, output: Path | None = None) -> Path:
    """Write the package of the compiled extension in `folder`; returns where it is."""
    package = json.loads((folder / "package.json").read_text(encoding="utf-8"))
    compiled = sorted((folder / "out" / "src").rglob("*.js")) if (folder / "out" / "src").is_dir() else []
    if not compiled:
        raise VsixError(
            "the extension is not compiled: run `npm run build` in vscode/ (or `uv run python -m tools.check`)"
        )
    output = output or folder / f"{package['name']}-{package['version']}.vsix"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as written:
        written.writestr("extension.vsixmanifest", manifest(package))
        written.writestr("[Content_Types].xml", CONTENT_TYPES)
        written.write(folder / "package.json", "extension/package.json")
        written.write(folder / "README.md", "extension/README.md")
        for path in compiled:
            written.write(path, f"extension/{path.relative_to(folder).as_posix()}")
        for path in sorted((folder / "media").rglob("*")) if (folder / "media").is_dir() else []:
            if path.is_file():
                written.write(path, f"extension/{path.relative_to(folder).as_posix()}")
        for path in sorted(LIBRARIES.rglob("*")) if LIBRARIES.is_dir() else []:  # decision 0135: one copy, Clank's
            if path.is_file():
                written.write(path, f"extension/media/lib/{path.relative_to(LIBRARIES).as_posix()}")
    return output


def main() -> int:
    """Write `vscode/clank-<version>.vsix` and say how to install it."""
    try:
        built = build_vsix()
    except VsixError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Wrote {built}; install it with: code --install-extension {built}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
