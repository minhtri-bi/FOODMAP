"""Permitted regional OSM suggestions; proximity is ranking, never a route estimate."""

import math
import sqlite3
from datetime import datetime

from backend.schemas import Contract, OsmEvidence

DISCOVERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS osm_places (
    osm_id TEXT PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL,
    latitude REAL NOT NULL, longitude REAL NOT NULL, category TEXT NOT NULL,
    source_url TEXT NOT NULL, observed_at TEXT NOT NULL, license TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS osm_search USING fts5(
    osm_id UNINDEXED, name, address, tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS osm_imports (
    id INTEGER PRIMARY KEY CHECK(id = 1), observed_at TEXT NOT NULL,
    source_url TEXT NOT NULL, checksum TEXT NOT NULL, coverage TEXT NOT NULL, count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS source_osm_evidence (
    source_id TEXT PRIMARY KEY REFERENCES sources(id), osm_id TEXT NOT NULL UNIQUE,
    evidence_json TEXT NOT NULL
);
"""
COVERAGE = (
    "Incomplete OSM coverage: named food venues in the Ho Chi Minh City pilot rectangle "
    "10.35–11.2 latitude, 106.2–107.1 longitude. Not an administrative city boundary; "
    "some edge records may be outside the city. No Google ratings or route distances."
)


class Suggestion(OsmEvidence):
    distance_km: float | None


class DiscoveryMeta(Contract):
    total: int
    coverage: str
    observed_at: datetime | None


class DiscoveryPage(Contract):
    data: list[Suggestion]
    meta: DiscoveryMeta


def search_places(connection: sqlite3.Connection, query: str, latitude: float | None,
                  longitude: float | None, limit: int) -> DiscoveryPage:
    words = query.split()
    match = " AND ".join('"' + word.replace('"', '""') + '"*' for word in words)
    condition = "WHERE osm_id IN (SELECT osm_id FROM osm_search WHERE osm_search MATCH ?)" if match else ""
    connection.execute("BEGIN")
    rows = connection.execute("SELECT * FROM osm_places " + condition, (match,) if match else ()).fetchall()
    source = connection.execute("SELECT observed_at, coverage FROM osm_imports WHERE id = 1").fetchone()
    results = [Suggestion.model_validate({**dict(row), "distance_km": (
        proximity(latitude, longitude, row["latitude"], row["longitude"])
        if latitude is not None and longitude is not None else None
    )}) for row in rows]
    ordered = sorted(results, key=lambda item: (
        item.distance_km if item.distance_km is not None else 0, item.name.casefold(), item.osm_id
    ))
    return DiscoveryPage(data=ordered[:limit], meta=DiscoveryMeta(
        total=len(results), coverage=source["coverage"] if source else COVERAGE,
        observed_at=source["observed_at"] if source else None,
    ))


def proximity(origin_lat: float, origin_lon: float, target_lat: float, target_lon: float) -> float:
    """Haversine great-circle distance for suggestion ordering only."""
    delta_lat = math.radians(target_lat - origin_lat)
    delta_lon = math.radians(target_lon - origin_lon)
    value = (math.sin(delta_lat / 2) ** 2 + math.cos(math.radians(origin_lat))
             * math.cos(math.radians(target_lat)) * math.sin(delta_lon / 2) ** 2)
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, value))))
