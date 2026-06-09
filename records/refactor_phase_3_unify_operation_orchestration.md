# Refactor Phase 3: Unify Operation Orchestration

## Goal

Remove duplicated lifecycle orchestration by creating one shared application service for managed stack operations, then migrate the worker, CLI, and API to call it.

## Why This Phase Exists

The codebase currently duplicates the same business flow in multiple places. That duplication is the main source of cyclomatic complexity and drift risk. Once extracted seams exist, the next step is to move orchestration into one explicit service.

## Scope

- Introduce a shared managed stack operation service
- Replace duplicated branching in the worker and CLI
- Move route-level business logic closer to the service boundary

## Target Design

Introduce something like:

- `ManagedStackOperationService`
- `ManagedStackOperationRequest`
- `ManagedStackOperationResult`

The service should own:

- tenant resolution
- stack context resolution
- passphrase validation
- lock handling
- operation dispatch
- result shaping

Transport layers should become adapters:

- CLI gathers input and formats terminal output
- API validates transport schema and submits work
- worker executes the shared business flow

## Human Learning Tasks

### Task 1: Design the service contract

Write down the inputs and outputs needed by all three entry points:

- CLI
- API
- worker

Define:

- what data each caller supplies
- what data the service returns
- what errors the service raises

Why this helps:

- Forces clear separation between business logic and transport logic
- Teaches where the layers are currently entangled

### Task 2: Migrate worker execution first

Refactor `src/pulice/core/task_definitions.py` to call the shared service.

Why first:

- The worker already behaves like an application layer
- It has fewer presentation concerns than the CLI

### Task 3: Migrate CLI managed-component execution

Refactor `_make_run_managed_component` so it mainly:

- prompts for missing interactive values
- builds a request
- calls the shared service
- renders the result

Why this helps:

- Removes the biggest duplicate branch tree in the codebase

### Task 4: Thin out the API route layer

Move business validation and request assembly into the shared service or a service-facing validator where appropriate.

Why this helps:

- Makes routes easier to read and test
- Prevents API-specific logic from becoming the canonical business flow

## Suggested Implementation Tasks

1. Introduce typed request and result DTOs.
2. Implement the shared service with the current behavior preserved.
3. Update worker execution to delegate to the service.
4. Update CLI managed-component operations to delegate to the service.
5. Simplify API stack submission code to use the same rules.

## Acceptance Criteria

- There is one canonical implementation of managed stack operation orchestration.
- CLI and worker no longer have separate full dispatch trees for the same lifecycle behavior.
- API code is thinner and contains less business logic.
- Tests cover the service behavior directly.

## Risks

- Moving too much transport-specific logic into the service
- Designing the service around one caller instead of all callers
- Accidentally changing output shape during migration

## Out of Scope

- Full module split of `core/stack.py`
- UI cleanup in admin screens
- Broader dependency injection redesign

