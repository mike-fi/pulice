"""Read-only data provider for the admin TUI."""

from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import pulice
from pulice.core.stack import (
    LocalStackReferenceStore,
    SqliteBackendStorage,
    StackReference,
    Tenant,
)
from pulice.core.tasks import TaskBackend, TaskResult
from typing import Any


class AdminDataSource:
    """Read-only data provider for the admin TUI.

    Wraps existing storage APIs to provide data for all admin screens.
    """

    def __init__(self, state_dir: str | None = None) -> None:
        self._state_dir = state_dir or os.getenv('PULICE_STATE_DIR')
        self._storage = SqliteBackendStorage(root_dir=self._state_dir)
        self._references = LocalStackReferenceStore(root_dir=self._state_dir)
        self._task_backend: TaskBackend | None = None

    def _get_task_backend(self) -> TaskBackend:
        if self._task_backend is None:
            from pulice.core.tasks import get_task_backend

            self._task_backend = get_task_backend(state_dir=self._state_dir)
        return self._task_backend

    @property
    def state_dir(self) -> str:
        return str(self._storage._root)

    def get_tenants(self) -> list[Tenant]:
        return self._storage.list_tenants()

    def get_stacks(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        return self._storage.list_stacks(tenant_id=tenant_id)

    def get_stack_references(self, tenant_id: str | None = None) -> list[StackReference]:
        return self._references.list(tenant_id=tenant_id)

    def get_locks(self) -> list[dict[str, Any]]:
        with self._storage._connect() as conn:
            rows = conn.execute(
                'SELECT stack_name, holder, operation, locked_at FROM stack_locks'
            ).fetchall()
        now = datetime.now(timezone.utc)
        results = []
        for r in rows:
            locked_at = datetime.fromisoformat(r[3])
            age_seconds = (now - locked_at).total_seconds()
            results.append(
                {
                    'stack_name': r[0],
                    'holder': r[1],
                    'operation': r[2],
                    'locked_at': r[3],
                    'age_seconds': age_seconds,
                }
            )
        return results

    def get_task_status(self, task_id: str) -> TaskResult:
        return self._get_task_backend().get_status(task_id)

    def get_system_info(self) -> dict[str, Any]:
        state_path = Path(self.state_dir)
        db_path = state_path / 'pulice_stacks.sqlite3'

        total_size = sum(f.stat().st_size for f in state_path.rglob('*') if f.is_file())
        db_size = db_path.stat().st_size if db_path.exists() else 0

        tenants = self.get_tenants()
        stacks = self.get_stacks()
        locks = self.get_locks()

        backend_type = os.getenv('PULICE_TASK_BACKEND', 'huey')

        return {
            'version': pulice.__version__,
            'python': sys.version,
            'state_dir': self.state_dir,
            'state_dir_size': total_size,
            'db_size': db_size,
            'task_backend': backend_type,
            'tenant_count': len(tenants),
            'stack_count': len(stacks),
            'lock_count': len(locks),
            'locks': locks,
        }

    def delete_tenant(self, name: str) -> None:
        self._storage.delete_tenant(name)

    def release_lock(self, stack_name: str) -> None:
        with self._storage._connect() as conn:
            conn.execute('DELETE FROM stack_locks WHERE stack_name = ?', (stack_name,))

    def cancel_task(self, task_id: str) -> bool:
        return self._get_task_backend().cancel(task_id)

    def retry_task(self, task_id: str) -> str:
        return self._get_task_backend().retry(task_id)
