.PHONY: check sync-agents
check:
	uv run python scripts/validate.py
	uv run python -m unittest discover -s tests -v
	uv run python scripts/sync_agent_adapters.py --write
	uv run python scripts/sync_agent_adapters.py --check
sync-agents:
	uv run python scripts/sync_agent_adapters.py --write
