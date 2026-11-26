"""FastAPI application factory.

Run locally:

    cd backend
    uvicorn app.main:app --reload --port 8000

Interactive documentation is served at ``/docs`` (Swagger UI) and ``/redoc``.
A machine-readable OpenAPI document is committed at
``docs/api/openapi.json`` — regenerate it with ``python -m scripts.export_openapi``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import (
    routes_auth,
    routes_buyers,
    routes_crops,
    routes_farms,
    routes_finance,
    routes_forecasts,
    routes_markets,
    routes_reports,
    routes_weather,
)
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging_config import configure_logging
from app.database import init_db
from app.middleware.security_headers import RequestIdMiddleware, SecurityHeadersMiddleware
from app.schemas import HealthResponse
from app.services import ml_client
from app.services.seed_service import seed_reference_data

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: validate config, ensure schema, seed reference data."""
    configure_logging()
    settings.validate_runtime()

    if settings.environment != "testing":
        init_db()
        try:
            seed_reference_data()
        except Exception as exc:  # pragma: no cover - startup resilience
            logger.error("reference-data seeding failed: %s", exc)

    logger.info(
        "AgriPredict API %s starting (environment=%s, debug=%s)",
        __version__,
        settings.environment,
        settings.debug,
    )
    yield
    logger.info("AgriPredict API shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        description=(
            "Backend for the AgriPredict Android application: farm records, "
            "finances, market prices, price forecasts, weather and buyer discovery."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={"name": "AgriPredict team"},
        license_info={"name": "MIT"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex_or_none,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # ------------------------------------------------------------------
    # Error handling — one envelope shape for every failure mode
    # ------------------------------------------------------------------
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "One or more fields are invalid.",
                    "details": {
                        "fields": [
                            {
                                "field": ".".join(str(p) for p in err["loc"][1:]) or err["loc"][0],
                                "message": err["msg"],
                            }
                            for err in exc.errors()
                        ]
                    },
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback but never leak internals to the client.
        logger.exception("unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred. Please try again.",
                }
            },
        )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    prefix = settings.api_v1_prefix
    for router in (
        routes_auth.router,
        routes_farms.router,
        routes_crops.router,
        routes_markets.router,
        routes_forecasts.router,
        routes_weather.router,
        routes_buyers.router,
        routes_finance.router,
        routes_reports.router,
    ):
        app.include_router(router, prefix=prefix)

    # ------------------------------------------------------------------
    # Meta endpoints (unversioned on purpose: probes do not care about v1)
    # ------------------------------------------------------------------
    @app.get("/", tags=["meta"], summary="Service identity")
    def root() -> dict:
        return {
            "service": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "api": prefix,
        }

    @app.get("/health", response_model=HealthResponse, tags=["meta"], summary="Health probe")
    def health() -> HealthResponse:
        database = "ok"
        try:
            from sqlalchemy import text

            from app.database import engine

            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.error("database health check failed: %s", exc)
            database = "error"

        if not ml_client.is_ml_service_configured():
            ml_state = "disabled"
        else:
            ml_state = "ok" if ml_client.health_check() else "unavailable"

        overall = "ok" if database == "ok" else "degraded"
        return HealthResponse(
            status=overall,
            version=__version__,
            environment=settings.environment,
            database=database,
            ml_service=ml_state,  # type: ignore[arg-type]
        )

    return app


app = create_app()
