"""Design 0008 §4: each mark the owner draws on a figure, in words: the plot it is on (its title, and where it is among
several), its range in data coordinates in the axis's own scale (a log one too), the lines inside it with their points
and values; an arrow's tip and the line it points at (or the legend it stops just short of); a note's words and place;
a mark on a legend or a title says so; without the figure's geometry, its place in the image."""

from typing import Any

from clank.components.agents.figures import describe

LEFT = {
    "index": 0, "box": [50.0, 30.0, 350.0, 270.0], "title": "MSD vs time", "xlabel": "time", "ylabel": "MSD",
    "xlim": [0.0, 4.0], "ylim": [0.0, 16.0], "xscale": "linear", "yscale": "linear", "colorbar": False,
    "lines": [{"label": "n = 16", "color": "#1f77b4", "points": 5, "x": [0, 1, 2, 3, 4], "y": [0, 1, 4, 9, 16]}],
    "scatters": [], "legend": {"entries": ["n = 16"], "box": [60.0, 40.0, 150.0, 70.0]},
    "labels": {"title": [150.0, 5.0, 250.0, 25.0]},
}  # fmt: skip
RIGHT = {
    "index": 1, "box": [420.0, 30.0, 720.0, 270.0], "title": "growth", "xlabel": "", "ylabel": "",
    "xlim": [1.0, 4.0], "ylim": [10.0, 10000.0], "xscale": "linear", "yscale": "log", "colorbar": False,
    "lines": [], "scatters": [], "legend": None, "labels": {},
}  # fmt: skip
GEOMETRY: dict[str, Any] = {"size": [760, 300], "axes": [LEFT, RIGHT]}


def mark(n: int, kind: str, *points: tuple[float, float], color: str = "#e5484d", text: str = "") -> dict[str, Any]:
    return {"n": n, "kind": kind, "color": color, "points": [list(point) for point in points], "text": text}


def test_a_box_is_said_in_data_coordinates_with_the_lines_inside_it() -> None:
    [said] = describe([mark(1, "box", (190, 125), (285, 220))], GEOMETRY, (760, 300))
    assert said == (
        'Mark 1 (red box) on "MSD vs time" (left plot): time 1.867 to 3.133, MSD 3.333 to 9.667; '
        'inside it: "n = 16" (2 points, MSD 4 to 9).'
    )


def test_a_circle_holds_only_what_its_ellipse_holds_and_a_log_axis_is_read_in_its_scale() -> None:
    circle, logged = describe(
        [mark(2, "circle", (180, 190), (220, 230), color="#3e63dd"), mark(3, "box", (500, 110), (600, 190))],
        GEOMETRY,
        (760, 300),
    )
    assert circle.endswith('inside it: "n = 16" (1 point, MSD 4 to 4).')
    assert circle.startswith("Mark 2 (blue circle)")
    assert logged == 'Mark 3 (red box) on "growth" (right plot): x 1.8 to 2.8, y 100 to 1000.'


def test_an_arrow_says_what_its_tip_points_at_and_a_note_says_its_words() -> None:
    arrow, note, legend, title = describe(
        [
            mark(4, "arrow", (300, 40), (128, 252)),
            mark(5, "text", (200, 210), color="#f5a524", text="too crowded"),
            mark(6, "arrow", (300, 100), (100, 55)),
            mark(7, "circle", (180, 5), (220, 25)),
        ],
        GEOMETRY,
        (760, 300),
    )
    assert arrow == (
        'Mark 4 (red arrow) on "MSD vs time" (left plot): its tip at time 1.04, MSD 1.2, pointing at "n = 16" near '
        "time 1, MSD 1."
    )
    assert note == 'Mark 5 (amber note) "too crowded" on "MSD vs time" (left plot), at time 2, MSD 4.'
    assert legend == 'Mark 6 (red arrow) on the legend of "MSD vs time" (left plot) ("n = 16").'
    assert title == 'Mark 7 (red circle) on the title "MSD vs time" of "MSD vs time" (left plot).'


def test_an_arrow_that_stops_just_short_of_a_legend_points_at_it() -> None:
    short, line = describe(
        [mark(8, "arrow", (250, 200), (155, 75)), mark(9, "arrow", (300, 100), (130, 248))], GEOMETRY, (760, 300)
    )
    assert short == (
        'Mark 8 (red arrow) on "MSD vs time" (left plot): its tip at time 1.4, MSD 13, pointing at its legend '
        '("n = 16").'
    )
    assert "legend" not in line, "a line near the tip wins over a legend farther away"
    outside = {**RIGHT, "legend": {"entries": ["a", "b"], "box": [725.0, 100.0, 755.0, 140.0]}}
    [beside] = describe([mark(10, "arrow", (600, 250), (722, 145))], {"axes": [LEFT, outside]}, (760, 300))
    assert beside == 'Mark 10 (red arrow) pointing at the legend of "growth" (right plot) ("a", "b").'


def test_without_geometry_a_mark_is_placed_in_the_image() -> None:
    [said] = describe([mark(1, "circle", (700, 100), (800, 200))], None, (1000, 500))
    assert said == "Mark 1 (red circle) in the top right of the image (75% across, 30% down)."
