# Refactor Phase 4: Split Core and Strengthen Interfaces

## Goal

Break up the oversized core module into smaller focused modules and replace misleading or leaky abstractions with explicit interfaces and typed data transfer objects.

## Why This Phase Exists

After orchestration is unified, the codebase will have a clear center of gravity. This is the right time to split `core/stack.py` properly and fix the interface problems that currently force callers to reach into private internals.

## Scope

- Split the core module by responsibility
- Replace dict-heavy responses with typed DTOs
- Stop direct access to private internals like `_connect`, `_references`, and `_root`
- Clarify storage and repository interfaces

## Proposed Module Boundaries

Suggested target modules:

- `core/models.py`
- `core/tenants.py`
- `core/stacks.py`
- `core/stack_references.py`
- `core/locks.py`
- `core/passphrases.py`
- `core/workspaces.py`
- `core/stack_executor.py`

Exact naming can vary, but each module should have one clear reason to change.

## Human Learning Tasks

### Task 1: Identify leaky abstractions

Find and document where callers rely on private internals, especially:

- `_connect()`
- `_references`
- `_root`

Current examples include admin and CLI code.

Why this helps:

- Shows where the real public API is different from the intended one

### Task 2: Introduce explicit repository methods

Add public methods for operations that currently require internal access, such as:

- list locks
- release lock
- list stack references
- expose state directory via a proper method or property

Why this helps:

- Makes later refactors safer
- Reduces hidden coupling

### Task 3: Replace dict-shaped results

Introduce typed DTOs for:

- stack summary
- lock summary
- system info
- operation result

Why this helps:

- Improves discoverability
- Reduces stringly-typed behavior

## Suggested Implementation Tasks

1. Move core types into focused modules one concern at a time.
2. Add public methods where private access is currently required.
3. Update admin and service code to use those methods.
4. Introduce DTOs and update return sites gradually.
5. Remove old dict-based or private access paths once callers are migrated.

## Acceptance Criteria

- `core/stack.py` is either removed or reduced to a thin compatibility layer.
- Callers no longer depend on private storage internals.
- The major stateful concerns are separated into focused modules.
- Typed objects replace the most important dict-shaped responses.

## Risks

- Splitting modules too aggressively without stabilizing imports
- Introducing compatibility churn across many files at once
- Replacing too many dynamic shapes in one PR

## Out of Scope

- Admin UI visual redesign
- New user-facing features
- Changing the semantics of stack lifecycle operations

