# Refactor Phase 2: Extract Low-Risk Seams

## Goal

Start simplifying the codebase by extracting clearly isolated responsibilities from oversized modules, without changing the user-facing behavior or orchestration flow.

## Why This Phase Exists

The biggest maintainability problem in the codebase is that a few modules mix unrelated concerns. This phase creates cleaner seams with minimal behavioral risk and gives human contributors a set of contained refactors that teach the system incrementally.

## Scope

- Extract operation constants and policy into one place
- Extract stack reference persistence
- Extract passphrase handling
- Extract lock-related logic into its own module

## Human Learning Tasks

### Task 1: Centralize operation policy

Create a small module for shared operation definitions.

Move or define:

- valid operations
- mutating operations
- retryable operations
- optionally an `Operation` enum

Update consumers in:

- CLI
- API
- worker

Why this helps:

- Exposes how the system thinks about operations
- Reduces drift across layers

### Task 2: Extract stack reference storage

Move `LocalStackReferenceStore` into its own module.

Keep the public behavior the same for now.

Why this helps:

- Teaches the difference between persisted stack metadata and Pulumi runtime execution
- Creates a cleaner boundary for later service work

### Task 3: Extract passphrase handling

Move `PassphraseHasher` into a dedicated module, ideally near other security-related concerns.

Why this helps:

- Small and safe refactor
- Gives a human contributor a focused task with quick feedback

### Task 4: Extract lock logic

Move `StackLock` and related lock queries into a dedicated module or repository.

Include explicit public methods for:

- acquire or use lock
- list locks
- release lock

Why this helps:

- Starts removing direct access to storage internals
- Clarifies one of the most stateful parts of the system

## Suggested Implementation Tasks

1. Create a `core/operations.py` module.
2. Create a `core/stack_references.py` module.
3. Create a `core/passphrases.py` module.
4. Create a `core/locks.py` module.
5. Update imports and tests with no behavior changes.

## Acceptance Criteria

- Shared operation rules are defined once and reused.
- `core/stack.py` is meaningfully smaller.
- Extracted modules have focused responsibilities.
- Existing tests continue to pass unchanged except where imports or naming need updates.

## Risks

- Extracting code mechanically without improving boundaries
- Leaving old private access patterns in place
- Changing behavior accidentally while moving code

## Out of Scope

- Rewriting stack lifecycle orchestration
- Replacing CLI or worker dispatch logic
- Redesigning persistence interfaces

