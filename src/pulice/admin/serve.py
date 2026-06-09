"""textual-serve integration for mounting the admin TUI on FastAPI.

textual-serve currently runs as a standalone server and does not support
ASGI sub-mounting into an existing FastAPI app.  This module provides a
placeholder ``mount_admin`` that registers a redirect endpoint pointing
operators to the standalone textual-serve URL, and a ``serve_admin``
helper that launches the TUI as its own HTTP server.
"""

from __future__ import annotations
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse


def mount_admin(fastapi_app: FastAPI) -> None:
    """Register an /admin endpoint that explains how to launch the dashboard.

    Since textual-serve cannot be embedded as ASGI middleware, this
    endpoint returns instructions for running the standalone server.
    """

    @fastapi_app.get('/admin')
    def admin_info() -> PlainTextResponse:
        return PlainTextResponse(
            'The admin dashboard runs as a standalone server.\n'
            'Launch it with:\n\n'
            '  pulice admin\n\n'
            'Or serve in the browser with:\n\n'
            '  python -m pulice.admin.serve\n'
        )


def serve_admin(
    state_dir: str | None = None,
    host: str = 'localhost',
    port: int = 8080,
) -> None:
    """Launch the admin TUI as a browser-accessible server via textual-serve."""
    from textual_serve.server import Server

    command = 'python -m pulice.admin'
    if state_dir:
        command += f' {state_dir}'
    server = Server(command, host=host, port=port, title='Pulice Admin')
    server.serve()
