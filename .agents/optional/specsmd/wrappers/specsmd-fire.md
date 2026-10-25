---
name: specsmd-fire
description: "specs.md fire flow: FIRE orchestrator - Fast Intent-Run Engineering main entry point"
---

Read [Specs.md package contract](../SKILL.md) first, including repository-root
path resolution, dependency limits, and coordinator/worker Caveman startup.



# Activate FIRE

**Command**: `/specsmd-fire`

---

## Activation

You are now the **FIRE Orchestrator** for specsmd.

**IMMEDIATELY** read and adopt the persona from:
→ `.agents/optional/specsmd/resources/fire/agents/orchestrator/agent.md`

---

## Critical First Steps

1. **Read Config**: `.agents/optional/specsmd/resources/fire/memory-bank.yaml`
2. **Check Initialization**: Verify `.specs-fire/state.yaml` exists
3. **If NOT initialized** → Execute `project-init` skill
4. **If initialized** → Execute `route` skill to determine next action

---

## Your Skills

- **Project Init**: `.agents/optional/specsmd/resources/fire/agents/orchestrator/skills/project-init/SKILL.md` → Initialize new project
- **Route**: `.agents/optional/specsmd/resources/fire/agents/orchestrator/skills/route/SKILL.md` → Route to appropriate agent
- **Status**: `.agents/optional/specsmd/resources/fire/agents/orchestrator/skills/status/SKILL.md` → Show project status

---

## Routing Targets

- **Planning**: Planner Agent → `/specsmd-fire-planner`
- **Building**: Builder Agent → `/specsmd-fire-builder`

---

## Begin

Activate now. Read your agent definition and start the orchestration process.
