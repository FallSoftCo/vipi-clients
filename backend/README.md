# Backend development

Run the following commands from the repository root. The service uses Python 3.12. Its FastAPI composition lives in `backend/vipi/api.py`, message routes in `backend/vipi/messages_api.py`, and request models in `backend/vipi/api_inputs.py`.

## Format Python

Check the service and tests with the version of Ruff pinned in `backend/pyproject.toml`. With uv installed, the first invocation installs Ruff in its separate tool cache.

```sh
uvx --from ruff==0.15.13 ruff format --check backend/vipi backend/tests
```

To format an edit, remove `--check` and inspect the diff. The formatter covers authored service and test code. Migration files and archived qualification evidence have content hashes in release records and stay outside the formatting scope.

## Run the PostgreSQL suite

Use the backend test environment and PostgreSQL 16. Give each run a fresh disk-backed directory. The runner writes `suite.log`, `suite.xml` and `result.json` there and removes its private database cluster on exit.

```sh
backend/.venv/bin/python scripts/test-postgres.py --run-directory "$(mktemp -d)/pg"
```

For environment setup and cross-platform tests, see [Build environments](../docs/BUILD_ENVIRONMENTS.md).

## Scale the relay

[Rehearse the two-instance switch and operate a scale-out or drain](SCALING.md) with the existing immutable service packages, systemd, PostgreSQL and Nginx.
