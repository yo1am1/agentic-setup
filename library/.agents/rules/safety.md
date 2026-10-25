# Safety Rule

Agents must not:
- edit secrets or `.env` files;
- run destructive commands such as `rm -rf`, `git reset --hard`, or `git clean -fdx`;
- install new dependencies without a clear reason;
- rewrite unrelated files;
- change tests just to make an incorrect implementation pass.
