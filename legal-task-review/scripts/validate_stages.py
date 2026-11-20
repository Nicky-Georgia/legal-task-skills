#!/usr/bin/env python3
"""Validate and safely merge Stage 1 and humanized legal-review JSON."""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from pathlib import Path


RATINGS = {"Looks sound", "Minor concerns", "Major concerns", "Not assessed"}
RECOMMENDATIONS = {
    "Promising",
    "Minor revision",
    "Major revision",
    "Unsuitable",
    "Insufficient information",
}
DIMENSIONS = (
    "legal_workflow",
    "matter_realism",
    "reference_answer_work_product",
    "task_scoring_rubric",
)
TEXT_PATHS = (
    ("legal_workflow", "comment"),
    ("matter_realism", "comment"),
    ("reference_answer_work_product", "comment"),
    ("task_scoring_rubric", "comment"),
    ("recommendation_summary",),
    ("suggestions",),
)
EXPECTED_KEYS = {
    *DIMENSIONS,
    "recommendation",
    "recommendation_summary",
    "suggestions",
    "estimated_work_hours",
}


class ValidationError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage1", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--repair-output", required=True, type=Path)
    return parser.parse_args()


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"Expected an object in {path}")
    return data


def validate_shape(review: dict, label: str) -> None:
    if set(review) != EXPECTED_KEYS:
        missing = sorted(EXPECTED_KEYS - set(review))
        extra = sorted(set(review) - EXPECTED_KEYS)
        raise ValidationError(f"{label} keys mismatch; missing={missing}, extra={extra}")
    for dimension in DIMENSIONS:
        value = review[dimension]
        if not isinstance(value, dict) or set(value) != {"rating", "comment"}:
            raise ValidationError(f"{label}.{dimension} must contain rating and comment")
        if value["rating"] not in RATINGS:
            raise ValidationError(f"Invalid {label}.{dimension}.rating")
        if not isinstance(value["comment"], str):
            raise ValidationError(f"{label}.{dimension}.comment must be a string")
    if review["recommendation"] not in RECOMMENDATIONS:
        raise ValidationError(f"Invalid {label}.recommendation")
    for field in ("recommendation_summary", "suggestions"):
        if not isinstance(review[field], str):
            raise ValidationError(f"{label}.{field} must be a string")
    hours = review["estimated_work_hours"]
    if hours != "Cannot estimate" and not (
        type(hours) in (int, float)
        and hours > 0
        and (isinstance(hours, int) or math.isfinite(hours))
    ):
        raise ValidationError(
            f"{label}.estimated_work_hours must be a positive finite number "
            "or 'Cannot estimate'"
        )


def get_path(document: dict, parts: tuple[str, ...]) -> str:
    value = document
    for part in parts:
        value = value[part]
    return value


def set_path(document: dict, parts: tuple[str, ...], value: str) -> None:
    target = document
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


def protected_tokens(text: str) -> list[str]:
    patterns = (
        r"`[^`]+`",
        r"\b\d+(?:[.,]\d+)*(?:\s*(?:%|hours?|days?|years?))?\b",
        r"\b[A-Z]{1,8}[-_.]\d+(?:\.\d+)*\b",
    )
    tokens = []
    for pattern in patterns:
        tokens.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    return sorted(token.strip() for token in tokens)


def merge(stage1: dict, final: dict) -> tuple[dict, list[str], list[str]]:
    checked = copy.deepcopy(final)
    repaired = []
    errors = []

    for dimension in DIMENSIONS:
        if checked[dimension]["rating"] != stage1[dimension]["rating"]:
            checked[dimension]["rating"] = stage1[dimension]["rating"]
            repaired.append(f"{dimension}.rating")
    if checked["recommendation"] != stage1["recommendation"]:
        checked["recommendation"] = stage1["recommendation"]
        repaired.append("recommendation")
    if checked["estimated_work_hours"] != stage1["estimated_work_hours"]:
        checked["estimated_work_hours"] = stage1["estimated_work_hours"]
        repaired.append("estimated_work_hours")

    for parts in TEXT_PATHS:
        before = get_path(stage1, parts)
        after = get_path(checked, parts)
        field = ".".join(parts)
        if not before or before == "No further suggestions":
            if after != before:
                set_path(checked, parts, before)
                repaired.append(field)
            continue
        if protected_tokens(before) != protected_tokens(after):
            set_path(checked, parts, before)
            repaired.append(field)
            after = before
        if "—" in after or "–" in after:
            errors.append(f"{field} contains an em dash or en dash")

    return checked, repaired, errors


def main() -> int:
    args = parse_args()
    try:
        stage1 = read_json(args.stage1)
        final = read_json(args.final)
        validate_shape(stage1, "stage1")
        validate_shape(final, "final")
        checked, repaired, errors = merge(stage1, final)
        args.repair_output.write_text(
            json.dumps(checked, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValidationError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 1

    report = {
        "valid": not errors,
        "repaired_fields": repaired,
        "errors": errors,
        "output": str(args.repair_output.resolve()),
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
