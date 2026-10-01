"""Verify PostHog identity resolution and/or dry-run a capture call.

Never sends a real event: the underlying posthog.Posthog.capture is stubbed
at the transport layer before any capture happens, so this is safe to run
against the real, shared PostHog project.

Usage (from repo root):
    # Show what distinct_id/session_id PostHogCallbackHandler would resolve
    # for a given LangChain run metadata dict:
    uv run python .agents/skills/posthog-llm-observability/scripts/verify_capture.py \\
        --metadata '{"posthog_distinct_id": "abc"}'

    # Dry-run a new capture call and inspect the exact kwargs that would be sent:
    uv run python .agents/skills/posthog-llm-observability/scripts/verify_capture.py \\
        --event my_new_event --properties '{"$ai_trace_id": "..."}' --distinct-id foo
"""

import argparse
import functools
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

import core  # noqa: E402,F401  (force full package init, avoids circular import)
from lib.analytics import get_analytics_client  # noqa: E402
from lib.posthog_callback import PostHogCallbackHandler  # noqa: E402


def record_capture(captured: list[dict[str, Any]], *args: Any, **kwargs: Any) -> str:
    captured.append(kwargs)
    return "stubbed-no-network-call"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=str, default=None, help="JSON object")
    parser.add_argument("--event", type=str, default=None)
    parser.add_argument("--properties", type=str, default=None, help="JSON object")
    parser.add_argument("--distinct-id", type=str, default=None)
    return parser.parse_args()


def check_identity_resolution(metadata_json: str) -> None:
    metadata = json.loads(metadata_json)
    handler = PostHogCallbackHandler()
    distinct_id = handler._get_distinct_id(metadata)
    session_id = handler._get_session_id(metadata)
    print(f"resolved distinct_id: {distinct_id}")
    print(f"resolved session_id:  {session_id}")


def dry_run_capture(
    event: str, properties_json: str | None, distinct_id: str | None
) -> None:
    properties = json.loads(properties_json) if properties_json else {}

    client = get_analytics_client()
    if type(client).__name__ == "NullAnalyticsClient":
        print(
            "# posthog_api_key not set — using NullAnalyticsClient, "
            "nothing would be sent even without this dry run",
            file=sys.stderr,
        )

    captured = []
    underlying = getattr(client, "_client", None)
    if underlying is not None:
        real_capture = underlying.capture
        underlying.capture = functools.partial(record_capture, captured)
        try:
            client.capture(
                event=event,
                distinct_id=distinct_id or "verify-script",
                properties=properties,
            )
        finally:
            underlying.capture = real_capture
    else:
        client.capture(
            event=event,
            distinct_id=distinct_id or "verify-script",
            properties=properties,
        )

    if captured:
        print(json.dumps(captured[0], indent=2, default=str))
        if "$ai_trace_id" not in captured[0].get("properties", {}):
            print(
                "# warning: no $ai_trace_id in properties — this event will not "
                "appear in a PostHog trace timeline",
                file=sys.stderr,
            )
    print("# no network capture was sent (stubbed at transport layer)", file=sys.stderr)


def main() -> None:
    args = parse_args()
    if not args.metadata and not args.event:
        print(__doc__)
        sys.exit(1)

    if args.metadata:
        check_identity_resolution(args.metadata)

    if args.event:
        dry_run_capture(args.event, args.properties, args.distinct_id)


if __name__ == "__main__":
    main()
