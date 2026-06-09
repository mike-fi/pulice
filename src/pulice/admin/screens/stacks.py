"""Stacks screen — list and manage stacks."""

from __future__ import annotations
from textual.app import ComposeResult
from textual.widgets import DataTable, Static
from pulice.admin.widgets.confirm import ConfirmModal

if __name__ != '__main__':
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from pulice.admin.data import AdminDataSource


class StacksScreen(Static):
    """Table of all stacks with lock management."""

    DEFAULT_CSS = """
    StacksScreen {
        height: 1fr;
        padding: 1 2;
    }
    """

    BINDINGS = [
        ('l', 'release_lock', 'Release Lock'),
    ]

    def __init__(self, data_source: 'AdminDataSource') -> None:
        super().__init__()
        self._data = data_source
        self._tenant_filter: str | None = None

    def compose(self) -> ComposeResult:
        table = DataTable(id='stacks-table')
        table.cursor_type = 'row'
        table.add_columns('Stack Name', 'Tenant', 'UUID', 'Locked', 'Created')
        yield table

    def refresh_data(self) -> None:
        table = self.query_one('#stacks-table', DataTable)
        table.clear()
        stacks = self._data.get_stacks(tenant_id=self._tenant_filter)
        locks = {lock['stack_name']: lock for lock in self._data.get_locks()}
        tenants = {t.id: t.name for t in self._data.get_tenants()}

        for s in stacks:
            stack_name = s['stack_name']
            lock = locks.get(stack_name)
            lock_display = f'[red]Locked ({lock["operation"]})[/red]' if lock else ''
            tenant_name = tenants.get(s.get('tenant_id', ''), '—')

            table.add_row(
                stack_name,
                tenant_name,
                s['uuid'][:12],
                lock_display,
                s.get('created_at', '')[:19],
                key=stack_name,
            )

    def action_release_lock(self) -> None:
        table = self.query_one('#stacks-table', DataTable)
        if table.row_count == 0:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        stack_name = str(row_key)

        locks = {lock['stack_name']: lock for lock in self._data.get_locks()}
        if stack_name not in locks:
            self.notify('No lock on this stack', severity='warning')
            return

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                self._data.release_lock(stack_name)
                self.notify(f"Released lock on '{stack_name}'")
                self.refresh_data()

        self.app.push_screen(  # pyrefly: ignore
            ConfirmModal(
                f"Release lock on '{stack_name}'?",
                title='Release Lock',
            ),
            on_confirm,
        )
