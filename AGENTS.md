# AGENTS.md

Guidance for AI agents and contributors working on `django-fashion-size`.

## What this project is

Django model and form fields for the [`fashion-size`](https://github.com/ababic/fashion-size) library (CalVer releases on PyPI). The package stores size types, size units, and size tokens on Django models, and provides an autocomplete form control backed by fashion-size charts.

Most behaviour is delegated to `fashion-size`. This repo should adapt to that library, not reimplement its charts or conversions.

## Repository layout

- `src/django_fashion_size/`: the package (hatchling build, `src` layout).
  - `model_fields.py`: `SizeField`, `SizeTypeField`, `SizeUnitField`, `FashionProductTypeField`, and their form fields.
  - `widgets.py`: `SizeValueWidget`, `SizeFormField`, `SizeBoundField`, and the JSON config built for the frontend (`size_value_config`). Chart and scale construction live here too (`_scale_from_chart`, `_resolve_scale`).
  - `kinds.py`: `TextChoices` enums (`SizeTypeSlug`, `SizeUnitSlug`, `FashionProductType`) whose values must match fashion-size.
  - `__init__.py`: import side effects. Importing the package registers Django's `get_language` with fashion-size and replaces `Size.display`. Keep that in mind when changing imports.
  - `static/django_fashion_size/`: compiled widget assets (`size_value_field.js`, `size_value_field.css`). These are generated and committed.
- `frontend/`: the React autocomplete widget source (`size_value_field/`), with its own `package.json`, ESLint, and Stylelint configs.
- `tests/`: pytest suite. Each module targets one field or widget. `test_size_value_widget.py` is the largest.
- `hatch_build.py`: build hook that runs `npm ci` and `npm run build` in `frontend/` when building a wheel or sdist from the repo.
- `tox.ini`: test matrix (Python 3.12, Django 6.0, 6.1, and main).
- `.github/workflows/`: CI (`test.yml`, `lint.yml`, `frontend.yml`) and `release.yml`.

## Setup

The project uses `uv` with a committed `uv.lock`. Python is 3.12 or newer (`requires-python = ">=3.12"`).

```bash
uv sync --extra testing --extra development
```

If you do not have `uv`, `pip install -e ".[testing,development]"` works, but CI and the lock file are based on `uv`.

## Commands

Run these before you report a change as done. They match what CI runs.

```bash
# Python tests (default locked dependencies)
uv run pytest tests

# Lint Python (CI runs ruff>=0.11,<1)
uv run --with "ruff>=0.11,<1" ruff check src tests

# Test against the latest fashion-size, not only the locked version
uv run --with fashion-size==<version> pytest tests

# Full multi-version matrix (Django 6.0, 6.1, main)
tox
tox -e py312-django60

# Frontend lint and build
cd frontend && npm ci && npm run lint && npm run build
```

Run a single test with `uv run pytest tests/test_size_value_widget.py::test_name`.

## Frontend assets

`npm run build` writes `src/django_fashion_size/static/django_fashion_size/size_value_field.js` and copies the CSS there. CI's `frontend.yml` runs `git diff --exit-code` on that directory, so:

- If you change anything under `frontend/`, run `npm run build` and commit the regenerated static files in the same commit.
- Do not hand-edit the compiled files.
- An install from PyPI uses the compiled files and does not need Node. Node is only needed when building from this repo.

## Dependency rules

- `fashion-size` is pinned with a lower bound in `pyproject.toml` and `tox.ini`. When you need a newer fashion-size feature or fix, raise both bounds and run `uv lock --upgrade-package fashion-size`.
- After upgrading, confirm the lock resolves the version you expect. A cached index can show an older release. Clear it with `uv cache clean fashion-size` and re-run `uv lock --upgrade-package fashion-size`.
- Django is constrained to `>=6.0,<7`. Do not widen this without updating the tox matrix and the README.

## Known fashion-size API details

- `fashion_size.types.ConversionScale` takes `effective_from` (required in the latest releases) and an optional `effective_until`. Older releases had no date fields. `_scale_from_chart` handles both, and the fallback only uses "now" when a chart carries no date. Do not drop that fallback until the minimum fashion-size bound guarantees the date fields.
- Brand charts come from `fashion_size.charts.chart_for(...)`. The returned `BrandConversionChart` exposes `effective_from`, `updated_at`, and `effective_until` in recent releases. Read them with `getattr` so older versions still work.
- Do not import `BrandConversionChart` from `fashion_size.brands`. It lives in `fashion_size.charts`.
- Before changing how this package calls fashion-size, inspect the installed signature. For example: `uv run python -c "import inspect; from fashion_size.types import ConversionScale as C; print(inspect.signature(C))"`.

## Coding conventions

- Ruff is the only linter. `pyproject.toml` sets `target-version = "py312"`, `src = ["src", "tests"]`, and ignores `RUF012` globally. In tests, `E402` and `I001` are ignored.
- Code uses `from __future__ import annotations` where it helps. Type hints are expected on public functions.
- Keep Django and fashion-size imports at module level. Only use local imports in tests when you need to isolate a module.
- Comments should explain intent, trade-offs, or constraints the code cannot express. Do not add comments that narrate what the code does.
- Use `gettext_lazy` for user-facing labels so `makemessages` can collect them.
- Passed `choices` on the `SizeUnitField`, `SizeTypeField`, and `FashionProductTypeField` form fields are intentionally ignored. Do not reintroduce them, because stale lists would then override fashion-size.

## Testing guidance

- Tests configure Django in-module with an in-memory SQLite database. Keep that pattern when adding test models. `tests/test_size_value_widget.py` defines the `Item` model with `app_label = "django_fashion_size"`.
- `pytest.ini_options` sets `pythonpath = ["src"]`, so tests import the package from `src/` without installing it.
- For widget behaviour, test the rendered config (`_config` in `test_size_value_widget.py`) and the posted cleaning path, not only the HTML.
- When you change conversion or chart logic, add a test that pins the expected token, not only that the form is valid.
- Run the suite against the latest fashion-size before opening a PR, because the locked version may lag.

## Release process

1. Bump `version` in `pyproject.toml` (CalVer is used by fashion-size, but this package uses SemVer `X.Y.Z`; follow the existing history).
2. Update `uv.lock` (`uv lock`) so the editable package version matches.
3. Merge to `main` (or a `release-*` branch). The release workflow refuses tags that are not on `main` or a `release-*` branch.
4. Tag `vX.Y.Z` on that commit. The workflow builds the wheel and sdist (compiling the frontend), attaches them to a GitHub release, and publishes to PyPI.

The tag must match the `pyproject.toml` version. Do not tag a commit that is not on `main` or a `release-*` branch.

## Git and PR workflow

- Branch names for agent work follow `cursor/<descriptive-name>-858a` (lowercase).
- Keep one logical change per commit. Run the commands in the Commands section before pushing.
- Do not force-push, amend, or rewrite shared history unless the user explicitly asks.
- PRs target `main` unless they are explicitly stacked on another branch.
