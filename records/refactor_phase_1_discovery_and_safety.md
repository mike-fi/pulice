# Refactor Phase 1: Discovery and Safety

## Goal

Build a reliable mental model of the codebase before moving responsibilities around. This phase is about understanding the current architecture, documenting behavior, and adding safety rails so later refactors are grounded in tests instead of assumptions.

## Why This Phase Exists

This codebase appears to have been assembled quickly and iteratively. That usually means there is useful behavior hidden inside awkward structure. Before changing design, we want to preserve what works, identify where the real complexity lives, and make accidental behavior visible.

## Scope

- Understand one end-to-end managed stack operation flow.
- Identify responsibility boundaries in the core lifecycle code.
- Add characterization tests around stateful and failure-prone behavior.

## Human Learning Tasks

These tasks are intentionally good onboarding work for someone getting to know the codebase.

### Task 1: Trace the stack lifecycle end to end

Follow at least these operations:

- `create`
- `update`
- `list`
- `delete`

Read through:

- `src/pulice/cli/registry.py`
- `src/pulice/api/routes_stacks.py`
- `src/pulice/core/task_definitions.py`
- `src/pulice/core/managed.py`
- `src/pulice/core/stack.py`

Deliverable:

- A short markdown note in a scratch doc or PR description explaining:
  - where input enters the system
  - where tenant validation happens
  - where passphrase checks happen
  - where stack names and references are resolved
  - where Pulumi Automation is invoked

Why this helps:

- Teaches the real execution model
- Makes later service extraction much safer

### Task 2: Inventory responsibilities in `core/stack.py`

Read `src/pulice/core/stack.py` and group the code into these buckets:

- domain models
- passphrase hashing
- stack reference persistence
- SQLite tenant and stack persistence
- lock management
- Pulumi workspace and execution helpers

Deliverable:

- A simple responsibility map listing which classes and methods belong to which concern

Why this helps:

- Highlights SRP violations clearly
- Creates a roadmap for future extraction work

### Task 3: Add characterization tests

Add or expand tests for:

- stack reference `save`, `get`, `list`, `delete`
- tenant CRUD edge cases
- passphrase hash and verification behavior
- stale lock cleanup
- lock timeout behavior

Important note:

- These tests should capture current behavior, even if that behavior is not ideal
- Do not redesign during this task

Why this helps:

- Locks down behavior before structural changes
- Makes later refactors much less risky

## Suggested Implementation Tasks

1. Add a lightweight architecture note under `specs/` or in a PR description summarizing stack flow.
2. Expand existing tests around stack storage and locking.
3. Add missing negative-path coverage where current behavior is under-specified.

## Acceptance Criteria

- A teammate can explain the lifecycle of a managed stack operation without guessing.
- The main behaviors of tenant management, references, passphrases, and locks are covered by tests.
- No production behavior changes are introduced in this phase.

## Risks

- Over-refactoring too early
- Mistaking poor structure for broken behavior
- Writing tests that encode implementation details instead of user-visible behavior

## Out of Scope

- Moving modules
- Introducing new abstractions
- Rewriting the CLI, API, or worker flow

