

setup:
	python -m venv .venv
	.venv/bin/pip install poetry pre-commit
	.venv/bin/poetry install --with dev -E pydantic-settings
	.venv/bin/pre-commit install
