"""Exercise persistence, stale edits, identity confirmation and local browser boundaries."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app

HEADERS = {"X-FoodRoute-Request": "1", "Origin": "http://127.0.0.1:5173"}
BRANCH = {
    "name": "Phở Hòa Pasteur", "branch": "Pasteur", "address": "260C Pasteur, Ho Chi Minh City",
    "latitude": 10.7866905, "longitude": 106.6892627, "branch_confirmed": True,
}


def test_private_edits_survive_restart_without_changing_source(tmp_path: Path) -> None:
    database = tmp_path / "places.sqlite3"
    with TestClient(create_app(database)) as client:
        created = client.post("/api/v1/restaurants", json=BRANCH, headers=HEADERS)
        assert created.status_code == 201
        original = created.json()["data"]
        identity = original["id"]
        edit = {"favorite": True, "status": "tried", "personal_rating": 0,
                "notes": "Private note; not a Google review", "revision": 1}
        updated = client.put(f"/api/v1/restaurants/{identity}/personal", json=edit, headers=HEADERS)
        assert updated.status_code == 200
        assert updated.json()["data"]["personal"]["revision"] == 2
        stale = client.put(f"/api/v1/restaurants/{identity}/personal", json={**edit, "notes": "stale"}, headers=HEADERS)
        assert stale.status_code == 409
    with TestClient(create_app(database)) as restarted:
        record = restarted.get(f"/api/v1/restaurants/{identity}").json()["data"]
        assert record["source"] == original["source"]
        assert record["personal"]["notes"] == edit["notes"]
        assert record["personal"]["personal_rating"] == 0
        assert record["personal"]["favorite"] is True
        assert record["personal"]["status"] == "tried"
        found = restarted.get("/api/v1/restaurants", params={"q": "pho hoa", "favorite_only": True}).json()
        assert [place["id"] for place in found["data"]] == [identity]
        assert restarted.get("/api/v1/restaurants", params={"status": "avoid"}).json()["data"] == []


def test_exact_duplicates_do_not_merge_distinct_branches(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "places.sqlite3")) as client:
        first = client.post("/api/v1/restaurants", json=BRANCH, headers=HEADERS)
        duplicate = client.post("/api/v1/restaurants", json=BRANCH, headers=HEADERS)
        assert duplicate.status_code == 409
        other = client.post("/api/v1/restaurants", json={**BRANCH, "branch": "Another branch", "address": "Different address"}, headers=HEADERS)
        assert other.status_code == 201
        assert first.json()["data"]["id"] != other.json()["data"]["id"]
        assert client.get("/api/v1/restaurants").json()["meta"]["total"] == 2


@pytest.mark.parametrize("patch", [
    {"name": "   "}, {"latitude": 91}, {"longitude": -181},
    {"branch_confirmed": False}, {"google_rating": 5},
])
def test_invalid_identity_never_enters_collection(tmp_path: Path, patch: dict[str, object]) -> None:
    with TestClient(create_app(tmp_path / "places.sqlite3")) as client:
        response = client.post("/api/v1/restaurants", json={**BRANCH, **patch}, headers=HEADERS)
        assert response.status_code == 422
        assert client.get("/api/v1/restaurants").json()["data"] == []


def test_cross_origin_form_and_missing_header_cannot_write(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "places.sqlite3")) as client:
        assert client.post("/api/v1/restaurants", json=BRANCH).status_code == 403
        denied = client.post("/api/v1/restaurants", json=BRANCH, headers={**HEADERS, "Origin": "https://untrusted.example"})
        assert denied.status_code == 403
        assert client.get("/api/v1/restaurants").json()["data"] == []


def test_oversized_edit_revision_is_rejected_without_losing_notes(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "places.sqlite3")) as client:
        record = client.post("/api/v1/restaurants", json=BRANCH, headers=HEADERS).json()["data"]
        payload = {key: value for key, value in record["personal"].items() if key != "updated_at"}
        response = client.put(f"/api/v1/restaurants/{record['id']}/personal", headers=HEADERS,
                              json={**payload, "revision": 9_223_372_036_854_775_808})
        assert response.status_code == 422
        persisted = client.get(f"/api/v1/restaurants/{record['id']}").json()["data"]
        assert persisted["personal"] == record["personal"]
