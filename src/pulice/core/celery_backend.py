"""Celery-backed implementation of TaskBackend.

Requires ``pulice[celery]`` to be installed.
"""

from __future__ import annotations
import os
from pulice.core.tasks import TaskResult, TaskStatus
from typing import Any


class CeleryTaskBackend:
    """Celery-backed implementation of TaskBackend."""

    def __init__(self, celery_app: Any) -> None:
        self._app = celery_app
        self._task: Any = None
        self._register_tasks()

    def _register_tasks(self) -> None:
        """Register the generic stack operation task with the Celery app."""

        @self._app.task(bind=True, name='stack.operation')
        def execute_stack_operation(self_task: Any, **kwargs: Any) -> dict:
            from pulice.core.task_definitions import execute_stack_operation as run_op

            return run_op(**kwargs)

        self._task = execute_stack_operation

    def submit(self, task_name: str, kwargs: dict[str, Any]) -> str:
        result = self._app.send_task('stack.operation', kwargs=kwargs)
        return result.id

    def get_status(self, task_id: str) -> TaskResult:
        result = self._app.AsyncResult(task_id)
        state = result.state

        if state == 'PENDING':
            return TaskResult(task_id=task_id, status=TaskStatus.PENDING)
        if state == 'STARTED':
            return TaskResult(task_id=task_id, status=TaskStatus.RUNNING)
        if state == 'SUCCESS':
            value = result.result
            if isinstance(value, dict) and value.get('__error__'):
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    error=value['__error__'],
                )
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.SUCCESS,
                result=value,
            )
        if state == 'FAILURE':
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=str(result.result),
            )
        if state == 'REVOKED':
            return TaskResult(task_id=task_id, status=TaskStatus.CANCELLED)
        if state == 'RETRY':
            return TaskResult(task_id=task_id, status=TaskStatus.RETRYING)

        return TaskResult(task_id=task_id, status=TaskStatus.PENDING)

    def cancel(self, task_id: str) -> bool:
        self._app.control.revoke(task_id, terminate=True)
        return True

    def retry(self, task_id: str) -> str:
        result = self._app.AsyncResult(task_id)
        if not hasattr(result, 'kwargs') or not result.kwargs:
            raise ValueError(f"Cannot retry task '{task_id}': original kwargs not available.")
        return self.submit('stack.operation', result.kwargs)


def create_celery_backend() -> CeleryTaskBackend:
    """Create a CeleryTaskBackend with default configuration."""
    from celery import Celery  # pyrefly: ignore

    celery_app = Celery(
        'pulice',
        broker=os.getenv('PULICE_CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        backend=os.getenv('PULICE_CELERY_RESULT_BACKEND', 'redis://localhost:6379/1'),
    )
    return CeleryTaskBackend(celery_app)
