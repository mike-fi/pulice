# Contributing

Thank you for considering contributing to pulice! This guide covers how to set up a development environment, run tests, and submit changes.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/mike-fi/pulice.git
cd pulice

# Install with all development dependencies
uv sync --all-groups

# Or with pip
pip install -e ".[dev,api,celery,docs]"
```

## Running Tests

```bash
# Run the full test suite
pytest

# Run with coverage
pytest --cov=pulice --cov-report=term-missing

# Run a specific test file
pytest tests/test_stack.py
```

## Code Style

- Format with [ruff](https://docs.astral.sh/ruff/)
- Type annotations on all public functions
- Google-style docstrings on public API symbols

```bash
# Check formatting and linting
ruff check src/ tests/
ruff format --check src/ tests/

# Auto-fix
ruff check --fix src/ tests/
ruff format src/ tests/
```

## Documentation

```bash
# Install docs dependencies
uv sync --group docs

# Live preview
zensical serve

# Build static site
zensical build
```

## Project Structure

```
src/pulice/
├── core/           # Framework internals (stack ops, storage, tasks)
├── cli/            # Typer-based CLI
└── api/            # FastAPI HTTP server
tests/              # pytest test suite
docs/               # Documentation source (Zensical/MkDocs)
specs/              # Design specifications
```

## Submitting Changes

1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure `pytest` passes and `ruff check` is clean
4. Submit a pull request with a clear description

## Reporting Issues

Open an issue on GitHub with:

- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
- Pulumi CLI version (if relevant)
