"""Artifact storage — filesystem + JSON sidecar metadata. No database writes.

Per the platform decision, artifacts and their metadata live entirely on the
persistent /data volume — never in alaska.db or alaska_pmf.db. Layout:

    <base>/<owner_skill>/<run_id>/<filename>            # the artifact
    <base>/<owner_skill>/<run_id>/<filename>.meta.json  # its metadata sidecar
    <base>/index.jsonl                                  # append-only registry

`<base>` is $ALASKA_ARTIFACTS_DIR or /data/workspace/artifacts. Tests point the
env var at a tempdir. Re-runs never overwrite an existing artifact unless
overwrite=True (so a retry can't clobber a prior good report).

    store_artifact(path, artifact_type, owner_skill, run_id) -> metadata dict
    get_artifact_metadata(artifact_id) -> metadata dict | None
    list_artifacts(owner_skill=None) -> list[metadata dict]
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("alaska_artifacts.store")

DEFAULT_BASE = "/data/workspace/artifacts"
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class ArtifactExistsError(FileExistsError):
    """An artifact already exists at the target path and overwrite was not set."""


def artifacts_base() -> str:
    """Resolved base dir: $ALASKA_ARTIFACTS_DIR or the /data default."""
    return os.environ.get("ALASKA_ARTIFACTS_DIR", DEFAULT_BASE)


def _safe(segment: str, *, field: str) -> str:
    """Sanitize a path segment (owner_skill / run_id) — no traversal, no slashes."""
    cleaned = _SAFE.sub("-", str(segment)).strip("-")
    if not cleaned:
        raise ValueError("%s must contain at least one safe character: %r" % (field, segment))
    return cleaned


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def store_artifact(
    path: str,
    artifact_type: str,
    owner_skill: str,
    run_id: str,
    *,
    overwrite: bool = False,
    base_dir: Optional[str] = None,
    now: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Copy `path` into the artifact store and write its metadata sidecar.

    The source file is left untouched (copy, not move). Returns the metadata
    dict (also persisted as <artifact>.meta.json and appended to index.jsonl).
    Raises FileNotFoundError if the source is missing, ArtifactExistsError if the
    destination exists and overwrite is False.
    """
    if not os.path.exists(path):
        raise FileNotFoundError("artifact source does not exist: %s" % path)

    base = base_dir or artifacts_base()
    owner = _safe(owner_skill, field="owner_skill")
    run = _safe(run_id, field="run_id")
    filename = os.path.basename(path)
    dest_dir = os.path.join(base, owner, run)
    dest = os.path.join(dest_dir, filename)

    if os.path.exists(dest) and not overwrite:
        raise ArtifactExistsError(
            "artifact already exists (pass overwrite=True to replace): %s" % dest)

    os.makedirs(dest_dir, exist_ok=True)
    shutil.copy2(path, dest)
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass

    artifact_id = "%s/%s/%s" % (owner, run, filename)
    metadata: Dict[str, Any] = {
        "artifact_id": artifact_id,
        "owner_skill": owner,
        "run_id": run,
        "artifact_type": artifact_type,
        "filename": filename,
        "path": os.path.abspath(dest),
        "bytes": os.path.getsize(dest),
        "sha256": _sha256(dest),
        "created_at": now or datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        metadata["extra"] = extra

    meta_path = dest + ".meta.json"
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, sort_keys=True)
    try:
        os.chmod(meta_path, 0o600)
    except OSError:
        pass

    _append_index(base, metadata)
    logger.info("stored artifact %s (%d bytes) at %s", artifact_id, metadata["bytes"], metadata["path"])
    return metadata


def _append_index(base: str, metadata: Dict[str, Any]) -> None:
    os.makedirs(base, exist_ok=True)
    line = json.dumps({k: metadata[k] for k in (
        "artifact_id", "owner_skill", "run_id", "artifact_type", "path",
        "bytes", "created_at")}, sort_keys=True)
    with open(os.path.join(base, "index.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def get_artifact_metadata(artifact_id: str, *, base_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load the metadata sidecar for a stored artifact, or None if not found."""
    base = base_dir or artifacts_base()
    # artifact_id is "<owner>/<run>/<filename>" — keep it inside the base dir.
    candidate = os.path.normpath(os.path.join(base, artifact_id + ".meta.json"))
    if not candidate.startswith(os.path.normpath(base) + os.sep):
        return None
    if not os.path.exists(candidate):
        return None
    try:
        with open(candidate, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def list_artifacts(owner_skill: Optional[str] = None, *, base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return index rows, optionally filtered by owner_skill."""
    base = base_dir or artifacts_base()
    index = os.path.join(base, "index.jsonl")
    if not os.path.exists(index):
        return []
    rows: List[Dict[str, Any]] = []
    with open(index, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if owner_skill is None or row.get("owner_skill") == _safe(owner_skill, field="owner_skill"):
                rows.append(row)
    return rows
