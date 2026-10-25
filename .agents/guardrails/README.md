# Optional Git guardrails

Hooks are uninstalled. `make ai` never activates them or runs application checks.
Default [policy](policy.json) has no project checks. A user may explicitly configure
project checks, then separately authorize hook use or installation.

For an authorized one-off action:

```sh
GUARDRAILS_AUTHORIZED=1 .agents/guardrails/pre-commit
```

The runner checks an isolated index tree and confirms the index remains unchanged.
Configured failures fail closed. Pre-push checks outgoing trees and treats deletion
as a separate review action. Local hooks are bypassable and are not remote access
controls. No CI or protected-branch policy is installed here.

Environment tests: `python3 -m unittest discover -s .agents/tests -v`.
