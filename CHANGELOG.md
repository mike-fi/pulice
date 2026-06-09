# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-29

### Added

- Core framework: `ManagedComponent`, `ComponentArgs` base classes
- 9 lifecycle operations: create, read, update, delete, refresh, list, status, export, import
- Tenant isolation with named boundaries and namespace scoping
- `SqliteBackendStorage` for stack metadata, passphrase hashes, and advisory locks
- `PassphraseHasher` with scrypt-based validation
- `StackLock` for preventing concurrent mutating operations
- `StackOperations` wrapping the Pulumi Automation API
- CLI via Typer with auto-generated commands from Pydantic models
- Tenant management commands (`pulice tenant create/list/delete`)
- FastAPI HTTP API with async task execution
- Huey task backend (SQLite, zero external dependencies)
- Celery task backend (Redis) for distributed deployments
- `WorkspaceController` and `ComponentController` base classes
- `LocalStackReferenceStore` for filesystem-backed stack references
- Full documentation site (Zensical + mkdocstrings)
- GitHub Actions workflow for docs deployment
