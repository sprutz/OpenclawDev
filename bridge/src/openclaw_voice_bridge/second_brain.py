from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SAFE_REL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


@dataclass(frozen=True)
class SecondBrainPaths:
    root: Path

    @property
    def journal_dir(self) -> Path:
        return self.root / "journal"

    @property
    def docs_dir(self) -> Path:
        return self.root / "docs"


def _resolve_root(root: str | Path) -> Path:
    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Second Brain root not found: {path}")
    return path


def resolve_under(root: Path, relative: str) -> Path:
    """Resolve a relative path under root; reject traversal."""
    rel = (relative or "").strip().lstrip("/")
    if not rel or not _SAFE_REL.match(rel) or ".." in rel.split("/"):
        raise ValueError("Invalid path")
    full = (root / rel).resolve()
    if not str(full).startswith(str(root.resolve()) + "/") and full != root.resolve():
        raise ValueError("Path escapes Second Brain root")
    return full


def list_journals(root: str | Path, *, limit: int = 14) -> list[dict[str, str | int]]:
    paths = SecondBrainPaths(_resolve_root(root))
    if not paths.journal_dir.is_dir():
        return []
    files = sorted(paths.journal_dir.glob("????-??-??.md"), reverse=True)
    out: list[dict[str, str | int]] = []
    for path in files[: max(1, limit)]:
        out.append(
            {
                "date": path.stem,
                "path": f"journal/{path.name}",
                "bytes": path.stat().st_size,
            }
        )
    return out


def list_docs(root: str | Path, *, limit: int = 50) -> list[dict[str, str | int]]:
    paths = SecondBrainPaths(_resolve_root(root))
    if not paths.docs_dir.is_dir():
        return []
    files = sorted(
        [p for p in paths.docs_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".txt"}],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out: list[dict[str, str | int]] = []
    for path in files[: max(1, limit)]:
        rel = path.relative_to(paths.root).as_posix()
        out.append({"path": rel, "bytes": path.stat().st_size, "title": path.stem.replace("-", " ")})
    return out


def newest_journal_date(root: str | Path) -> str | None:
    items = list_journals(root, limit=1)
    if not items:
        return None
    return str(items[0]["date"])


def read_daily_report(root: str | Path, day: str | None = None) -> dict[str, object]:
    paths = SecondBrainPaths(_resolve_root(root))
    requested = (day or "").strip()
    fallback = False
    if not requested:
        requested = date.today().isoformat()
    if not _DATE_RE.match(requested):
        raise ValueError("date must be YYYY-MM-DD")

    path = paths.journal_dir / f"{requested}.md"
    if not path.is_file():
        latest = newest_journal_date(root)
        if not latest:
            raise FileNotFoundError("No journal entries found in Second Brain")
        path = paths.journal_dir / f"{latest}.md"
        requested = latest
        fallback = True

    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return {
        "date": requested,
        "path": f"journal/{path.name}",
        "fallback_to_latest": fallback,
        "content": text,
        "spoken_text": _spoken_from_markdown(text),
    }


def read_doc(root: str | Path, relative_path: str) -> dict[str, object]:
    paths = SecondBrainPaths(_resolve_root(root))
    rel = (relative_path or "").strip().lstrip("/")
    if rel.startswith("journal/"):
        target = resolve_under(paths.root, rel)
    elif "/" not in rel and _DATE_RE.match(rel.removesuffix(".md")):
        target = resolve_under(paths.root, f"journal/{rel if rel.endswith('.md') else rel + '.md'}")
    else:
        # Default docs/ prefix when caller passes a bare filename.
        if not rel.startswith("docs/"):
            rel = f"docs/{rel}"
        target = resolve_under(paths.root, rel)
    if not target.is_file():
        raise FileNotFoundError(f"Not found: {rel}")
    text = target.read_text(encoding="utf-8", errors="replace").strip()
    return {
        "path": target.relative_to(paths.root).as_posix(),
        "content": text,
        "spoken_text": _spoken_from_markdown(text),
    }


def search_second_brain(
    root: str | Path,
    query: str,
    *,
    limit: int = 8,
) -> list[dict[str, object]]:
    q = (query or "").strip().lower()
    if len(q) < 2:
        raise ValueError("query is too short")
    paths = SecondBrainPaths(_resolve_root(root))
    candidates: list[Path] = []
    if paths.journal_dir.is_dir():
        candidates.extend(sorted(paths.journal_dir.glob("????-??-??.md"), reverse=True)[:60])
    if paths.docs_dir.is_dir():
        candidates.extend(
            p for p in paths.docs_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".txt"}
        )

    hits: list[dict[str, object]] = []
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        name = path.name.lower()
        hay = f"{name}\n{text.lower()}"
        if q not in hay:
            continue
        # Prefer a matching line for the snippet.
        snippet = ""
        for line in text.splitlines():
            if q in line.lower():
                snippet = line.strip()
                break
        if not snippet:
            snippet = text.strip().splitlines()[0] if text.strip() else path.name
        hits.append(
            {
                "path": path.relative_to(paths.root).as_posix(),
                "title": path.stem.replace("-", " "),
                "snippet": snippet[:240],
                "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )
        if len(hits) >= limit:
            break
    return hits


def _spoken_from_markdown(text: str, *, max_chars: int = 3500) -> str:
    """Light cleanup so Grok can read the report aloud without markdown noise."""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"^\s*[-*]\s+", "", line)
        line = re.sub(r"^\s*\d+\.\s+", "", line)
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 20].rstrip() + "\n… (truncated for speech)"
    return cleaned
