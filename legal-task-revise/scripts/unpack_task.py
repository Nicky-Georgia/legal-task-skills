#!/usr/bin/env python3
"""Safely unpack a legal evaluation task package and emit a role manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath


MAX_FILES = 500
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 250 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200

ROLE_ALIASES = {
    "materials": "materials",
    "material": "materials",
    "case": "materials",
    "case_materials": "materials",
    "matter": "materials",
    "matter_materials": "materials",
    "reference": "reference_answer",
    "reference_answer": "reference_answer",
    "reference_answers": "reference_answer",
    "answer": "reference_answer",
    "model_answer": "reference_answer",
    "grading_rubric": "grading_rubric",
    "grading": "grading_rubric",
    "rubric": "grading_rubric",
    "evaluation_rubric": "grading_rubric",
    "matter_files": "materials",
    "review": "reviews",
    "reviews": "reviews",
    "review_1": "reviews",
    "review_2": "reviews",
    "review1": "reviews",
    "review2": "reviews",
}


class PackageError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--combined", action="append", default=[], type=Path)
    parser.add_argument("--materials", action="append", default=[], type=Path)
    parser.add_argument("--reference", action="append", default=[], type=Path)
    parser.add_argument("--rubric", action="append", default=[], type=Path)
    parser.add_argument("--reviews", action="append", default=[], type=Path)
    return parser.parse_args()


def normalize_segment(segment: str) -> str:
    return re.sub(r"^_+|_+$", "", re.sub(r"[\s-]+", "_", segment.lower()))


def infer_role(member_name: str, default_role: str, combined: bool) -> str:
    if not combined:
        return default_role
    # The nearest role directory wins over a generic wrapper named "case".
    for segment in reversed(member_name.split("/")[:-1]):
        role = ROLE_ALIASES.get(normalize_segment(segment))
        if role:
            return role
    stem = normalize_segment(PurePosixPath(member_name).stem)
    if stem in {"review", "reviews", "review1", "review2", "review_1", "review_2"}:
        return "reviews"
    return default_role


def safe_member_name(raw_name: str) -> str:
    normalized = raw_name.replace("\\", "/")
    if "\x00" in normalized or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise PackageError(f"Unsafe absolute ZIP path: {raw_name}")
    if any(part in {"", ".", ".."} for part in normalized.rstrip("/").split("/")):
        raise PackageError(f"Unsafe ZIP path: {raw_name}")
    pure = PurePosixPath(normalized)
    if not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise PackageError(f"Unsafe ZIP path: {raw_name}")
    return "/".join(pure.parts)


def ignored_metadata(member_name: str) -> bool:
    parts = member_name.split("/")
    base = parts[-1]
    return (
        "__MACOSX" in parts
        or base in {".DS_Store", "Thumbs.db"}
        or base.startswith("._")
    )


def is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def validate_output(output: Path) -> Path:
    resolved = output.expanduser().resolve()
    if resolved in {Path("/"), Path.home().resolve()}:
        raise PackageError("Refusing to use a broad output directory.")
    if resolved.exists() and any(resolved.iterdir()):
        raise PackageError(f"Output directory is not empty: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def copy_member(source, destination: Path) -> str:
    digest = hashlib.sha256()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as target:
        while chunk := source.read(1024 * 1024):
            target.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def inspect_archives(specs: list[tuple[Path, str, bool]]) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    for archive_path, _, _ in specs:
        if not archive_path.is_file():
            raise PackageError(f"ZIP file not found: {archive_path}")
        if archive_path.suffix.lower() != ".zip":
            raise PackageError(f"Expected a .zip file: {archive_path}")
        try:
            with zipfile.ZipFile(archive_path) as archive:
                seen = set()
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    member_name = safe_member_name(info.filename)
                    if ignored_metadata(member_name):
                        continue
                    if is_symlink(info):
                        raise PackageError(
                            f"ZIP symlinks are not allowed: {archive_path}/{member_name}"
                        )
                    key = member_name.casefold()
                    if key in seen:
                        raise PackageError(f"Duplicate ZIP destination: {member_name}")
                    seen.add(key)
                    if info.flag_bits & 1:
                        raise PackageError(f"Encrypted ZIP member: {member_name}")
                    file_count += 1
                    total_bytes += info.file_size
                    if info.file_size > MAX_FILE_BYTES:
                        raise PackageError(
                            f"File exceeds {MAX_FILE_BYTES // 1024 // 1024} MB: "
                            f"{archive_path}/{member_name}"
                        )
                    if (
                        info.file_size > 1024 * 1024
                        and info.compress_size > 0
                        and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
                    ):
                        raise PackageError(
                            f"Suspicious compression ratio: {archive_path}/{member_name}"
                        )
        except zipfile.BadZipFile as exc:
            raise PackageError(f"Unreadable ZIP file: {archive_path}") from exc
    if file_count > MAX_FILES:
        raise PackageError(f"Package has {file_count} files; limit is {MAX_FILES}.")
    if total_bytes > MAX_TOTAL_BYTES:
        raise PackageError(
            f"Package expands to {total_bytes / 1024 / 1024:.1f} MB; "
            f"limit is {MAX_TOTAL_BYTES // 1024 // 1024} MB."
        )
    return file_count, total_bytes


def unpack(specs: list[tuple[Path, str, bool]], output: Path) -> dict:
    expected_count, total_bytes = inspect_archives(specs)
    records = []
    role_counts = {"materials": 0, "reference_answer": 0, "grading_rubric": 0, "reviews": 0, "unclassified": 0}

    for archive_index, (archive_path, default_role, combined) in enumerate(specs, 1):
        archive_path = archive_path.expanduser().resolve()
        archive_bucket = f"archive-{archive_index:02d}"
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                member_name = safe_member_name(info.filename)
                if ignored_metadata(member_name):
                    continue
                role = infer_role(member_name, default_role, combined)
                destination = output / role / archive_bucket / member_name
                destination_resolved = destination.resolve()
                if output not in destination_resolved.parents:
                    raise PackageError(f"Unsafe extraction destination: {member_name}")
                try:
                    with archive.open(info, "r") as source:
                        sha256 = copy_member(source, destination_resolved)
                except RuntimeError as exc:
                    raise PackageError(
                        f"Cannot extract encrypted or invalid member: {member_name}"
                    ) from exc
                role_counts[role] += 1
                records.append(
                    {
                        "role": role,
                        "archive": str(archive_path),
                        "source_path": member_name,
                        "extracted_path": str(destination_resolved),
                        "bytes": info.file_size,
                        "sha256": sha256,
                    }
                )

    if len(records) != expected_count:
        raise PackageError("Extracted file count did not match the validated archive count.")
    missing = [role for role in ("materials", "reference_answer", "grading_rubric") if role_counts[role] == 0]
    if missing:
        raise PackageError(
            "Missing required package role(s): " + ", ".join(missing)
        )

    manifest = {
        "version": 1,
        "file_count": len(records),
        "total_uncompressed_bytes": total_bytes,
        "role_counts": role_counts,
        "files": records,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    args = parse_args()
    specs: list[tuple[Path, str, bool]] = []
    specs.extend((path, "unclassified", True) for path in args.combined)
    specs.extend((path, "materials", False) for path in args.materials)
    specs.extend((path, "reference_answer", False) for path in args.reference)
    specs.extend((path, "grading_rubric", False) for path in args.rubric)
    specs.extend((path, "reviews", False) for path in args.reviews)
    if not specs:
        print("error: provide at least one ZIP input", file=sys.stderr)
        return 2

    try:
        output = validate_output(args.output)
        manifest = unpack(specs, output)
    except (OSError, PackageError, zipfile.BadZipFile, NotImplementedError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
