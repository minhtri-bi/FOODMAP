"""SQLite transactions keep source evidence, identity versions and private edits separate."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.discovery import DISCOVERY_SCHEMA
from backend.schemas import PersonalInput, Restaurant, RestaurantCreate, RestaurantPage

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind = 'user_manual'),
    permission_basis TEXT NOT NULL, observed_at TEXT NOT NULL,
    storage_allowed INTEGER NOT NULL CHECK(storage_allowed IN (0, 1)),
    cloud_eligible INTEGER NOT NULL CHECK(cloud_eligible IN (0, 1))
);
CREATE TABLE IF NOT EXISTS restaurants (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, current_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS restaurant_versions (
    restaurant_id TEXT NOT NULL REFERENCES restaurants(id), version INTEGER NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(id), name TEXT NOT NULL,
    branch TEXT NOT NULL, address TEXT NOT NULL,
    latitude REAL NOT NULL CHECK(latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL CHECK(longitude BETWEEN -180 AND 180),
    PRIMARY KEY(restaurant_id, version),
    UNIQUE(name, branch, address, latitude, longitude)
);
CREATE TABLE IF NOT EXISTS user_places (
    restaurant_id TEXT PRIMARY KEY REFERENCES restaurants(id),
    favorite INTEGER NOT NULL CHECK(favorite IN (0, 1)),
    status TEXT NOT NULL CHECK(status IN ('want_to_try', 'tried', 'avoid')),
    personal_rating REAL CHECK(personal_rating BETWEEN 0 AND 5), notes TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision >= 1), updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_place_versions (
    restaurant_id TEXT NOT NULL REFERENCES restaurants(id), revision INTEGER NOT NULL,
    favorite INTEGER NOT NULL, status TEXT NOT NULL, personal_rating REAL,
    notes TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(restaurant_id, revision)
);
CREATE VIRTUAL TABLE IF NOT EXISTS restaurant_search USING fts5(
    restaurant_id UNINDEXED, name, branch, address, tokenize='unicode61 remove_diacritics 2'
);
"""
SELECT_RECORD = """
SELECT r.id, r.created_at, v.version, v.name, v.branch, v.address, v.latitude, v.longitude,
       s.id AS source_id, s.kind, s.permission_basis, s.observed_at,
       s.storage_allowed, s.cloud_eligible,
       p.favorite, p.status, p.personal_rating, p.notes, p.revision, p.updated_at,
       e.evidence_json
FROM restaurants r
JOIN restaurant_versions v ON v.restaurant_id = r.id AND v.version = r.current_version
JOIN sources s ON s.id = v.source_id
JOIN user_places p ON p.restaurant_id = r.id
LEFT JOIN source_osm_evidence e ON e.source_id = s.id
"""


class EditConflict(Exception):
    """A newer personal edit exists; callers must not overwrite it."""


class UnknownOsmPlace(Exception):
    """The requested origin is not present in the approved local OSM index."""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise RuntimeError("Unsupported database version; do not downgrade this database")
            connection.executescript(SCHEMA)
            connection.executescript(DISCOVERY_SCHEMA)
            connection.execute("PRAGMA user_version = 2")

    @staticmethod
    def record(row: sqlite3.Row) -> Restaurant:
        return Restaurant.model_validate(
            {
                **{
                    key: row[key]
                    for key in (
                        "id",
                        "created_at",
                        "version",
                        "name",
                        "branch",
                        "address",
                        "latitude",
                        "longitude",
                    )
                },
                "source": {
                    "id": row["source_id"],
                    "osm_origin": json.loads(row["evidence_json"]) if row["evidence_json"] else None,
                    **{
                        key: row[key]
                        for key in (
                            "kind",
                            "permission_basis",
                            "observed_at",
                            "storage_allowed",
                            "cloud_eligible",
                        )
                    },
                },
                "personal": {
                    key: row[key]
                    for key in (
                        "favorite",
                        "status",
                        "personal_rating",
                        "notes",
                        "revision",
                        "updated_at",
                    )
                },
            }
        )

    def get(self, restaurant_id: str) -> Restaurant | None:
        with self.connect() as connection:
            row = connection.execute(SELECT_RECORD + " WHERE r.id = ?", (restaurant_id,)).fetchone()
        return self.record(row) if row else None

    def create(self, payload: RestaurantCreate) -> Restaurant:
        identity, source_id = str(uuid4()), str(uuid4())
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?)",
                (source_id, "user_manual", "User-confirmed manual restaurant identity", now, 1, 0),
            )
            if payload.osm_id:
                original = connection.execute(
                    "SELECT * FROM osm_places WHERE osm_id = ?", (payload.osm_id,)
                ).fetchone()
                if original is None:
                    raise UnknownOsmPlace
                connection.execute(
                    "INSERT INTO source_osm_evidence VALUES (?, ?, ?)",
                    (source_id, payload.osm_id, json.dumps(dict(original), ensure_ascii=False)),
                )
            connection.execute("INSERT INTO restaurants VALUES (?, ?, 1)", (identity, now))
            connection.execute(
                "INSERT INTO restaurant_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identity,
                    1,
                    source_id,
                    payload.name,
                    payload.branch,
                    payload.address,
                    payload.latitude,
                    payload.longitude,
                ),
            )
            connection.execute(
                "INSERT INTO user_places VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identity, 0, "want_to_try", None, "", 1, now),
            )
            connection.execute(
                "INSERT INTO user_place_versions "
                "SELECT restaurant_id, revision, favorite, status, personal_rating, notes, updated_at "
                "FROM user_places WHERE restaurant_id = ?",
                (identity,),
            )
            connection.execute(
                "INSERT INTO restaurant_search VALUES (?, ?, ?, ?)",
                (identity, payload.name, payload.branch, payload.address),
            )
            row = connection.execute(SELECT_RECORD + " WHERE r.id = ?", (identity,)).fetchone()
        return self.record(row)

    def list(
        self, query: str, status: str | None, favorite_only: bool, limit: int, offset: int
    ) -> RestaurantPage:
        tokens = query.split()
        match = " AND ".join('"' + token.replace('"', '""') + '"*' for token in tokens)
        conditions = ["1 = 1"]
        parameters: list[str | int] = []
        if match:
            conditions.append(
                "r.id IN (SELECT restaurant_id FROM restaurant_search WHERE restaurant_search MATCH ?)"
            )
            parameters.append(match)
        if status:
            conditions.append("p.status = ?")
            parameters.append(status)
        if favorite_only:
            conditions.append("p.favorite = 1")
        filtered = SELECT_RECORD + " WHERE " + " AND ".join(conditions)
        with self.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM (" + filtered + ")", parameters
            ).fetchone()[0]
            rows = connection.execute(
                filtered + " ORDER BY v.name COLLATE NOCASE, r.id LIMIT ? OFFSET ?",
                (*parameters, limit, offset),
            ).fetchall()
        return RestaurantPage(
            data=[self.record(row) for row in rows],
            meta={"total": total, "limit": limit, "offset": offset},
        )

    def update_personal(self, restaurant_id: str, payload: PersonalInput) -> Restaurant | None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            changed = connection.execute(
                """
                UPDATE user_places SET favorite = ?, status = ?, personal_rating = ?, notes = ?,
                    revision = revision + 1, updated_at = ?
                WHERE restaurant_id = ? AND revision = ?
            """,
                (
                    payload.favorite,
                    payload.status,
                    payload.personal_rating,
                    payload.notes,
                    now,
                    restaurant_id,
                    payload.revision,
                ),
            )
            if changed.rowcount == 0:
                exists = connection.execute(
                    "SELECT 1 FROM user_places WHERE restaurant_id = ?", (restaurant_id,)
                ).fetchone()
                if exists:
                    raise EditConflict
                return None
            connection.execute(
                "INSERT INTO user_place_versions "
                "SELECT restaurant_id, revision, favorite, status, personal_rating, notes, updated_at "
                "FROM user_places WHERE restaurant_id = ?",
                (restaurant_id,),
            )
            row = connection.execute(SELECT_RECORD + " WHERE r.id = ?", (restaurant_id,)).fetchone()
        return self.record(row)
