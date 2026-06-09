"""Metric card widget for the dashboard."""

from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label


class StatCard(Widget):
    """A simple card showing a label and a numeric value."""

    DEFAULT_CSS = """
    StatCard {
        width: 1fr;
        height: 5;
        border: solid $primary;
        padding: 0 1;
    }
    StatCard .stat-label {
        color: $text-muted;
    }
    StatCard .stat-value {
        text-style: bold;
    }
    """

    def __init__(
        self,
        label: str,
        value: str = '0',
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)  # pyrefly: ignore
        self._label = label
        self._value = value

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._label, classes='stat-label')
            yield Label(self._value, classes='stat-value', id='value')

    def update_value(self, value: str) -> None:
        self._value = value
        try:
            self.query_one('#value', Label).update(value)
        except Exception:  # noseq
            pass
