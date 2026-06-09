"""Pulumi Automation API stack operations and backend storage."""

from __future__ import annotations
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from pulumi import automation
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class StackLockError(Exception):
    """Raised when a stack lock cannot be acquired."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tenant:
    """Named isolation boundary that owns zero or more stacks.

    Tenants provide namespace isolation so that identically-named components
    belonging to different environments or customers never collide.

    Attributes:
        id: Unique identifier (UUID hex string).
        name: Human-readable tenant name (unique across the system).
        created_at: ISO 8601 timestamp of when the tenant was created.
    """

    id: str
    name: str
    created_at: str


class BackendStorage(ABC):
    """Storage contract for stack metadata and working directories."""

    @abstractmethod
    def ensure_stack_dir(self, stack_name: str) -> str:
        """Return an existing or newly created filesystem path for *stack_name*."""


@dataclass(frozen=True)
class StackReference:
    """Filesystem-backed reference used to locate a managed stack.

    A stack reference is returned by the ``create`` operation and must be
    provided for all subsequent operations on that stack. It maps a short
    UUID handle to the full stack metadata needed to locate Pulumi state.

    Attributes:
        id: UUID hex string used as the public handle.
        component_name: Name of the registered ManagedComponent.
        stack_name: Full Pulumi stack name (tenant-component-uuid).
        project_name: Pulumi project name.
        workdir: Filesystem path to the stack's working directory.
        tenant_id: ID of the owning tenant.
    """

    id: str
    component_name: str
    stack_name: str
    project_name: str
    workdir: str
    tenant_id: str = ''


# ---------------------------------------------------------------------------
# PassphraseHasher
# ---------------------------------------------------------------------------


class PassphraseHasher:
    """Hash and verify passphrases using hashlib.scrypt (zero new dependencies)."""

    @staticmethod
    def hash(passphrase: str) -> str:
        """Return an scrypt hash string of the passphrase.

        Format: ``scrypt:<salt_hex>:<hash_hex>``
        """
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(
            passphrase.encode('utf-8'),
            salt=salt,
            n=16384,
            r=8,
            p=1,
            dklen=32,
        )
        return f'scrypt:{salt.hex()}:{derived.hex()}'

    @staticmethod
    def verify(passphrase: str, passphrase_hash: str) -> bool:
        """Return True if the passphrase matches the stored hash."""
        parts = passphrase_hash.split(':')
        if len(parts) != 3 or parts[0] != 'scrypt':
            return False
        salt = bytes.fromhex(parts[1])
        expected = bytes.fromhex(parts[2])
        derived = hashlib.scrypt(
            passphrase.encode('utf-8'),
            salt=salt,
            n=16384,
            r=8,
            p=1,
            dklen=32,
        )
        return secrets.compare_digest(derived, expected)


# ---------------------------------------------------------------------------
# LocalStackReferenceStore
# ---------------------------------------------------------------------------


class LocalStackReferenceStore:
    """Store stack references as local JSON files under ``<root>/stack_refs``."""

    def __init__(self, root_dir: Optional[str] = None, dirname: str = 'stack_refs') -> None:
        default_root = Path(tempfile.gettempdir()) / 'pulice-state'
        self._root = Path(root_dir) if root_dir else default_root
        self._refs_dir = self._root / dirname
        self._refs_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, reference_id: str) -> Path:
        return self._refs_dir / f'{reference_id}.json'

    def save(self, reference: StackReference) -> None:
        self._path_for(reference.id).write_text(json.dumps(reference.__dict__), encoding='utf-8')

    def get(self, reference_id: str) -> StackReference:
        ref_path = self._path_for(reference_id)
        if not ref_path.exists():
            raise ValueError(
                f"Unknown stack reference '{reference_id}'. "
                'Run create first and use the returned reference id.'
            )
        data = json.loads(ref_path.read_text(encoding='utf-8'))
        # Handle old JSON files missing tenant_id
        data.setdefault('tenant_id', '')
        return StackReference(**data)

    def delete(self, reference_id: str) -> None:
        """Remove a stack reference file."""
        ref_path = self._path_for(reference_id)
        if ref_path.exists():
            ref_path.unlink()

    def list(
        self,
        tenant_id: str | None = None,
        component_name: str | None = None,
    ) -> list[StackReference]:
        """List all stored stack references, optionally filtered."""
        results: list[StackReference] = []
        for ref_file in self._refs_dir.glob('*.json'):
            data = json.loads(ref_file.read_text(encoding='utf-8'))
            data.setdefault('tenant_id', '')
            ref = StackReference(**data)
            if tenant_id and ref.tenant_id != tenant_id:
                continue
            if component_name and ref.component_name != component_name:
                continue
            results.append(ref)
        return results


# ---------------------------------------------------------------------------
# SqliteBackendStorage
# ---------------------------------------------------------------------------


class SqliteBackendStorage(BackendStorage):
    """SQLite-backed storage for stack name/uuid mapping and stack directories.

    Args:
        root_dir: Root directory for all state files. Defaults to a
            ``pulice-state`` directory in the system temp folder.
        db_filename: Name of the SQLite database file.
        stacks_dirname: Subdirectory name for per-stack working directories.
    """

    def __init__(
        self,
        root_dir: Optional[str] = None,
        db_filename: str = 'pulice_stacks.sqlite3',
        stacks_dirname: str = 'stacks',
    ) -> None:
        default_root = Path(tempfile.gettempdir()) / 'pulice-state'
        self._root = Path(root_dir) if root_dir else default_root
        self._root.mkdir(parents=True, exist_ok=True)
        self._db_path = self._root / db_filename
        self._stacks_root = self._root / stacks_dirname
        self._stacks_root.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            # Tenants table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tenants (
                    id         TEXT PRIMARY KEY,
                    name       TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Stacks table — check if it already exists (for migration)
            existing_cols = {row[1] for row in conn.execute('PRAGMA table_info(stacks)').fetchall()}

            if not existing_cols:
                # Fresh install — create full schema
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS stacks (
                        name            TEXT PRIMARY KEY,
                        uuid            TEXT NOT NULL UNIQUE,
                        path            TEXT NOT NULL,
                        tenant_id       TEXT NOT NULL DEFAULT '',
                        passphrase_hash TEXT,
                        created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            else:
                # Migration from old schema
                if 'tenant_id' not in existing_cols:
                    conn.execute("ALTER TABLE stacks ADD COLUMN tenant_id TEXT NOT NULL DEFAULT ''")
                if 'passphrase_hash' not in existing_cols:
                    conn.execute('ALTER TABLE stacks ADD COLUMN passphrase_hash TEXT')

            # Stack locks table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stack_locks (
                    stack_name TEXT PRIMARY KEY,
                    holder     TEXT NOT NULL,
                    operation  TEXT NOT NULL,
                    locked_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Ensure a default tenant exists for backward compatibility
            conn.execute(
                """
                INSERT OR IGNORE INTO tenants(id, name, created_at)
                VALUES ('default', 'default', CURRENT_TIMESTAMP)
                """
            )

            # Backfill existing stacks without a tenant_id
            conn.execute("UPDATE stacks SET tenant_id = 'default' WHERE tenant_id = ''")

    # --- Tenant CRUD ---

    def create_tenant(self, name: str) -> Tenant:
        tenant_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            try:
                conn.execute(
                    'INSERT INTO tenants(id, name, created_at) VALUES (?, ?, ?)',
                    (tenant_id, name, now),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"Tenant '{name}' already exists.") from None
        return Tenant(id=tenant_id, name=name, created_at=now)

    def get_tenant(self, name: str) -> Tenant:
        with self._connect() as conn:
            row = conn.execute(
                'SELECT id, name, created_at FROM tenants WHERE name = ?',
                (name,),
            ).fetchone()
        if not row:
            raise ValueError(f"Tenant '{name}' not found.")
        return Tenant(id=row[0], name=row[1], created_at=row[2])

    def get_tenant_by_id(self, tenant_id: str) -> Tenant:
        with self._connect() as conn:
            row = conn.execute(
                'SELECT id, name, created_at FROM tenants WHERE id = ?',
                (tenant_id,),
            ).fetchone()
        if not row:
            raise ValueError(f"Tenant with id '{tenant_id}' not found.")
        return Tenant(id=row[0], name=row[1], created_at=row[2])

    def list_tenants(self) -> list[Tenant]:
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT id, name, created_at FROM tenants ORDER BY created_at'
            ).fetchall()
        return [Tenant(id=r[0], name=r[1], created_at=r[2]) for r in rows]

    def delete_tenant(self, name: str) -> None:
        with self._connect() as conn:
            tenant = conn.execute(
                'SELECT id FROM tenants WHERE name = ?',
                (name,),
            ).fetchone()
            if not tenant:
                raise ValueError(f"Tenant '{name}' not found.")
            stack_count = conn.execute(
                'SELECT COUNT(*) FROM stacks WHERE tenant_id = ?',
                (tenant[0],),
            ).fetchone()[0]
            if stack_count > 0:
                raise ValueError(
                    f"Cannot delete tenant '{name}': it still has {stack_count} stack(s)."
                )
            conn.execute('DELETE FROM tenants WHERE name = ?', (name,))

    # --- Passphrase hash storage ---

    def save_passphrase_hash(self, stack_name: str, passphrase_hash: str) -> None:
        with self._connect() as conn:
            conn.execute(
                'UPDATE stacks SET passphrase_hash = ? WHERE name = ?',
                (passphrase_hash, stack_name),
            )

    def get_passphrase_hash(self, stack_name: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                'SELECT passphrase_hash FROM stacks WHERE name = ?',
                (stack_name,),
            ).fetchone()
        if not row:
            return None
        return row[0]

    # --- Stack listing ---

    def list_stacks(
        self,
        tenant_id: str | None = None,
        component_name: str | None = None,
    ) -> list[dict]:
        query = 'SELECT name, uuid, path, tenant_id, created_at FROM stacks WHERE 1=1'
        params: list[str] = []
        if tenant_id is not None:
            query += ' AND tenant_id = ?'
            params.append(tenant_id)
        if component_name is not None:
            query += ' AND name LIKE ?'
            params.append(f'%{component_name}%')
        query += ' ORDER BY created_at'
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                'stack_name': r[0],
                'uuid': r[1],
                'path': r[2],
                'tenant_id': r[3],
                'created_at': r[4],
            }
            for r in rows
        ]

    def delete_stack(self, stack_name: str) -> None:
        """Remove a stack entry from the database."""
        with self._connect() as conn:
            conn.execute('DELETE FROM stacks WHERE name = ?', (stack_name,))

    # --- Stack directory management ---

    def ensure_stack_dir(self, stack_name: str, tenant_id: str = 'default') -> str:
        with self._connect() as conn:
            row = conn.execute(
                'SELECT uuid, path FROM stacks WHERE name = ?',
                (stack_name,),
            ).fetchone()

            if row:
                stack_path = Path(row[1])
                stack_path.mkdir(parents=True, exist_ok=True)
                return str(stack_path)

            stack_uuid = str(uuid4())
            stack_path = self._stacks_root / stack_uuid
            stack_path.mkdir(parents=True, exist_ok=True)
            conn.execute(
                'INSERT INTO stacks(name, uuid, path, tenant_id) VALUES (?, ?, ?, ?)',
                (stack_name, stack_uuid, str(stack_path), tenant_id),
            )
            return str(stack_path)


# ---------------------------------------------------------------------------
# StackLock
# ---------------------------------------------------------------------------


class StackLock:
    """Advisory lock for stack operations backed by SQLite.

    Use as a context manager to prevent concurrent mutating operations on
    the same stack::

        with StackLock(storage, stack_name, 'update'):
            # perform the operation
            ...

    Args:
        storage: The SQLite backend that holds the lock table.
        stack_name: Name of the stack to lock.
        operation: Name of the operation acquiring the lock (for diagnostics).
        timeout: Maximum seconds to wait for the lock before raising.

    Raises:
        StackLockError: If the lock cannot be acquired within the timeout.
    """

    _STALE_THRESHOLD_SECONDS = 600  # 10 minutes

    def __init__(
        self,
        storage: SqliteBackendStorage,
        stack_name: str,
        operation: str,
        timeout: float = 30.0,
    ) -> None:
        self._storage = storage
        self._stack_name = stack_name
        self._operation = operation
        self._timeout = timeout
        self._holder = uuid4().hex

    def __enter__(self) -> StackLock:
        deadline = time.monotonic() + self._timeout
        delay = 0.1
        while True:
            try:
                with self._storage._connect() as conn:
                    conn.execute(
                        'INSERT INTO stack_locks(stack_name, holder, operation, locked_at) '
                        'VALUES (?, ?, ?, ?)',
                        (
                            self._stack_name,
                            self._holder,
                            self._operation,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                return self
            except sqlite3.IntegrityError:
                # Lock exists — check if stale
                with self._storage._connect() as conn:
                    row = conn.execute(
                        'SELECT holder, operation, locked_at FROM stack_locks WHERE stack_name = ?',
                        (self._stack_name,),
                    ).fetchone()
                if row:
                    locked_at = datetime.fromisoformat(row[2])
                    age = (datetime.now(timezone.utc) - locked_at).total_seconds()
                    if age > self._STALE_THRESHOLD_SECONDS:
                        with self._storage._connect() as conn:
                            conn.execute(
                                'DELETE FROM stack_locks WHERE stack_name = ?',
                                (self._stack_name,),
                            )
                        continue  # Retry immediately after cleaning stale lock

                if time.monotonic() >= deadline:
                    holder_info = f"operation='{row[1]}'" if row else 'unknown'
                    raise StackLockError(
                        f"Cannot acquire lock for stack '{self._stack_name}': "
                        f'held by another process ({holder_info}). '
                        f'Timed out after {self._timeout}s.'
                    )
                time.sleep(delay)
                delay = min(delay * 2, 2.0)

        return self

    def __exit__(self, *exc_info: object) -> None:
        with self._storage._connect() as conn:
            deleted = conn.execute(
                'DELETE FROM stack_locks WHERE stack_name = ? AND holder = ?',
                (self._stack_name, self._holder),
            ).rowcount
        if not deleted:
            logger.warning(
                'Lock for stack %r was already released or stolen.',
                self._stack_name,
            )


# ---------------------------------------------------------------------------
# StackOperations
# ---------------------------------------------------------------------------


class StackOperations:
    """Helpers for provisioning Pulumi stacks via the Automation API.

    Provides methods for each lifecycle operation (create, preview, destroy,
    refresh, status, export, import) and manages stack references and
    working directories.

    Args:
        storage: Backend storage instance. Defaults to a new
            ``SqliteBackendStorage`` using ``PULICE_STATE_DIR``.
    """

    def __init__(self, storage: Optional[BackendStorage] = None) -> None:
        self._storage = storage or SqliteBackendStorage(root_dir=os.getenv('PULICE_STATE_DIR'))
        self._references = LocalStackReferenceStore(root_dir=os.getenv('PULICE_STATE_DIR'))

    @property
    def storage(self) -> BackendStorage:
        """Public access to the underlying storage backend."""
        return self._storage

    def save_stack_reference(
        self,
        reference_id: str,
        component_name: str,
        stack_name: str,
        project_name: str,
        workdir: str,
        tenant_id: str = '',
    ) -> StackReference:
        reference = StackReference(
            id=reference_id,
            component_name=component_name,
            stack_name=stack_name,
            project_name=project_name,
            workdir=workdir,
            tenant_id=tenant_id,
        )
        self._references.save(reference)
        return reference

    def get_stack_reference(
        self,
        reference_id: str,
        expected_component_name: Optional[str] = None,
    ) -> StackReference:
        reference = self._references.get(reference_id)
        if expected_component_name and reference.component_name != expected_component_name:
            raise ValueError(
                f"Stack reference '{reference_id}' belongs to component "
                f"'{reference.component_name}', not '{expected_component_name}'."
            )
        return reference

    def ensure_workspace(self, workdir: Optional[str] = os.getenv('PULICE_STATE_DIR')) -> str:
        if workdir:
            Path(workdir).mkdir(parents=True, exist_ok=True)
            return workdir
        return tempfile.mkdtemp(prefix='pulumi-auto-')

    def ensure_stack_workspace(self, stack_name: str, workdir: Optional[str] = None) -> str:
        if workdir:
            return self.ensure_workspace(workdir)
        return self._storage.ensure_stack_dir(stack_name)

    def _local_workspace_opts(
        self,
        project_name: str,
        workdir: str,
        env_vars: Optional[dict] = None,
    ) -> automation.LocalWorkspaceOptions:
        state_dir = Path(workdir) / '.pulumi-state'
        state_dir.mkdir(parents=True, exist_ok=True)
        backend_url = os.getenv('PULICE_PULUMI_BACKEND_URL', f'file://{state_dir}')

        merged_env = {
            'PULUMI_CONFIG_PASSPHRASE': '',  # nosec B105
            **(env_vars or {}),
        }

        return automation.LocalWorkspaceOptions(
            work_dir=workdir,
            project_settings=automation.ProjectSettings(
                name=project_name,
                runtime='python',
                backend=automation.ProjectBackend(url=backend_url),
            ),
            env_vars=merged_env,
        )

    def create_or_update_stack(
        self,
        stack_name: str,
        project_name: str,
        workdir: str,
        program: Callable,
        env_vars: Optional[dict] = None,
    ) -> automation.Stack:
        try:
            stack = automation.create_or_select_stack(
                stack_name=stack_name,
                project_name=project_name,
                program=program,
                opts=self._local_workspace_opts(project_name, workdir, env_vars),
            )
        except automation.StackAlreadyExistsError:
            stack = automation.select_stack(
                stack_name=stack_name,
                project_name=project_name,
                program=program,
                opts=self._local_workspace_opts(project_name, workdir, env_vars),
            )
        stack.up(on_output=print)
        return stack

    def preview_stack(
        self,
        stack_name: str,
        project_name: str,
        workdir: str,
        program: Callable,
        env_vars: Optional[dict] = None,
    ) -> automation.Stack:
        stack = automation.create_or_select_stack(
            stack_name=stack_name,
            project_name=project_name,
            program=program,
            opts=self._local_workspace_opts(project_name, workdir, env_vars),
        )
        stack.preview(refresh=True, on_output=print)
        return stack

    def destroy_stack(
        self,
        stack_name: str,
        project_name: str,
        workdir: str,
        program: Callable,
        env_vars: Optional[dict] = None,
    ) -> automation.Stack:
        stack = automation.create_or_select_stack(
            stack_name=stack_name,
            project_name=project_name,
            program=program,
            opts=self._local_workspace_opts(project_name, workdir, env_vars),
        )
        stack.destroy(refresh=True, on_output=print)
        return stack

    def refresh_stack(
        self,
        stack_name: str,
        project_name: str,
        workdir: str,
        program: Callable,
        env_vars: Optional[dict] = None,
    ) -> automation.Stack:
        stack = automation.create_or_select_stack(
            stack_name=stack_name,
            project_name=project_name,
            program=program,
            opts=self._local_workspace_opts(project_name, workdir, env_vars),
        )
        stack.refresh(on_output=print)
        return stack

    def stack_status(
        self,
        stack_name: str,
        project_name: str,
        workdir: str,
        program: Callable,
        env_vars: Optional[dict] = None,
    ) -> dict:
        stack = automation.create_or_select_stack(
            stack_name=stack_name,
            project_name=project_name,
            program=program,
            opts=self._local_workspace_opts(project_name, workdir, env_vars),
        )
        info = stack.info()
        return {
            'stack_name': stack_name,
            'resource_count': info.resource_count if info else 0,  # pyrefly: ignore
            'last_update': str(info.last_update) if info else None,  # pyrefly: ignore
            'url': info.url if info else None,  # pyrefly: ignore
        }

    def export_stack(
        self,
        stack_name: str,
        project_name: str,
        workdir: str,
        program: Callable,
        env_vars: Optional[dict] = None,
    ) -> dict:
        stack = automation.create_or_select_stack(
            stack_name=stack_name,
            project_name=project_name,
            program=program,
            opts=self._local_workspace_opts(project_name, workdir, env_vars),
        )
        deployment = stack.export_stack()
        return deployment.deployment  # pyrefly: ignore

    def import_stack(
        self,
        stack_name: str,
        project_name: str,
        workdir: str,
        program: Callable,
        state: dict,
        env_vars: Optional[dict] = None,
    ) -> None:
        stack = automation.create_or_select_stack(
            stack_name=stack_name,
            project_name=project_name,
            program=program,
            opts=self._local_workspace_opts(project_name, workdir, env_vars),
        )
        stack.import_stack(automation.Deployment(version=3, deployment=state))
