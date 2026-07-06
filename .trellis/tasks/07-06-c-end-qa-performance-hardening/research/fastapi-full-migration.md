# FastAPI 全量迁移研究记录

## Sources

* FastAPI Server-Sent Events docs: https://fastapi.tiangolo.com/tutorial/server-sent-events/
* FastAPI Static Files docs: https://fastapi.tiangolo.com/tutorial/static-files/
* FastAPI Request Files docs: https://fastapi.tiangolo.com/tutorial/request-files/
* FastAPI Testing docs: https://fastapi.tiangolo.com/tutorial/testing/
* FastAPI Bigger Applications docs: https://fastapi.tiangolo.com/tutorial/bigger-applications/
* FastAPI Server Workers docs: https://fastapi.tiangolo.com/deployment/server-workers/
* Starlette Responses docs: https://starlette.dev/responses/
* Starlette StaticFiles docs: https://starlette.dev/staticfiles/
* Starlette TestClient docs: https://starlette.dev/testclient/

## Findings

* SSE is a first-class FastAPI use case for AI chat streaming. Current event payloads can be reused if the route yields the existing event dictionaries or preformatted event strings.
* FastAPI/Starlette can serve static files by mounting `StaticFiles`; the existing Vite output under `cyclops/static/dist` can move from manual `static_path()` handling to an ASGI static mount plus explicit root/index route.
* Upload routes should use `UploadFile`, not raw multipart parsing. FastAPI requires `python-multipart` for file uploads.
* Tests can use `fastapi.testclient.TestClient`, which comes from Starlette. For lifespan/startup behavior, the client should be used as a context manager.
* Large FastAPI apps should split routes by domain with `APIRouter`, then include routers in the main app. This maps well to current domains: settings, import, FAQ, assistant, retrieval evaluation, KG, analytics, static/downloads.
* Uvicorn/FastAPI can run multiple workers, but worker count multiplies per-process resources. DB pools and model concurrency limits must be sized with worker count in mind.

## Repo Mapping

* `AdminApp` already contains most business methods. A practical migration can keep `AdminApp` as the service facade first, while moving HTTP parsing/routing from `make_handler()` to FastAPI routers.
* Current custom helpers still matter:
  * `classify_error_response()` for consistent error bodies.
  * `format_sse_event()` for stream compatibility.
  * `safe_upload_name()` and `ensure_upload_path_within()` for file safety.
  * download/asset handling currently implemented in `get_import_file_for_download()` and `get_import_asset()`.
* The migration should avoid duplicating business logic. Route handlers should be thin adapters from FastAPI request objects to `AdminApp` methods.

## Recommended Migration Shape

1. Add `cyclops/asgi_app.py` as app factory and shared dependency container.
2. Add routers under `cyclops/api/` by domain.
3. Keep `AdminApp` as a temporary service facade until routing is migrated and covered by tests.
4. Add `cyclops api` or `cyclops admin --asgi` startup path with Uvicorn.
5. Keep the old `admin` server available during this task unless the user explicitly chooses immediate replacement.

## Risks

* Full migration is broad: every manual route in `admin_server.py` needs parity tests or at least focused route smoke tests.
* File upload and download behavior can drift if `Content-Disposition`, filename encoding, and request size limits are not preserved.
* Blocking model calls inside async routes can still block if implemented incorrectly. Route handlers should use sync endpoints or explicit thread offloading for existing sync service methods until clients are made fully async.
* Multiple Uvicorn workers multiply DB connections and model concurrency. Defaults must be conservative.
