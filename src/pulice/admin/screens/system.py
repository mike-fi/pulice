"""System screen — read-only information panel."""

from __future__ import annotations
from textual.app import ComposeResult
from textual.widgets import Static

if __name__ != '__main__':
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from pulice.admin.data import AdminDataSource


def _format_bytes(size: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024:
            return f'{size:.1f} {unit}'
        size //= 1024
    return f'{size:.1f} TB'


class SystemScreen(Static):
    """Read-only system information panel."""

    DEFAULT_CSS = """
    SystemScreen {
        height: 1fr;
        padding: 1 2;
    }
    """

    def __init__(self, data_source: 'AdminDataSource') -> None:
        super().__init__()
        self._data = data_source

    def compose(self) -> ComposeResult:
        yield Static(id='system-content')

    def refresh_data(self) -> None:
        info = self._data.get_system_info()

        locks_text = ''
        if info['locks']:
            lock_lines = []
            for lock in info['locks']:
                age_min = int(lock['age_seconds']) // 60
                lock_lines.append(f'  - {lock["stack_name"]} ({lock["operation"]}, {age_min}m ago)')
            locks_text = '\n'.join(lock_lines)
        else:
            locks_text = '  None'

        text = (
            f'[bold]Version:[/bold]       {info["version"]}\n'
            f'[bold]Python:[/bold]        {info["python"].split()[0]}\n'
            f'[bold]State Dir:[/bold]     {info["state_dir"]}\n'
            f'[bold]State Size:[/bold]    {_format_bytes(info["state_dir_size"])}\n'
            f'[bold]DB Size:[/bold]       {_format_bytes(info["db_size"])}\n'
            f'[bold]Task Backend:[/bold]  {info["task_backend"]}\n'
            f'\n'
            f'[bold]Database Stats:[/bold]\n'
            f'  Tenants: {info["tenant_count"]}\n'
            f'  Stacks:  {info["stack_count"]}\n'
            f'  Locks:   {info["lock_count"]}\n'
            f'\n'
            f'[bold]Active Locks:[/bold]\n{locks_text}'
        )
        self.query_one('#system-content', Static).update(text)
