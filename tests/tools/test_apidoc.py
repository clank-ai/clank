"""Design 0002 §2.14: the API page lists every route the service serves, with its method, its access level and what it
does."""

from pathlib import Path

from tools.apidoc import render_repository


def test_the_api_page_lists_every_route_with_its_access_and_purpose(tmp_path: Path) -> None:
    page = render_repository(tmp_path)
    assert "| GET | `/api/v1/events` | control | The event stream:" in page
    assert "| POST | `/api/v1/questions/{id}/answer` | control | Answer a question, once;" in page
    assert "| none |" not in page
