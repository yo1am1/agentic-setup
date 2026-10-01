.PHONY: check
check:
	uv run --no-project python scripts/validate.py
	uv run --no-project python -m unittest discover -s tests -v
