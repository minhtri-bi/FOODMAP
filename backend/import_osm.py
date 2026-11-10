"""Import a bounded Geofabrik snapshot without a full-country node-location cache."""

import argparse
import hashlib
from datetime import datetime
from pathlib import Path

import osmium

from backend.database import Store
from backend.discovery import COVERAGE

SOURCE_URL = "https://download.geofabrik.de/asia/vietnam-261108.osm.pbf"
EXPECTED_MD5 = "06e54d5e1726ea3aac340b8272ffd26d"
OBSERVED_AT = "2026-11-08T21:21:00Z"
BOUNDS = (10.35, 106.2, 11.2, 107.1)
AMENITIES = frozenset({"restaurant", "cafe", "fast_food", "food_court"})
MAX_RECORDS = 20_000
MAX_WAY_CANDIDATES = 30_000
MAX_WAY_REFERENCES = 1_000_000


def entry(tags: osmium.osm.TagList, osm_id: str) -> dict[str, object] | None:
    name, category = tags.get("name", "").strip(), tags.get("amenity", "")
    if not name or category not in AMENITIES:
        return None
    street = " ".join(filter(None, (tags.get("addr:housenumber"), tags.get("addr:street"))))
    address = tags.get("addr:full") or ", ".join(filter(None, (
        street, tags.get("addr:suburb"), tags.get("addr:district"), tags.get("addr:city")
    )))
    return {"osm_id": osm_id, "name": name[:160], "address": address[:500],
            "category": category, "source_url": f"https://www.openstreetmap.org/{osm_id}",
            "observed_at": OBSERVED_AT, "license": "ODbL-1.0; © OpenStreetMap contributors"}


def within(latitude: float, longitude: float) -> bool:
    return BOUNDS[0] <= latitude <= BOUNDS[2] and BOUNDS[1] <= longitude <= BOUNDS[3]


class FoodObjects(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict[str, object]] = []
        self.ways: list[tuple[dict[str, object], tuple[int, ...]]] = []
        self.reference_count = 0

    def node(self, node: osmium.osm.Node) -> None:
        if not node.location.valid() or not within(node.location.lat, node.location.lon):
            return
        record = entry(node.tags, f"node/{node.id}")
        if record:
            if len(self.records) >= MAX_RECORDS:
                raise ValueError("Regional node candidate limit reached; index was not changed.")
            self.records.append({**record, "latitude": node.location.lat, "longitude": node.location.lon})

    def way(self, way: osmium.osm.Way) -> None:
        record = entry(way.tags, f"way/{way.id}")
        if record and way.nodes:
            if (len(self.ways) >= MAX_WAY_CANDIDATES
                    or self.reference_count + len(way.nodes) > MAX_WAY_REFERENCES):
                raise ValueError("OSM way working-set limit reached; index was not changed.")
            self.reference_count += len(way.nodes)
            self.ways.append((record, tuple(node.ref for node in way.nodes)))


class NeededLocations(osmium.SimpleHandler):
    def __init__(self, needed: frozenset[int]) -> None:
        super().__init__()
        self.needed = needed
        self.locations: dict[int, tuple[float, float]] = {}

    def node(self, node: osmium.osm.Node) -> None:
        if node.id in self.needed and node.location.valid():
            self.locations[node.id] = (node.location.lat, node.location.lon)


def import_snapshot(path: Path, store: Store) -> int:
    if not path.is_file() or path.stat().st_size > 512 * 1024 * 1024:
        raise ValueError("Expected the pinned OSM PBF file below 512 MiB.")
    with path.open("rb") as snapshot:
        digest = hashlib.file_digest(snapshot, "md5").hexdigest()
    if digest != EXPECTED_MD5:
        raise ValueError("Snapshot checksum differs from the pinned Geofabrik source; import stopped.")
    datetime.fromisoformat(OBSERVED_AT)
    food = FoodObjects()
    food.apply_file(str(path), filters=[
        osmium.filter.TagFilter(*(('amenity', category) for category in sorted(AMENITIES))),
        osmium.filter.KeyFilter('name'),
    ])
    locations = NeededLocations(frozenset(ref for _, refs in food.ways for ref in refs))
    locations.apply_file(str(path), filters=[osmium.filter.IdFilter(locations.needed)])
    for original, refs in food.ways:
        unique = tuple(dict.fromkeys(refs))
        points = [locations.locations[ref] for ref in unique if ref in locations.locations]
        if len(points) != len(unique):
            continue
        latitude = sum(point[0] for point in points) / len(points)
        longitude = sum(point[1] for point in points) / len(points)
        if within(latitude, longitude):
            if len(food.records) >= MAX_RECORDS:
                raise ValueError("Regional record limit reached; index was not changed.")
            food.records.append({**original, "latitude": latitude, "longitude": longitude})
    if not 0 < len(food.records) <= MAX_RECORDS:
        raise ValueError("Import produced an empty or oversized regional collection; original index retained.")
    store.initialize()
    coverage = COVERAGE + " Nodes and approximate way centers only; relation-only venues are omitted. Confirm the exact pin."
    with store.connect() as connection:
        connection.execute("DELETE FROM osm_search")
        connection.execute("DELETE FROM osm_places")
        connection.executemany("""
            INSERT INTO osm_places(osm_id, name, address, latitude, longitude, category,
                                   source_url, observed_at, license)
            VALUES (:osm_id, :name, :address, :latitude, :longitude, :category,
                    :source_url, :observed_at, :license)
        """, food.records)
        connection.executemany("INSERT INTO osm_search VALUES (:osm_id, :name, :address)", food.records)
        connection.execute("""
            INSERT INTO osm_imports VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET observed_at=excluded.observed_at,
                source_url=excluded.source_url, checksum=excluded.checksum,
                coverage=excluded.coverage, count=excluded.count
        """, (OBSERVED_AT, SOURCE_URL, digest, coverage, len(food.records)))
    return len(food.records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbf", type=Path)
    parser.add_argument("--database", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "foodroute.sqlite3")
    args = parser.parse_args()
    count = import_snapshot(args.pbf, Store(args.database))
    print(f"Imported {count} named regional OSM food venues; snapshot {OBSERVED_AT}; source {SOURCE_URL}")
