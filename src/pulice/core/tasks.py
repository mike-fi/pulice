"""Task backend abstraction and Huey implementation.

``TaskBackend`` defines the protocol for async task execution.
``HueyTaskBackend`` is the default SQLite-backed implementation.
"""

from __future__ import annotations
import logging
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class TaskStatus(Enum):
    """Status of an async task in the execution pipeline.

    Attributes:
        PENDING: Task submitted but not yet picked up by a worker.
        RUNNING: Task is currently being executed.
        SUCCESS: Task completed without error.
        FAILED: Task raised an exception during execution.
        CANCELLED: Task was cancelled before or during execution.
        RETRYING: Task failed and has been resubmitted.
    """

    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    RETRYING = 'retrying'


@dataclass(frozen=True)
class TaskResult:
    """Snapshot of a task's current state and outcome.

    Attributes:
        task_id: Unique identifier for the task.
        status: Current lifecycle status.
        result: Operation result payload (on success).
        error: Error message (on failure).
        created_at: ISO 8601 timestamp when the task was submitted.
        started_at: ISO 8601 timestamp when execution began.
        completed_at: ISO 8601 timestamp when execution finished.
    """

    task_id: str
    status: TaskStatus
    result: Any | None = None
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TaskBackend(Protocol):
    """Contract for async task execution backends."""

    def submit(
        self,
        task_name: str,
        kwargs: dict[str, Any],
    ) -> str:
        """Submit a task for async execution. Return a task ID."""
        ...

    def get_status(self, task_id: str) -> TaskResult:
        """Return the current status and result of a task."""
        ...

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or running task. Return True if cancelled."""
        ...

    def retry(self, task_id: str) -> str:
        """Retry a failed task. Return the new task ID."""
        ...


# ---------------------------------------------------------------------------
# Huey helpers
# ---------------------------------------------------------------------------


def create_huey_instance(
    state_dir: str | None = None,
    immediate: bool = False,
) -> Any:
    """Create a configured SqliteHuey instance.

    Parameters
    ----------
    state_dir:
        Root directory for the Huey SQLite database.
    immediate:
        If True, tasks execute inline (useful for testing).
    """
    from huey import SqliteHuey

    root = (
        state_dir
        or os.getenv('PULICE_STATE_DIR')
        or str(Path(tempfile.gettempdir()) / 'pulice-state')
    )
    Path(root).mkdir(parents=True, exist_ok=True)
    db_path = str(Path(root) / 'pulice-tasks.db')
    return SqliteHuey(filename=db_path, immediate=immediate)


# ---------------------------------------------------------------------------
# HueyTaskBackend
# ---------------------------------------------------------------------------


class HueyTaskBackend:
    """Huey-backed implementation of TaskBackend.

    Args:
        huey_instance: A configured ``SqliteHuey`` instance (from
            :func:`create_huey_instance`).
    """

    def __init__(self, huey_instance: Any) -> None:
        self._huey = huey_instance
        self._task_fn = self._register_task()
        # Store submitted task kwargs for retry support
        self._submitted_kwargs: dict[str, dict[str, Any]] = {}

    def _register_task(self) -> Any:
        """Register the generic stack operation task with the Huey instance."""

        @self._huey.task(context=True)
        def execute_stack_operation(task=None, **kwargs: Any) -> dict:
            from pulice.core.task_definitions import execute_stack_operation as run_op

            return run_op(**kwargs)

        return execute_stack_operation

    def submit(self, task_name: str, kwargs: dict[str, Any]) -> str:
        result_handle = self._task_fn(**kwargs)
        task_id = result_handle.id
        self._submitted_kwargs[task_id] = kwargs
        return task_id

    def get_status(self, task_id: str) -> TaskResult:
        result_handle = self._huey.result(task_id, preserve=True)

        # Check if the task was revoked
        if self._huey.is_revoked(task_id):
            return TaskResult(task_id=task_id, status=TaskStatus.CANCELLED)

        if result_handle is None:
            # Task hasn't produced a result yet — still pending or running
            return TaskResult(task_id=task_id, status=TaskStatus.PENDING)

        # If result is an exception dict (our convention), it's a failure
        if isinstance(result_handle, dict) and result_handle.get('__error__'):
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=result_handle.get('__error__'),
            )

        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCESS,
            result=result_handle,
        )

    def cancel(self, task_id: str) -> bool:
        self._huey.revoke_by_id(task_id)
        return True

    def retry(self, task_id: str) -> str:
        kwargs = self._submitted_kwargs.get(task_id)
        if kwargs is None:
            raise ValueError(f"Cannot retry task '{task_id}': original kwargs not found.")
        return self.submit(kwargs.get('task_name', 'stack.operation'), kwargs)


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------


def get_task_backend(state_dir: str | None = None) -> TaskBackend:
    """Return a configured TaskBackend based on environment."""
    backend_type = os.getenv('PULICE_TASK_BACKEND', 'huey')

    if backend_type == 'huey':
        huey_instance = create_huey_instance(state_dir=state_dir)
        return HueyTaskBackend(huey_instance)

    if backend_type == 'celery':
        try:
            from pulice.core.celery_backend import create_celery_backend

            return create_celery_backend()
        except ImportError:
            raise ImportError(
                "Celery backend requires 'pulice[celery]'. Install with: pip install pulice[celery]"
            ) from None

    raise ValueError(f"Unknown task backend: {backend_type!r}. Use 'huey' or 'celery'.")
