"""The artifact libraries (decision 0135): fetch them into `clank/components/artifacts/lib/`, or check the copy there.

`python -m tools.artifact_libs fetch` downloads each library's files at its pinned version from jsDelivr's copy of its
npm package (`SOURCES`), KaTeX's fonts as its style sheet names them, and the license texts, then writes
`LIBRARIES.json`: each file with its library, version, source URL and SHA-256. `python -m tools.artifact_libs check`
(and the repository's tests) compare every file with its checksum. Never run by Clank itself: the files are kept in the
repository, so Clank needs no network to show an artifact.
"""

import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "clank" / "components" / "artifacts" / "lib"
MANIFEST = LIB / "LIBRARIES.json"
NPM = "https://cdn.jsdelivr.net/npm"
# library: (npm package, version, license, {file kept: path in the package}, the package's license file)
SOURCES: dict[str, tuple[str, str, str, dict[str, str], str]] = {
    "Plotly": ("plotly.js-dist-min", "2.35.2", "MIT", {"plotly.min.js": "plotly.min.js"}, "LICENSE"),
    "KaTeX": (
        "katex",
        "0.16.11",
        "MIT",
        {
            "katex.min.js": "dist/katex.min.js",
            "katex.min.css": "dist/katex.min.css",
            "auto-render.min.js": "dist/contrib/auto-render.min.js",
        },
        "LICENSE",
    ),
    "marked": ("marked", "14.1.3", "MIT", {"marked.min.js": "marked.min.js"}, "LICENSE.md"),
    "Mermaid": ("mermaid", "11.4.0", "MIT", {"mermaid.min.js": "dist/mermaid.min.js"}, "LICENSE"),
}
FONTS = re.compile(r"url\((fonts/[A-Za-z0-9_-]+\.woff2)\)")


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as answer:
        data: bytes = answer.read()
        return data


def fetch() -> int:
    """Download every file and write the manifest."""
    LIB.mkdir(parents=True, exist_ok=True)
    listed: list[dict[str, str]] = []

    def keep(name: str, library: str, version: str, url: str) -> None:
        data = _get(url)
        target = LIB / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        listed.append({"file": name, "library": library, "version": version, "source": url,
                       "sha256": hashlib.sha256(data).hexdigest()})  # fmt: skip
        print(f"{name}: {len(data):,} bytes")

    for library, (package, version, _, files, license_file) in SOURCES.items():
        base = f"{NPM}/{package}@{version}"
        for name, path in files.items():
            keep(name, library, version, f"{base}/{path}")
        keep(f"licenses/{library}.txt", library, version, f"{base}/{license_file}")
        if library == "KaTeX":
            style = (LIB / "katex.min.css").read_text(encoding="utf-8")
            for font in sorted(set(FONTS.findall(style))):
                keep(font, library, version, f"{base}/dist/{font}")
    MANIFEST.write_text(json.dumps({"libraries": {name: {"version": source[1], "license": source[2]}
                                                  for name, source in SOURCES.items()},
                                    "files": listed}, indent=2) + "\n", encoding="utf-8")  # fmt: skip
    return 0


def problems() -> list[str]:
    """What is missing or differs from its checksum."""
    if not MANIFEST.is_file():
        return [f"{MANIFEST} is missing: python -m tools.artifact_libs fetch"]
    found = []
    for each in json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]:
        path = LIB / each["file"]
        if not path.is_file():
            found.append(f"{each['file']} is missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != each["sha256"]:
            found.append(f"{each['file']} differs from its checksum")
    return found


def main() -> int:
    """`fetch`, or check the copy (the default): 1 when anything is missing or differs."""
    if sys.argv[1:] == ["fetch"]:
        return fetch()
    found = problems()
    for problem in found:
        print(problem)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
