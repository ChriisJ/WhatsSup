# Contributing

PRs welcome. A few things to know:

## Dev setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
# Start the backend
python -m backend.main
# In another terminal, just open http://localhost:8000
```

## Adding to the supplement catalog

Edit `backend/seed_catalog.py` and add an entry. Slug must be unique.
On next startup, the catalog is seeded idempotently — your entry appears
in the catalog but won't overwrite existing user data.

## Adding an interaction rule

Edit `backend/interactions.py` → `SEED_RULES`. Severity must be one of
`info`, `warning`, `danger`.

## Adding a notifier channel

1. Create a new file in `backend/notifiers/`.
2. Subclass `Notifier` (`base.py`).
3. Wire it into `NotifierManager.default()` in `backend/notifiers/__init__.py`.
4. Add settings in `backend/config.py` and `.env.example`.

## Code style

- Python: PEP 8, type hints everywhere.
- No external build tooling for the frontend — keep it vanilla JS.

## Running tests

```bash
pytest backend/ -v
```

(Tests are minimal right now — pull requests adding coverage are very welcome.)
