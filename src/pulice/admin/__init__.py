"""Pulice Admin TUI — terminal and browser dashboard."""

from __future__ import annotations


def create_admin_app(
    state_dir: str | None = None,
    refresh_interval: int = 5,
) -> 'PuliceAdmin':  # noqa: F821  # pyrefly: ignore
    """Create and return the admin TUI application."""
    from pulice.admin.app import PuliceAdmin

    return PuliceAdmin(state_dir=state_dir, refresh_interval=refresh_interval)
