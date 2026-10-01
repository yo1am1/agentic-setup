---
name: patch-review
description: Use after code edits to review diff minimality, unrelated changes, public behavior, and validation coverage.
---

# Patch Review Skill

Check:
- Is the diff minimal?
- Did the patch modify only relevant files?
- Did it preserve public behavior except the intended fix?
- Were tests run?
- Is there any hidden side effect?
- Should docs or comments change?
