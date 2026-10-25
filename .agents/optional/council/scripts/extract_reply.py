"""Read a council researcher's latest reply from its CLI's local transcript (read-only).

The reply is the text between the last occurrence of --start before the last --marker
and that marker, inclusive of the marker.
"""

import argparse
import json
import pathlib
import sqlite3
import sys

HOME = pathlib.Path.home()


def claude_text(session_id: str) -> str:
    logs = list((HOME / ".claude/projects").glob(f"*/{session_id}.jsonl"))
    if not logs:
        sys.exit(f"no claude transcript for session {session_id}")
    parts = []
    for line in logs[0].open():
        entry = json.loads(line)
        if entry.get("type") == "assistant":
            parts += [
                c["text"]
                for c in entry["message"].get("content", [])
                if c.get("type") == "text"
            ]
    return "\n".join(parts)


def codex_text(session_id: str) -> str:
    logs = list((HOME / ".codex/sessions").rglob(f"*{session_id}.jsonl"))
    if not logs:
        sys.exit(f"no codex transcript for session {session_id}")
    parts = []
    for line in logs[0].open():
        entry = json.loads(line)
        payload = entry.get("payload", {})
        if (
            entry.get("type") == "response_item"
            and payload.get("type") == "message"
            and payload.get("role") == "assistant"
        ):
            parts.append(
                "".join(item.get("text", "") for item in payload.get("content", []))
            )
    return "\n".join(parts)


def agy_text(session_id: str, marker: str) -> str:
    db_path = HOME / ".gemini/antigravity-cli/conversations" / f"{session_id}.db"
    if not db_path.exists():
        sys.exit(f"no agy conversation db for session {session_id}")
    rows = (
        sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        .execute("select step_payload from steps order by idx")
        .fetchall()
    )
    # Prompts contain the marker too; the reply is the last step that has it.
    for (payload,) in reversed(rows):
        if payload and marker.encode() in payload:
            return payload.decode("utf-8", "replace")
    return ""


def cut_reply(text: str, start: str, marker: str) -> str:
    end = text.rfind(marker)
    if end < 0:
        return ""
    begin = text.rfind(start, 0, end)
    return text[max(begin, 0) : end + len(marker)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True, choices=["claude", "codex", "agy"])
    parser.add_argument("--session", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument(
        "--start", required=True, help="text that opens the reply, e.g. '1.' or 'VOTE:'"
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.kind == "claude":
        text = claude_text(args.session)
    elif args.kind == "codex":
        text = codex_text(args.session)
    else:
        text = agy_text(args.session, args.marker)

    reply = cut_reply(text, args.start, args.marker)
    if not reply:
        sys.exit(
            f"marker {args.marker!r} not found for {args.kind} session {args.session}"
        )
    pathlib.Path(args.out).write_text(reply)
    print(f"{args.kind}: {len(reply.split())} words -> {args.out}")


main()
