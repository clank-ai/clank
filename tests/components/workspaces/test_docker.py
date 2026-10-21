"""Design 0002 §2.9 and §3.2: Clank tells its own containers from the others by their labels (this CLANK_HOME's,
another home's, another program's labels or name), and the Docker route shows the platform's state, a one-line
summary and each container with its owner, behind the token."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.service import owner
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import open_kernel
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform, container

AUTHORIZED = {"Authorization": "Bearer t"}


def test_a_container_is_clanks_only_by_this_homes_label_whatever_its_name(home: Home) -> None:
    mine = container("workspace-demo", labels={"clank.home": home.id, "clank.component": "workspaces"})
    another_homes = container("workspace-other", labels={"clank.home": "ffffffffffff"})
    labeled = container("sandbox-017", labels={"toolbox.sandbox": "1"})
    named = container("clank-looking-build")
    other = container("postgres-dev", labels={"com.docker.compose.project": "dev"})
    found = [owner(each, home.id) for each in (mine, another_homes, labeled, named, other)]
    assert found == ["clank", "other", "other", "other", "other"]


@pytest.fixture
def http(home: Home, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    platform = FakePlatform(
        containers=[
            container("workspace-demo", labels={"clank.home": home.id, "clank.component": "workspaces"}),
            container("toolbox-sandbox-017", labels={"toolbox.sandbox": "1"}),
            container("postgres-dev"),
            container("old-build", state="exited"),
        ]
    )
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 11, 12, 0, tzinfo=UTC)), registry.components())
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as client:
        yield client
    kernel.close()


def test_the_docker_route_shows_the_state_and_each_container_with_its_owner(http: TestClient) -> None:
    answer = http.get("/api/v1/docker", headers=AUTHORIZED).json()
    assert (answer["state"], answer["version"], answer["engine"]) == ("running", "4.85.0", "29.6.2")
    assert answer["summary"] == "Fake Docker · running · 3 containers running, 1 of them Clank's"
    owners = {each["name"]: each["owner"] for each in answer["containers"]}
    assert owners == {
        "workspace-demo": "clank",
        "toolbox-sandbox-017": "other",
        "postgres-dev": "other",
        "old-build": "other",
    }
    assert http.get("/api/v1/docker").status_code == 401
