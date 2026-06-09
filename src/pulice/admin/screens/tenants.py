"""Tenants screen — list and manage tenants."""

from __future__ import annotations
from textual.app import ComposeResult
from textual.widgets import DataTable, Static
from pulice.admin.widgets.confirm import ConfirmModal

if __name__ != '__main__':
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from pulice.admin.data import AdminDataSource


class TenantsScreen(Static):
    """Table of all tenants with actions."""

    DEFAULT_CSS = """
    TenantsScreen {
        height: 1fr;
        padding: 1 2;
    }
    """

    BINDINGS = [
        ('d', 'delete_tenant', 'Delete'),
    ]

    def __init__(self, data_source: 'AdminDataSource') -> None:
        super().__init__()
        self._data = data_source

    def compose(self) -> ComposeResult:
        table = DataTable(id='tenants-table')
        table.cursor_type = 'row'
        table.add_columns('Name', 'ID', 'Stacks', 'Created')
        yield table

    def refresh_data(self) -> None:
        table = self.query_one('#tenants-table', DataTable)
        table.clear()
        tenants = self._data.get_tenants()
        stacks = self._data.get_stacks()

        stack_counts: dict[str, int] = {}
        for s in stacks:
            tid = s.get('tenant_id', '')
            stack_counts[tid] = stack_counts.get(tid, 0) + 1

        for t in tenants:
            table.add_row(
                t.name,
                t.id[:12],
                str(stack_counts.get(t.id, 0)),
                t.created_at[:19],
                key=t.name,
            )

    def action_delete_tenant(self) -> None:
        table = self.query_one('#tenants-table', DataTable)
        if table.row_count == 0:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        tenant_name = str(row_key)

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                try:
                    self._data.delete_tenant(tenant_name)
                    self.notify(f"Deleted tenant '{tenant_name}'")
                    self.refresh_data()
                except ValueError as e:
                    self.notify(str(e), severity='error')

        self.app.push_screen(  # pyrefly: ignore
            ConfirmModal(f"Delete tenant '{tenant_name}'?", title='Delete Tenant'),
            on_confirm,
        )
