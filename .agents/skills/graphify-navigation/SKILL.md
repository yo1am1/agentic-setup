---
name: graphify-navigation
description: >
  Use when structural navigation is needed: inspect graph artifacts, identify candidate files,
  then inspect source files directly before editing.
---

# Graphify Navigation Skill

Use Graphify only for orientation.

Rule:
Graphify helps decide where to look.
Source files decide what is true.
Tests decide whether the change is valid.

Do not edit code based only on graph summaries.

When the graph carries semantic (LLM-written) node descriptions in addition to AST
structure, prefer them for narrowing candidate files before falling back to a manual
grep-style search.
