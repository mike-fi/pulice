"""PuliceAdmin — main Textual application for the admin TUI."""

from __future__ import annotations
from pathlib import Path
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, TabbedContent, TabPane
from pulice.admin.data import AdminDataSource
from pulice.admin.screens.dashboard import DashboardScreen
from pulice.admin.screens.stacks import StacksScreen
from pulice.admin.screens.system import SystemScreen
from pulice.admin.screens.tasks import TasksScreen
from pulice.admin.screens.tenants import TenantsScreen

CSS_PATH = Path(__file__).parent / 'styles' / 'app.tcss'


class PuliceAdmin(App):
    """Pulice administrative dashboard TUI."""

    TITLE = 'Pulice Admin'
    CSS_PATH = CSS_PATH
    BINDINGS = [
        Binding('1', "switch_tab('dashboard')", 'Dashboard', show=False),
        Binding('2', "switch_tab('tenants')", 'Tenants', show=False),
        Binding('3', "switch_tab('stacks')", 'Stacks', show=False),
        Binding('4', "switch_tab('tasks')", 'Tasks', show=False),
        Binding('5', "switch_tab('system')", 'System', show=False),
        Binding('r', 'force_refresh', 'Refresh'),
        Binding('q', 'quit', 'Quit'),
    ]

    def __init__(
        self,
        state_dir: str | None = None,
        refresh_interval: int = 5,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._state_dir = state_dir
        self._refresh_interval = refresh_interval
        self._data = AdminDataSource(state_dir=state_dir)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id='main'):
            with TabbedContent(id='tabs'):
                with TabPane('Dashboard', id='dashboard'):
                    yield DashboardScreen(self._data)
                with TabPane('Tenants', id='tenants'):
                    yield TenantsScreen(self._data)
                with TabPane('Stacks', id='stacks'):
                    yield StacksScreen(self._data)
                with TabPane('Tasks', id='tasks'):
                    yield TasksScreen(self._data)
                with TabPane('System', id='system'):
                    yield SystemScreen(self._data)
        yield Footer()

    def on_mount(self) -> None:
        self._do_refresh()
        if self._refresh_interval > 0:
            self.set_interval(self._refresh_interval, self._do_refresh)

    def _do_refresh(self) -> None:
        self.run_worker(self._refresh_worker, exclusive=True)

    async def _refresh_worker(self) -> None:
        for screen_cls in (
            DashboardScreen,
            TenantsScreen,
            StacksScreen,
            TasksScreen,
            SystemScreen,
        ):
            try:
                widget = self.query_one(screen_cls)  # pyrefly: ignore
                widget.refresh_data()
            except Exception:  # noseq
                pass

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one('#tabs', TabbedContent)
        tabs.active = tab_id  # pyrefly: ignore
        self._do_refresh()

    def action_force_refresh(self) -> None:
        self._do_refresh()
        self.notify('Refreshed')
