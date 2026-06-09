"""Confirmation modal for destructive actions."""

from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmModal(ModalScreen[bool]):
    """A modal dialog that asks the user to confirm an action."""

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    ConfirmModal > Vertical {
        width: 60;
        height: auto;
        max-height: 12;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    ConfirmModal .confirm-buttons {
        margin-top: 1;
        align: center middle;
    }
    ConfirmModal Button {
        margin: 0 1;
    }
    """

    def __init__(self, message: str, title: str = 'Confirm') -> None:
        super().__init__()
        self._message = message
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f'[bold]{self._title}[/bold]')
            yield Label(self._message)
            with Horizontal(classes='confirm-buttons'):
                yield Button('Yes', variant='error', id='yes')
                yield Button('No', variant='primary', id='no')

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == 'yes')
