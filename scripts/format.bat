poetry run pytest
poetry run python -m ruff check
poetry run python -m ruff format
poetry run python scripts/commit.py
