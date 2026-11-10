"""Regional suggestions never hide far matches or overwrite confirmed source evidence."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.database import Store
from backend.main import create_app

HEADERS = {"X-FoodRoute-Request": "1", "Origin": "http://127.0.0.1:5173"}


def seed_index(store: Store) -> None:
    store.initialize()
    with store.connect() as connection:
        connection.executemany("INSERT INTO osm_places VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            ("node/1", "Same food", "Near street", 10.7, 106.7, "restaurant",
             "https://www.openstreetmap.org/node/1", "2026-11-08T21:21:00Z", "ODbL-1.0"),
            ("node/2", "Same food", "Far street", 11.1, 107.0, "restaurant",
             "https://www.openstreetmap.org/node/2", "2026-11-08T21:21:00Z", "ODbL-1.0"),
        ])
        connection.execute("INSERT INTO osm_search SELECT osm_id, name, address FROM osm_places")


def test_origin_changes_order_without_excluding_far_match(tmp_path: Path) -> None:
    path = tmp_path / "places.sqlite3"
    seed_index(Store(path))
    with TestClient(create_app(path)) as client:
        near = client.get("/api/v1/discovery", params={"q": "same", "latitude": 10.7, "longitude": 106.7}).json()
        far = client.get("/api/v1/discovery", params={"q": "same", "latitude": 11.1, "longitude": 107}).json()
        assert [item["osm_id"] for item in near["data"]] == ["node/1", "node/2"]
        assert [item["osm_id"] for item in far["data"]] == ["node/2", "node/1"]
        assert near["meta"]["total"] == far["meta"]["total"] == 2
        assert near["data"][0]["distance_km"] == 0
        unknown = client.get("/api/v1/discovery", params={"q": "same"}).json()
        assert all(item["distance_km"] is None for item in unknown["data"])
        assert client.get("/api/v1/discovery", params={"latitude": 10}).status_code == 422
        assert client.get("/api/v1/discovery", params={"latitude": "nan", "longitude": 1}).status_code == 422


def test_confirmed_osm_corrections_keep_original_evidence_and_source_identity(tmp_path: Path) -> None:
    path = tmp_path / "places.sqlite3"
    store = Store(path)
    seed_index(store)
    payload = {"name": "User corrected name", "branch": "Confirmed branch", "address": "Corrected street",
               "latitude": 10.71, "longitude": 106.71, "branch_confirmed": True, "osm_id": "node/1"}
    with TestClient(create_app(path)) as client:
        created = client.post("/api/v1/restaurants", json=payload, headers=HEADERS)
        assert created.status_code == 201
        record = created.json()["data"]
        evidence = record["source"]["osm_origin"]
        assert evidence["name"] == "Same food"
        assert evidence["address"] == "Near street"
        assert record["name"] == "User corrected name"
        assert client.post("/api/v1/restaurants", json={**payload, "name": "Different spelling"}, headers=HEADERS).status_code == 409
        with store.connect() as connection:
            connection.execute("UPDATE osm_places SET name = 'New source value' WHERE osm_id = 'node/1'")
        persisted = client.get(f"/api/v1/restaurants/{record['id']}").json()["data"]
        assert persisted["source"]["osm_origin"] == evidence
        assert persisted["name"] == payload["name"]
        assert client.post("/api/v1/restaurants", json={**payload, "osm_id": "node/999"}, headers=HEADERS).status_code == 422
