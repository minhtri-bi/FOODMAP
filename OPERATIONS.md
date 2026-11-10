# FoodRoute local application

## Implemented journey

The personal collection supports manual branch/address/coordinate confirmation, durable SQLite storage, local name/address search, list and favorite filters, and versioned private ratings/notes. Personal ratings are not Google ratings. Empty collections contain no seeded records. Manual data and private notes are not sent to cloud services.

Regional OSM discovery and an opt-in manual pin map are connected. The Google scraper feasibility test remains separate from the application. Google ratings/photos, network routing, menu extraction, AI answers, Takeout import, phone HTTPS and recovery/export workflows are not connected. The native roadmap remains the source of task status; these are not hidden exclusions from final scope.

## Environment and locked setup

Exercised on Windows with Node 24.14.0, npm 11.18.0 and uv 0.11.33. uv selected Python 3.12.14 for the isolated project environment; the global Python installation was not modified. Compatible npm packages are pinned in `package.json`/`package-lock.json`; Python resolution is pinned in `uv.lock`.

From the repository root:

```text
npm ci
uv sync --locked
```

Dependency installation was exercised through `npm install --save-exact` and `uv add`; the lock-based commands above are the reproducible reinstall equivalents. No global dependency installation is required.

## Launch

Use two terminals from the repository root:

```text
uv run --locked uvicorn backend.main:app --host 127.0.0.1 --port 8000
npm run dev -- --port 5173
```

Open `http://127.0.0.1:5173`. The frontend proxies `/api` to the local backend. Ports are strict: a collision fails rather than silently selecting another port. Do not bind these unauthenticated personal services to a public interface or expose them through a tunnel. Phone access is intentionally not configured yet.

The backend initializes `data/foodroute.sqlite3` by default, independently of the current working directory. `FOODROUTE_DATABASE` can select an explicit database path before process launch. Database files, local environments, private exports and secrets are ignored by Git. The app stores source permissions, identity versions and personal edit history separately. It does not create location history or cache external Google records.

## Exercise and checks

```text
npm run build
uv run pytest backend/tests -q
uv run ruff check backend
```

The browser acceptance adds a real restaurant through the form, saves private preferences, restarts the actual API process, reloads the UI and checks the same persisted values. Mobile-width reflow is a desktop browser emulation, not proof of phone HTTPS/GPS. Automated API tests cover restart persistence, stale-edit protection, duplicates versus distinct branches, coordinate/confirmation validation, oversized edit revisions and cross-origin write rejection.

Starlette currently emits an upstream deprecation warning for its httpx-backed test client. Tests pass; the warning is not suppressed or described as a runtime failure.

## Stop and process ownership

In a normal terminal use Ctrl+C in each application terminal. Do not kill all Python/Node processes.

The current OMP-owned services are `foodroute-frontend-d1` and `foodroute-backend-d1`, launched with the commands above and readiness checks on ports 5173 and 8000. The earlier D0 handles were already exited on resume; no unrelated processes were stopped. Stop only the exact live tool handle with `proc://<service>/kill`.

## Data safety and current boundaries

- Confirm the exact branch and decimal-degree coordinates before saving. Local OSM name/address suggestions fill a draft, not a verified identity. Missing addresses require manual entry.
- Duplicate exact identities or an already saved OSM source identity return a conflict, rather than merging similar restaurant names.
- Personal edits carry a revision. A stale revision cannot overwrite a newer edit. The form retains its draft after an error; reload the latest revision, inspect the draft and save deliberately.
- Navigation warns before discarding unsaved panel changes. Navigation is disabled while a save is pending.
- API writes require JSON, a bounded declared content length, the app request header and an allowed browser origin. Trusted loopback hosts are enforced. This is a local-browser boundary, not multi-user authentication.
- No raw database export/restore capability is claimed. Until U0 supplies a tested recovery flow, do not treat copying a live SQLite file as a verified backup strategy.

## Regional OSM discovery and pins

The exercised import command is:

```text
uv run --locked python -m backend.import_osm data/vietnam-261108.osm.pbf
```

The existing local PBF stays outside Git. Do not redownload or substitute a newer extract implicitly. This pinned importer expects MD5 `06e54d5e1726ea3aac340b8272ffd26d`, source `https://download.geofabrik.de/asia/vietnam-261108.osm.pbf`, and snapshot `2026-11-08T21:21:00Z`. The last successful import produced 4,553 named food venues.

The pilot rectangle is latitude 10.35–11.2 and longitude 106.2–107.1, not an administrative Ho Chi Minh City boundary. Coverage is incomplete: named restaurant/cafe/fast-food/food-court nodes and approximate way centers only; relation-only venues are omitted. Missing names/addresses and stale source data remain possible. Data attribution is © OpenStreetMap contributors, ODbL-1.0; preserve source IDs, date and license when reusing this dataset.

Search uses local SQLite FTS5. Both manual origin coordinates are optional together; they bias ordering without a radius cutoff. Distant matches remain searchable. Distances are straight-line estimates, never route distance, ETA or traffic evidence. Search does not call Google or public Nominatim.

Selecting a result fills the branch form. Saving requires name/address, valid coordinates and explicit branch confirmation. Coordinate or identity edits reset confirmation. Saved records retain the original OSM identity, source URL, date, license and evidence separately from the confirmed identity and private preferences.

The map requests no external tiles until **Load map**. Loading, panning and zooming disclose the visible map area and IP address to OpenStreetMap's tile service. Only normal visible tiles are requested; no offline prefetch or GPS is used. Click to set a draft pin, or use the decimal inputs as the keyboard alternative. If tiles fail, keep the draft and use decimal coordinates; do not infer a successful map load.

Current-run browser acceptance exercised nearby ordering, a distant origin retaining matches over 1,100 km away, branch-confirmation blocking/reset, a saved OSM branch and provenance after reload, no-match manual map/keyboard pins, and a 390px mobile viewport without horizontal overflow. The prior D0 favorite, tried state, personal rating and notes remained intact. One real OSM-backed acceptance record was added to the local collection; no synthetic no-match record was saved.

Before the first application checkpoint push, an isolated copy of the exact staged D0/D1 snapshot passed `npm run build`, `uv run ruff check backend`, and `uv run pytest backend/tests -q` (11 passed). Existing dependencies were reused without reinstalling. The build reported a chunk larger than 500 kB; the test-client deprecation warning remains unsuppressed. Unfinished routing additions were excluded from this snapshot. Desktop browser emulation does not prove phone HTTPS or real GPS access.

## Regional routing preparation

The local tooling image is built with `docker build --file routing.Dockerfile --tag foodroute-routing-tools:3.9.1-osmium1.16.0 .`. The Docker build context excludes application data and all files except the Dockerfile and ignore policy. The base is the official Valhalla 3.9.1 Linux amd64 image pinned to `sha256:18cb42988e03c70dc4bc4ca095a259ec4db5e5df928be65956fc1c64c280b47a`; the added native extractor is `osmium-tool=1.16.0-1build1`. No host-global package was installed.

The real regional extraction completed with Osmium `extract -b 106.2,10.35,107.1,11.2 -s smart -S types=restriction`, using the existing PBF read-only and writing `data/routing/pilot.osm.pbf`. It retained original OSM IDs, complete ways and completed restriction relations. The resulting PBF is about 29.2 MB, SHA-256 `b7bd5de6007245d933e01d9408c427c74f45fa9e8bc55267c2c64ee8da08d165`. This is not a full-Vietnam routing graph.

For a fresh routing directory, `uv run --locked python -m backend.prepare_routing data/vietnam-261108.osm.pbf data/routing` wraps that same bounded native command and records source provenance. It refuses existing artifacts instead of replacing them. Do not rerun it over the prepared data. Container limits are 2 CPUs, 4 GiB memory with no extra swap, finite PIDs and no network; an extraction timeout stops only its owned container. Initial Python-level scans exceeded the deadline/node bound and were replaced by the native extractor, not presented as successful imports.

The source is incomplete at region boundaries. The administrative metadata build reported incomplete country boundaries, including Vietnam; those warnings are not proof of correct country-specific motorized access. No profile is enabled until real regional route checks pass. Graph construction, profile acceptance and application route behavior remain R0 gates, independently of this completed extraction.

## Version control

Publish coherent, exercised implementation slices to the existing `main` branch rather than waiting for one final bulk push or creating an automatic PR. Unfinished work stays outside completed checkpoints. Use ordinary pushes; do not rewrite shared history or bypass branch protections.

The source repository is public. Local `.omp/` workstation/task metadata, `data/`, private SQLite records/exports/notes, PBF/routing artifacts, secrets, environments and dependency directories are excluded from Git. Source publication is not permission to deploy the personal application publicly.

## Change record

- Added runnable React/TypeScript/Vite and FastAPI/SQLite personal collection.
- Added confirmed manual identities, separate provenance/history, private preferences and optimistic edit revisions.
- Added responsive labels/focus/unknown states and local browser request boundaries.
- Preserved the explicitly requested removal of the initial GitHub README; no replacement README was created.
- Added pinned regional OSM import, local origin-ranked discovery, opt-in Leaflet pins and separate original OSM evidence.
- Exercised D1 on the real local API/UI while preserving the existing personal collection.
