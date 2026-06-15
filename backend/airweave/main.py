"""Main module of the FastAPI application.

This module sets up the FastAPI application and the middleware to log incoming requests
and unhandled exceptions.
"""

import os
import subprocess
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from airweave.api.middleware import (
    DynamicCORSMiddleware,
    add_request_id,
    airweave_exception_handler,
    analytics_middleware,
    exception_logging_middleware,
    http_metrics_middleware,
    invalid_input_exception_handler,
    invalid_state_exception_handler,
    log_requests,
    not_found_exception_handler,
    permission_exception_handler,
    rate_limit_exception_handler,
    rate_limit_headers_middleware,
    request_body_size_middleware,
    request_timeout_middleware,
    validation_exception_handler,
)
from airweave.api.router import TrailingSlashRouter
from airweave.api.v1.api import api_router
from airweave.core.config import settings
from airweave.core.exceptions import (
    AirweaveException,
    InvalidInputError,
    InvalidStateError,
    NotFoundException,
    PermissionException,
    RateLimitExceededException,
)
from airweave.core.logging import logger
from airweave.db.init_db import init_db
from airweave.db.session import AsyncSessionLocal
from airweave.domains.embedders.config import validate_embedding_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events.

    Initializes the DI container, runs alembic migrations, and syncs platform components.
    """
    # Initialize the dependency injection container (fail fast if wiring is broken)
    from airweave.core import container as container_mod  # noqa: PLC0415
    from airweave.core.container import initialize_container  # noqa: PLC0415

    logger.info("Initializing dependency injection container...")
    initialize_container(settings)
    logger.info("Container initialized successfully")

    async with AsyncSessionLocal() as db:
        if settings.RUN_ALEMBIC_MIGRATIONS:
            logger.info("Running alembic migrations...")
            env = os.environ.copy()
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env["PYTHONPATH"] = backend_dir
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                check=True,
                cwd=backend_dir,
                env=env,
            )
        await init_db(db)

        # Reconcile embedding config against DB deployment metadata
        await validate_embedding_config(db)

    # Initialize system-level Temporal schedules (cleanup, API key notifications)
    try:
        logger.info("Initializing system Temporal schedules...")
        await container_mod.container.temporal_schedule_service.ensure_system_schedules()
        logger.info("System Temporal schedules initialized successfully")
    except Exception as e:
        logger.warning(
            f"Failed to initialize system schedules (Temporal may not be available): {e}"
        )

    # Start metrics sidecar + DB pool sampler; wire app.state.http_metrics
    from airweave.core.metrics_service import metrics_lifespan  # noqa: PLC0415
    from airweave.db.session import async_engine  # noqa: PLC0415

    async with metrics_lifespan(app, container_mod.container.metrics, async_engine.pool):
        yield

    container_mod.container.health.shutting_down = True

    # Clean up health check engine connections
    from airweave.db.session import health_check_engine  # noqa: PLC0415

    await health_check_engine.dispose()


# Create FastAPI app with our custom router and disable FastAPI's built-in redirects
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/openapi.json",
    lifespan=lifespan,
    router=TrailingSlashRouter(),
    redirect_slashes=False,  # Critical: disable FastAPI's built-in slash redirects
)

app.include_router(api_router)

# Register middleware directly in the correct order.
# Order matters: first registered = outermost (processes request first).
# http_metrics_middleware is intentionally early so it captures
# end-to-end latency and counts 413/408/429 responses generated
# by inner middlewares (body-size, timeout, rate-limit).
app.middleware("http")(add_request_id)
app.middleware("http")(http_metrics_middleware)
app.middleware("http")(request_body_size_middleware)
app.middleware("http")(request_timeout_middleware)
app.middleware("http")(rate_limit_headers_middleware)
app.middleware("http")(log_requests)
app.middleware("http")(analytics_middleware)
app.middleware("http")(exception_logging_middleware)

# Register exception handlers
app.exception_handler(RequestValidationError)(validation_exception_handler)
app.exception_handler(ValidationError)(validation_exception_handler)
app.exception_handler(PermissionException)(permission_exception_handler)
app.exception_handler(NotFoundException)(not_found_exception_handler)
app.exception_handler(RateLimitExceededException)(rate_limit_exception_handler)
app.exception_handler(InvalidStateError)(invalid_state_exception_handler)
app.exception_handler(InvalidInputError)(invalid_input_exception_handler)

# Register custom Airweave exception handlers
app.exception_handler(AirweaveException)(airweave_exception_handler)

# Default CORS origins - white labels and environment variables can extend this
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "localhost:8001",
    "http://localhost:8080",
    "https://app.dev-airweave.com",
    "https://app.stg-airweave.com",
    "https://app.airweave.ai",
    "https://connect.dev-airweave.com",
    "https://docs.airweave.ai",
    "localhost:3000",
]

if settings.ADDITIONAL_CORS_ORIGINS:
    origins = settings.ADDITIONAL_CORS_ORIGINS
    additional_origins = origins.split(",") if isinstance(origins, str) else origins
    if settings.ENVIRONMENT == "local":
        CORS_ORIGINS.append("*")
    else:
        CORS_ORIGINS.extend(additional_origins)

# Add the dynamic CORS middleware that handles both default origins and white label specific origins
app.add_middleware(
    DynamicCORSMiddleware,
    default_origins=CORS_ORIGINS,
)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def show_docs_reference() -> HTMLResponse:
    """Root endpoint to display the API documentation.

    Returns:
    -------
        HTMLResponse: The HTML content to display the API documentation.

    """
    html_content = """
<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="utf-8" />
        <title>Gooclaim OS Data Connector — API</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
            :root {
                color-scheme: light dark;
                --bg: #f8fafc;
                --card: #ffffff;
                --ink: #0f172a;
                --muted: #475569;
                --brand: #0369A1;
                --brand-hover: #075985;
                --border: #e2e8f0;
            }
            @media (prefers-color-scheme: dark) {
                :root {
                    --bg: #020617;
                    --card: #0f172a;
                    --ink: #f1f5f9;
                    --muted: #94a3b8;
                    --brand: #38bdf8;
                    --brand-hover: #7dd3fc;
                    --border: #1e293b;
                }
            }
            * { box-sizing: border-box; }
            body {
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                             Roboto, "Helvetica Neue", Arial, sans-serif;
                background: var(--bg);
                color: var(--ink);
                min-height: 100vh;
                display: grid;
                place-items: center;
                padding: 32px;
            }
            .card {
                width: min(560px, 100%);
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 40px 36px;
                box-shadow: 0 1px 2px rgba(15,23,42,0.04),
                            0 12px 32px rgba(15,23,42,0.08);
            }
            .eyebrow {
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: var(--muted);
                margin-bottom: 12px;
            }
            h1 {
                font-size: 28px;
                line-height: 1.2;
                margin: 0 0 8px;
                font-weight: 700;
            }
            p {
                margin: 0 0 20px;
                color: var(--muted);
                line-height: 1.55;
            }
            .links {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
                margin-top: 24px;
            }
            a.btn {
                display: block;
                padding: 12px 16px;
                border-radius: 10px;
                text-decoration: none;
                font-size: 14px;
                font-weight: 600;
                text-align: center;
                transition: background 0.15s ease, color 0.15s ease;
            }
            a.btn.primary {
                background: var(--brand);
                color: #ffffff;
            }
            a.btn.primary:hover { background: var(--brand-hover); }
            a.btn.ghost {
                background: transparent;
                color: var(--brand);
                border: 1px solid var(--border);
            }
            a.btn.ghost:hover {
                color: var(--brand-hover);
                border-color: var(--brand);
            }
            .meta {
                margin-top: 24px;
                padding-top: 20px;
                border-top: 1px solid var(--border);
                display: flex;
                justify-content: space-between;
                font-size: 12px;
                color: var(--muted);
            }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="eyebrow">Gooclaim OS</div>
            <h1>Data Connector API</h1>
            <p>
                The unified retrieval surface behind Gooclaim Data Sources —
                connect any system, index its content, query it from anywhere
                in the platform.
            </p>
            <div class="links">
                <a class="btn primary" href="/api/docs">Interactive API (Swagger)</a>
                <a class="btn ghost" href="/api/redoc">Reference (ReDoc)</a>
            </div>
            <div class="meta">
                <span>docs.gooclaim.com</span>
                <span>v1</span>
            </div>
        </div>
    </body>
</html>
    """
    return HTMLResponse(content=html_content)
