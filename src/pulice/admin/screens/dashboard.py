"""Dashboard screen — summary view with key metrics."""

from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static
from pulice.admin.widgets.stat_card import StatCard

if __name__ != '__main__':
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from pulice.admin.data import AdminDataSource


class DashboardScreen(Static):
    """Summary dashboard showing key metrics at a glance."""

    DEFAULT_CSS = """
    DashboardScreen {
        height: 1fr;
        padding: 1 2;
    }
    DashboardScreen .metrics-row {
        height: 7;
        margin-bottom: 1;
    }
    DashboardScreen .info-section {
        height: auto;
        padding: 1;
    }
    """

    def __init__(self, data_source: 'AdminDataSource') -> None:
        super().__init__()
        self._data = data_source

    def compose(self) -> ComposeResult:
        with Horizontal(classes='metrics-row'):
            yield StatCard('Tenants', '0', id='stat-tenants')
            yield StatCard('Stacks', '0', id='stat-stacks')
            yield StatCard('Active Locks', '0', id='stat-locks')
        with Horizontal(classes='metrics-row'):
            yield StatCard('Pending Tasks', '—', id='stat-pending')
            yield StatCard('Running Tasks', '—', id='stat-running')
            yield StatCard('Failed Tasks', '—', id='stat-failed')
        with Vertical(classes='info-section'):
            yield Static(id='system-info')

    def refresh_data(self) -> None:
        info = self._data.get_system_info()
        self.query_one('#stat-tenants', StatCard).update_value(str(info['tenant_count']))
        self.query_one('#stat-stacks', StatCard).update_value(str(info['stack_count']))
        self.query_one('#stat-locks', StatCard).update_value(str(info['lock_count']))

        info_text = (
            f'[bold]Pulice[/bold] v{info["version"]}  |  '
            f'Backend: {info["task_backend"]}  |  '
            f'State: {info["state_dir"]}'
        )
        self.query_one('#system-info', Static).update(info_text)
