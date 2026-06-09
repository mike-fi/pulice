"""Pulice FastAPI application factory."""

from __future__ import annotations
from fastapi import FastAPI
from pulice.api.routes_stacks import router as stack_router
from pulice.api.routes_tasks import router as task_router
from pulice.api.routes_tenants import router as tenant_router


def create_api() -> FastAPI:
    """Create and configure the Pulice API application."""
    app = FastAPI(title='Pulice API', version='0.1.0')
    app.include_router(tenant_router, prefix='/tenants', tags=['tenants'])
    app.include_router(stack_router, prefix='/stacks', tags=['stacks'])
    app.include_router(task_router, prefix='/tasks', tags=['tasks'])

    try:
        import textual  # noqa: F401  # pyrefly: ignore
        from pulice.admin.serve import mount_admin

        mount_admin(app)
    except ImportError:
        pass

    return app
