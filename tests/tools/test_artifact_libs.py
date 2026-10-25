"""Design 0021 §5 (decision 0135): the artifact libraries kept in Clank (Plotly, KaTeX, marked, Mermaid) are each file
its manifest lists, with its checksum, at the pinned versions, under the MIT license, with their license texts beside
them."""

import json

from tools.artifact_libs import LIB, MANIFEST, SOURCES, problems


def test_every_library_file_is_there_with_its_checksum() -> None:
    assert problems() == []


def test_the_libraries_are_the_pinned_four_under_the_mit_license_with_their_license_texts() -> None:
    kept = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert kept["libraries"] == {name: {"version": source[1], "license": "MIT"} for name, source in SOURCES.items()}
    assert set(kept["libraries"]) == {"Plotly", "KaTeX", "marked", "Mermaid"}
    for name in kept["libraries"]:
        assert (LIB / "licenses" / f"{name}.txt").is_file()
    assert any(each["file"].startswith("fonts/KaTeX_") for each in kept["files"]), "KaTeX's fonts, for offline math"
