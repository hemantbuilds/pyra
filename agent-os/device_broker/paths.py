"""Path jail — prevent traversal and symlink escapes."""

from __future__ import annotations

from pathlib import Path


class PathJailError(ValueError):
    pass


def realpath(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def normalize_join(base: Path, raw: str | Path) -> Path:
    """Join and collapse .. without escaping via string tricks before resolve."""
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    # Collapse lexical .. before symlink resolve
    parts: list[str] = []
    for part in candidate.parts:
        if part == "..":
            if parts and parts[-1] not in ("/", ""):
                parts.pop()
            continue
        if part in (".",):
            continue
        parts.append(part)
    if candidate.is_absolute():
        return Path(*parts) if parts else Path("/")
    return Path(*parts) if parts else Path(".")


def resolve_in_roots(
    raw: str | Path,
    roots: list[Path],
    *,
    must_exist: bool = False,
    for_write: bool = False,
) -> Path:
    """
    Resolve ``raw`` so the real path stays under one of ``roots``.

    For writes to new paths: every existing ancestor must be inside a root,
    and the final normalized path must also fall under that root.
    """
    if not roots:
        raise PathJailError("no approved roots configured")

    real_roots = [realpath(r) for r in roots]
    primary = real_roots[0]

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = primary / candidate
    candidate = normalize_join(Path("/"), candidate) if candidate.is_absolute() else candidate

    if candidate.exists() or candidate.is_symlink():
        target = realpath(candidate)
        if not any(is_under(target, root) for root in real_roots):
            raise PathJailError(f"path outside approved roots: {raw}")
        if must_exist and not target.exists():
            raise PathJailError(f"path does not exist: {raw}")
        return target

    # Non-existent path (create/write): jail via existing parent + lexical target
    parent = candidate.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if not parent.exists():
        raise PathJailError(f"cannot resolve parent for: {raw}")

    real_parent = realpath(parent)
    # Rebuild target under real parent
    try:
        rel = candidate.relative_to(parent)
    except ValueError:
        rel = Path(candidate.name)
    target = real_parent / rel
    target = normalize_join(Path("/"), target)

    if not any(is_under(target, root) or is_under(real_parent, root) for root in real_roots):
        raise PathJailError(f"path outside approved roots: {raw}")
    if not any(is_under(target, root) for root in real_roots):
        raise PathJailError(f"path outside approved roots: {raw}")
    if must_exist:
        raise PathJailError(f"path does not exist: {raw}")
    if for_write and not any(is_under(real_parent, root) for root in real_roots):
        raise PathJailError(f"parent outside approved roots: {raw}")
    return target
