"""FastAPI application — the Shape A cloud API.

Mounts:
  * /health and /version   public liveness + build info
  * /v1/jobs               replication job orchestration (Phase A2)
  * /v1/upload             tus protocol resumable upload (Phase A1)
  * /v1/git                git-based ingestion (Phase A1)
  * /v1/auth               WorkOS callback + session (Phase A4)
  * /v1/cutover            strangler-fig facade control (Phase B3)
  * /ws/jobs/{id}          WebSocket gate-progress stream (Phase A2)
"""

from __future__ import annotations

import importlib.metadata
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from omnix.cloud.config import get_settings


def _omnix_version() -> str:
    try:
        return importlib.metadata.version("omnix")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0-dev"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="OMNIX Cloud Orchestrator",
        version=_omnix_version(),
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [settings.cloud_api_base_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    try:
        from omnix.cloud.auth.tenancy import TenancyMiddleware  # noqa: WPS433
        app.add_middleware(TenancyMiddleware)
    except Exception:  # pragma: no cover
        pass

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}

    @app.get("/version", tags=["meta"])
    async def version() -> dict[str, str]:
        return {
            "omnix": _omnix_version(),
            "env": settings.env,
        }

    # Sub-routers — each guarded so unimported modules don't fail startup.
    try:
        from omnix.cloud.api import jobs as jobs_router  # noqa: WPS433
        app.include_router(jobs_router.router, prefix="/v1/jobs", tags=["jobs"])
    except Exception:  # pragma: no cover
        pass

    try:
        from omnix.cloud.api import upload as upload_router  # noqa: WPS433
        app.include_router(upload_router.router, prefix="/v1/upload", tags=["upload"])
    except Exception:  # pragma: no cover
        pass

    try:
        from omnix.cloud.api import git_ingest as git_router  # noqa: WPS433
        app.include_router(git_router.router, prefix="/v1/git", tags=["git"])
    except Exception:  # pragma: no cover
        pass

    try:
        from omnix.cloud.api import auth as auth_router  # noqa: WPS433
        app.include_router(auth_router.router, prefix="/v1/auth", tags=["auth"])
    except Exception:  # pragma: no cover
        pass

    try:
        from omnix.cloud.api import ws as ws_router  # noqa: WPS433
        app.include_router(ws_router.router, tags=["ws"])
    except Exception:  # pragma: no cover
        pass

    try:
        from omnix.cloud.api import cutover as cutover_router  # noqa: WPS433
        app.include_router(cutover_router.router, prefix="/v1/cutover", tags=["cutover"])
    except Exception:  # pragma: no cover
        pass

    try:
        from omnix.cloud.api import github_callback as gh_router  # noqa: WPS433
        app.include_router(gh_router.router, prefix="/v1/callback", tags=["callback"])
    except Exception:  # pragma: no cover
        pass

    try:
        from omnix.cloud.api import stripe_webhook as stripe_router  # noqa: WPS433
        app.include_router(stripe_router.router, prefix="/v1/billing", tags=["billing"])
    except Exception:  # pragma: no cover
        pass

    try:
        from omnix.cloud.verify_page import app as verify_app  # noqa: WPS433
        app.mount("/verify", verify_app)
    except Exception:  # pragma: no cover
        pass

    return app


app = create_app()
