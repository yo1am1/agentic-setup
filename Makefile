.DEFAULT_GOAL := help
.PHONY: help ai simple full ai-test check check-setup sync-agents

help:
	@echo "make ai simple | make ai full | make ai-test"

AI_MODE := $(filter simple full,$(MAKECMDGOALS))
ifneq ($(words $(AI_MODE)),0)
ifneq ($(words $(AI_MODE)),1)
$(error Usage: make ai simple OR make ai full)
endif
ifeq ($(filter ai,$(MAKECMDGOALS)),)
$(error Usage: make ai simple OR make ai full)
endif
endif

ai:
ifeq ($(AI_MODE),)
	@echo "Choose make ai simple OR make ai full (nothing was installed)."
else
	python3 .agents/adapters/sync.py --host all --layout $(AI_MODE) --write
endif

simple full:
	@:

ai-test:
	python3 -B -m unittest discover -s .agents/adapters/tests -v
	python3 -B -m unittest discover -s .agents/tests -v

check:
	uv run python scripts/validate.py
	uv run python -m unittest discover -s tests -v
	$(MAKE) ai-test

check-setup:
	$(MAKE) ai-test

sync-agents:
	python3 .agents/adapters/sync.py --host all --layout simple --write
