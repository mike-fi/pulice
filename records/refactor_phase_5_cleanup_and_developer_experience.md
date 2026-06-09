# Refactor Phase 5: Cleanup and Developer Experience

## Goal

Finish the refactor by simplifying remaining duplication, improving dependency wiring, and documenting the new architecture so future contributors can navigate the codebase confidently.

## Why This Phase Exists

Once the core architecture is cleaner, the remaining work is about making the code pleasant to maintain. This phase turns structural improvements into day-to-day developer ergonomics.

## Scope

- Reduce duplication in admin screens
- Replace module-level globals where practical
- Document the architecture and refactor outcomes
- Tighten testing around the new seams

## Human Learning Tasks

### Task 1: Extract shared admin screen patterns

Review:

- `src/pulice/admin/screens/tenants.py`
- `src/pulice/admin/screens/stacks.py`
- `src/pulice/admin/screens/tasks.py`

Look for repeated patterns around:

- table setup
- row selection
- confirmation dialogs
- notification and refresh flows

Why this helps:

- Great way to learn the UI layer in a contained part of the codebase

### Task 2: Reduce global runtime state

Review module-level globals such as:

- API storage singleton
- task backend override

Move toward app-level dependency wiring or explicit construction where feasible.

Why this helps:

- Improves testability
- Reduces hidden state and ordering problems

### Task 3: Write architecture docs

Produce short docs covering:

- how a managed stack operation works now
- module responsibilities after the refactor
- where to add new operations or backends

Why this helps:

- Prevents the codebase from drifting back into vibe-coded ambiguity

## Suggested Implementation Tasks

1. Add a small admin screen base helper or utility layer.
2. Replace easy module globals with injected dependencies.
3. Add or update docs in `docs/` and `specs/`.
4. Add regression tests around newly extracted seams and DTOs.
5. Remove temporary compatibility code left over from earlier phases.

## Acceptance Criteria

- Admin screen logic is less repetitive and easier to extend.
- Global mutable module state is reduced where it meaningfully improves clarity.
- The post-refactor architecture is documented for future contributors.
- The codebase is easier to onboard into than it was before the refactor.

## Risks

- Spending too much time polishing instead of finishing structural cleanup
- Removing compatibility shims before the codebase fully migrates
- Writing docs that describe aspirations instead of actual code

## Out of Scope

- Major feature development
- Rebuilding the admin UI
- Replacing core frameworks or libraries

