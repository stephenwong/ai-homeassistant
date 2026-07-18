"""Shared primitives for backup CLIs (prune, changelog, search).

Holds the backup-directory location, filename parsing, listing, and
tarball iteration so the three backup CLIs don't reach into each
other's modules for shared types.
"""

import re
import tarfile
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path(__file__).parent.parent / "backups"
_BACKUP_RE = re.compile(r"^ha_config_(\d{8})_(\d{6})\.tar\.gz$")


def parse_backup_filename(filename: str) -> datetime | None:
    """Parse backup filename and return datetime object."""
    match = _BACKUP_RE.match(filename)
    if not match:
        return None

    date_str = match.group(1)  # YYYYMMDD
    time_str = match.group(2)  # HHMMSS

    try:
        return datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S").astimezone()
    except ValueError:
        return None


def get_backups() -> list[dict]:
    """Get all backup files with their timestamps."""
    if not BACKUP_DIR.exists():
        return []

    backups = []
    for file in BACKUP_DIR.glob("*.tar.gz"):
        timestamp = parse_backup_filename(file.name)
        if timestamp:
            backups.append(
                {"path": file, "filename": file.name, "timestamp": timestamp}
            )

    return sorted(backups, key=lambda x: (x["timestamp"], x["filename"]))


def iter_tarball_file_members(path: Path) -> Iterator[tuple[str, object]]:
    """Yield ``(normalized_name, file_obj)`` for each regular file in a gzipped tarball.

    Skips non-file members (directories, symlinks) and members where
    ``extractfile()`` returns None or raises KeyError. Member names are
    normalized by stripping a leading ``./`` prefix.

    Raises ``tarfile.TarError`` or ``OSError`` if the archive cannot be
    opened. Callers should catch these and apply their own error-reporting
    policy (the two callers have different return-value contracts on error).

    The caller MUST consume each yielded file_obj before advancing the
    iterator — the file_obj is only valid while the underlying tarfile
    handle is open, and it is closed when the iterator advances or exits.
    """
    with tarfile.open(path, "r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            name = member.name.removeprefix("./")
            try:
                extracted = tar.extractfile(member)
            except KeyError:
                continue
            if extracted is None:
                continue
            yield name, extracted
