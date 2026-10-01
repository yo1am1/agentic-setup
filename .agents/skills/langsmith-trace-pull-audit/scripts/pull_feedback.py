"""Pull LangSmith root runs + feedback, or audit evaluation-key coverage.

Read-only: only calls runs.query_v2 / list_feedback. Safe to run against the
real LangSmith project.

Usage (from repo root):
    uv run python .agents/skills/langsmith-trace-pull-audit/scripts/pull_feedback.py [options]

Options:
    --days N        Lookback window in days (default: 1, matches EvaluationInput default)
    --limit N       Max root runs to fetch (default: 20)
    --keys k1,k2    Feedback keys to filter on (default: settings.evaluator_keys)
    --project NAME  LangSmith project (default: settings.langsmith_project)
    --audit         Report root runs missing any of the expected feedback keys,
                     instead of dumping individual feedback records
"""

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

import core  # noqa: E402,F401  (force full package init, avoids circular import)
from langsmith import AsyncClient  # noqa: E402
from config.settings import settings  # noqa: E402
from core.utils.dates import utcnow  # noqa: E402
from core.models import EvaluationInput  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--keys", type=str, default=None, help="comma-separated")
    parser.add_argument("--project", type=str, default=None)
    parser.add_argument("--audit", action="store_true")
    return parser.parse_args()


async def list_root_run_ids(
    dto: EvaluationInput, client: AsyncClient, limit: int
) -> list[str]:
    project = await client.read_project(project_name=dto.project_name)
    run_ids: list[str] = []
    async for run in client.runs.query_v2(
        project_ids=[str(project.id)],
        is_root=True,
        min_start_time=dto.start_time,
    ):
        run_ids.append(str(run.id))
        if len(run_ids) >= limit:
            break
    return run_ids


async def dump_feedback(
    dto: EvaluationInput, client: AsyncClient, run_ids: list[str]
) -> None:
    count = 0
    async for fb in client.list_feedback(
        run_ids=run_ids, feedback_key=dto.feedback_keys
    ):
        record = {
            "session_id": str(fb.session_id) if fb.session_id else None,
            "trace_id": str(fb.trace_id) if fb.trace_id else None,
            "run_id": str(fb.run_id) if fb.run_id else None,
            "comment": fb.comment,
            "key": fb.key,
            "score": fb.score,
            "created_at": fb.created_at.isoformat(),
        }
        print(json.dumps(record))
        count += 1
    print(
        f"# {count} feedback record(s) across {len(run_ids)} root run(s)",
        file=sys.stderr,
    )


async def audit_coverage(
    dto: EvaluationInput, client: AsyncClient, run_ids: list[str]
) -> None:
    seen_keys: dict[str, set[str]] = {rid: set() for rid in run_ids}
    async for fb in client.list_feedback(
        run_ids=run_ids, feedback_key=dto.feedback_keys
    ):
        seen_keys[str(fb.run_id)].add(fb.key)

    expected = set(dto.feedback_keys)
    for run_id, keys in seen_keys.items():
        missing = expected - keys
        if missing:
            print(f"{run_id}: missing {sorted(missing)}")
    print(
        f"# audited {len(run_ids)} root run(s) for keys {sorted(expected)}",
        file=sys.stderr,
    )


async def main() -> None:
    args = parse_args()
    dto = EvaluationInput(
        project_name=args.project or settings.langsmith_project,
        start_time=utcnow() - timedelta(days=args.days),
        **({"feedback_keys": args.keys.split(",")} if args.keys else {}),
    )
    client = AsyncClient()
    run_ids = await list_root_run_ids(dto, client, args.limit)

    if not run_ids:
        print("# no root runs in window", file=sys.stderr)
        return

    if args.audit:
        await audit_coverage(dto, client, run_ids)
    else:
        await dump_feedback(dto, client, run_ids)


if __name__ == "__main__":
    asyncio.run(main())
