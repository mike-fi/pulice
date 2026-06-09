"""Tasks screen — list and manage async tasks."""

from __future__ import annotations
from textual.app import ComposeResult
from textual.widgets import DataTable, Static
from pulice.admin.widgets.confirm import ConfirmModal

if __name__ != '__main__':
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from pulice.admin.data import AdminDataSource


class TasksScreen(Static):
    """Table of tasks with cancel/retry actions.

    Note: The current HueyTaskBackend does not support listing all tasks.
    This screen shows a placeholder until a task index is implemented.
    """

    DEFAULT_CSS = """
    TasksScreen {
        height: 1fr;
        padding: 1 2;
    }
    """

    BINDINGS = [
        ('c', 'cancel_task', 'Cancel'),
        ('r', 'retry_task', 'Retry'),
    ]

    def __init__(self, data_source: 'AdminDataSource') -> None:
        super().__init__()
        self._data = data_source

    def compose(self) -> ComposeResult:
        yield Static(
            '[dim]Task listing requires a task index (not yet implemented in the '
            'Huey backend). Individual tasks can be queried by ID.[/dim]',
            id='tasks-notice',
        )
        table = DataTable(id='tasks-table')
        table.cursor_type = 'row'
        table.add_columns('Task ID', 'Status', 'Error')
        yield table

    def refresh_data(self) -> None:
        pass

    def action_cancel_task(self) -> None:
        table = self.query_one('#tasks-table', DataTable)
        if table.row_count == 0:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        task_id = str(row_key)

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                success = self._data.cancel_task(task_id)
                if success:
                    self.notify(f"Cancelled task '{task_id[:12]}'")
                else:
                    self.notify('Could not cancel task', severity='error')
                self.refresh_data()

        self.app.push_screen(  # pyrefly: ignore
            ConfirmModal(f"Cancel task '{task_id[:12]}'?", title='Cancel Task'),
            on_confirm,
        )

    def action_retry_task(self) -> None:
        table = self.query_one('#tasks-table', DataTable)
        if table.row_count == 0:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        task_id = str(row_key)

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                try:
                    new_id = self._data.retry_task(task_id)
                    self.notify(f"Retried as '{new_id[:12]}'")
                    self.refresh_data()
                except ValueError as e:
                    self.notify(str(e), severity='error')

        self.app.push_screen(  # pyrefly: ignore
            ConfirmModal(f"Retry task '{task_id[:12]}'?", title='Retry Task'),
            on_confirm,
        )
