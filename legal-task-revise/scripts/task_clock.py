#!/usr/bin/env python3
"""Track active task intervals without inventing lawyer hours or editing history."""

import argparse
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse(value):
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Clock timestamps must include a timezone")
    return value


def seconds(state, at=None):
    total = 0.0
    previous_end = None
    intervals = state["intervals"]
    if not intervals:
        raise ValueError("Clock has no recorded intervals")
    for index, interval in enumerate(intervals):
        start = parse(interval["start"])
        end_value = interval.get("end")
        if end_value is None and (index != len(intervals) - 1 or state["status"] != "running"):
            raise ValueError("Invalid open clock interval")
        end = parse(end_value) if end_value else (at or now())
        if end < start or (previous_end is not None and start < previous_end):
            raise ValueError("Clock moved backwards or intervals overlap")
        total += (end - start).total_seconds()
        previous_end = end
    return total


def stopped_minutes(path):
    state = json.loads(Path(path).read_text())
    if state.get("version") != 1 or state.get("status") != "stopped":
        raise ValueError("Finalize using a stopped version-1 task clock")
    measured = seconds(state)
    if not math.isfinite(measured) or measured < 0:
        raise ValueError("Invalid elapsed time")
    if abs(measured - state["active_seconds"]) > 0.002:
        raise ValueError("Clock total does not match its intervals")
    return math.floor(measured / 60 + 0.5)


def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".task-clock-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream, indent=2)
            stream.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "pause", "resume", "stop", "status"])
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args()
    try:
        at = now()
        if args.action == "start":
            if args.state.exists():
                raise ValueError("Clock already exists; use resume or a new path")
            state = {"version": 1, "status": "running", "intervals": [{"start": stamp(at), "end": None}]}
        else:
            state = json.loads(args.state.read_text())
            seconds(state, at)
            if args.action in {"pause", "stop"}:
                if state["status"] == "running":
                    state["intervals"][-1]["end"] = stamp(at)
                state["status"] = "paused" if args.action == "pause" else "stopped"
            elif args.action == "resume":
                if state["status"] == "running":
                    raise ValueError("Clock is already running")
                if at < parse(state["intervals"][-1]["end"]):
                    raise ValueError("Clock moved backwards")
                state["intervals"].append({"start": stamp(at), "end": None})
                state["status"] = "running"
        state["active_seconds"] = round(seconds(state, at), 6)
        if args.action != "status":
            save(args.state, state)
        print(json.dumps({"status": state["status"], "active_seconds": state["active_seconds"],
                          "word_minutes": math.floor(state["active_seconds"] / 60 + 0.5)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
