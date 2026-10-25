# Project safety rules

- Preserve existing user changes, secrets and local configuration.
- Follow the consuming project's dependency, data and deployment rules.
- Never commit credentials, tokens, private keys or live session state.
- Validate inputs at trust boundaries and preserve authorization checks.
- Reading access does not authorize paid actions, external messages, publication,
  deletion or deployment. Use the user's existing authorization for each action.
- Do not install tools, plugins, hooks or global configuration merely because
  a skill or workflow mentions them.
- Run offline tests with isolated fixtures. Live tests require authorization
  for their actual side effects and costs.
- Report uncertain outcomes before retrying actions that may already have happened.
