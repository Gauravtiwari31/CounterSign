import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import embeddings, worker
from app.api import (
    routes_admin,
    routes_auth,
    routes_demo,
    routes_drafts,
    routes_export,
    routes_health,
    routes_review,
    routes_workflow,
)
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("countersign")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(embeddings.warm)
    task = asyncio.create_task(worker.loop()) if get_settings().run_worker else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Countersign", version="2.0.0", lifespan=lifespan,
              description="Brand governance: rules, claims and voice review with a countersign workflow.")

for r in (routes_health, routes_auth, routes_demo, routes_drafts, routes_review, routes_workflow, routes_admin,
          routes_export):
    app.include_router(r.router)

_origins = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


STATIC = (Path(__file__).resolve().parent.parent / get_settings().static_dir).resolve()
if (STATIC / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = STATIC / path
        if path and f.is_file() and STATIC in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(STATIC / "index.html")
