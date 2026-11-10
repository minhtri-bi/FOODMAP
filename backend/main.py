"""Local-only API. No cloud calls, scraping or account access occurs in this slice."""

import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.database import EditConflict, Store, UnknownOsmPlace
from backend.discovery import DiscoveryPage, search_places
from backend.schemas import (
    PersonalInput,
    PlaceStatus,
    RestaurantCreate,
    RestaurantPage,
    RestaurantResult,
)

LOGGER = logging.getLogger("foodroute")
DEFAULT_DATABASE = Path(__file__).resolve().parents[1] / "data" / "foodroute.sqlite3"
ALLOWED_ORIGINS = frozenset(
    {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    }
)
MAX_BODY_BYTES = 32_768


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(database_path: Path | None = None) -> FastAPI:
    store = Store(database_path or Path(os.environ.get("FOODROUTE_DATABASE", DEFAULT_DATABASE)))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.initialize()
        yield

    app = FastAPI(title="FoodRoute local API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin is not None and origin not in ALLOWED_ORIGINS:
                return error_response(403, "origin_denied", "This origin cannot edit local data.")
            if request.headers.get("x-foodroute-request") != "1":
                return error_response(
                    403, "request_header_required", "Use the FoodRoute app to edit data."
                )
            if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
                return error_response(415, "json_required", "Send application/json.")
            length = request.headers.get("content-length", "")
            if not length.isdecimal():
                return error_response(411, "length_required", "A valid Content-Length is required.")
            if int(length) > MAX_BODY_BYTES:
                return error_response(
                    413, "body_too_large", "This edit exceeds the input size limit."
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Check the highlighted input fields.",
                    "details": details,
                }
            },
        )

    @app.exception_handler(sqlite3.Error)
    async def database_error(_: Request, exc: sqlite3.Error):
        LOGGER.error("SQLite operation failed (%s)", type(exc).__name__)
        return error_response(
            503,
            "storage_unavailable",
            "Local storage is unavailable. Retry after checking the application data directory.",
        )

    @app.exception_handler(HTTPException)
    async def api_error(_: Request, exc: HTTPException):
        return error_response(exc.status_code, "request_failed", str(exc.detail))

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        with store.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok", "mode": "local-only"}

    @app.get("/api/v1/discovery", response_model=DiscoveryPage)
    def discover(
        q: Annotated[str, Query(max_length=200)] = "",
        latitude: Annotated[float | None, Query(ge=-90, le=90, allow_inf_nan=False)] = None,
        longitude: Annotated[float | None, Query(ge=-180, le=180, allow_inf_nan=False)] = None,
        limit: Annotated[int, Query(ge=1, le=30)] = 10,
    ) -> DiscoveryPage:
        if (latitude is None) != (longitude is None):
            raise HTTPException(422, "Provide both manual origin coordinates or neither.")
        with store.connect() as connection:
            return search_places(connection, q, latitude, longitude, limit)

    @app.get("/api/v1/restaurants", response_model=RestaurantPage)
    def list_restaurants(
        q: Annotated[str, Query(max_length=200)] = "",
        status: PlaceStatus | None = None,
        favorite_only: bool = False,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    ) -> RestaurantPage:
        return store.list(q, status, favorite_only, limit, offset)

    @app.get("/api/v1/restaurants/{restaurant_id}", response_model=RestaurantResult)
    def get_restaurant(restaurant_id: str) -> RestaurantResult:
        restaurant = store.get(restaurant_id)
        if restaurant is None:
            raise HTTPException(404, "Restaurant not found.")
        return RestaurantResult(data=restaurant)

    @app.post("/api/v1/restaurants", response_model=RestaurantResult, status_code=201)
    def add_restaurant(payload: RestaurantCreate, response: Response) -> RestaurantResult:
        try:
            restaurant = store.create(payload)
        except UnknownOsmPlace as exc:
            raise HTTPException(422, "This OSM record is not in the local index. Search again or use manual entry.") from exc
        except sqlite3.IntegrityError as exc:
            if ("UNIQUE constraint failed: restaurant_versions" in str(exc)
                    or "UNIQUE constraint failed: source_osm_evidence" in str(exc)):
                raise HTTPException(409, "This exact branch is already saved.") from exc
            raise
        response.headers["Location"] = f"/api/v1/restaurants/{restaurant.id}"
        return RestaurantResult(data=restaurant)

    @app.put("/api/v1/restaurants/{restaurant_id}/personal", response_model=RestaurantResult)
    def save_personal(restaurant_id: str, payload: PersonalInput) -> RestaurantResult:
        try:
            restaurant = store.update_personal(restaurant_id, payload)
        except EditConflict as exc:
            raise HTTPException(
                409,
                "A newer edit exists. Reload the restaurant before saving; your draft has not been overwritten.",
            ) from exc
        if restaurant is None:
            raise HTTPException(404, "Restaurant not found.")
        return RestaurantResult(data=restaurant)

    return app


app = create_app()
