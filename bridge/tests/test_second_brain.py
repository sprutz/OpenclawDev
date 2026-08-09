from __future__ import annotations

from pathlib import Path

import pytest

from openclaw_voice_bridge.second_brain import (
    list_journals,
    read_daily_report,
    read_doc,
    resolve_under,
    search_second_brain,
)


def _seed(root: Path) -> None:
    (root / "journal").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "journal" / "2026-04-18.md").write_text(
        "# Journal - April 18, 2026\n\n## Highlights\n- Built FactoryCommand agents\n",
        encoding="utf-8",
    )
    (root / "docs" / "terafab-notes.md").write_text(
        "# Terafab\nOpportunity notes for QDS.\n",
        encoding="utf-8",
    )


def test_read_daily_report_fallback(tmp_path: Path):
    root = tmp_path / "second-brain"
    _seed(root)
    data = read_daily_report(root, "2026-08-09")
    assert data["date"] == "2026-04-18"
    assert data["fallback_to_latest"] is True
    assert "FactoryCommand" in str(data["spoken_text"])


def test_search_and_read_doc(tmp_path: Path):
    root = tmp_path / "second-brain"
    _seed(root)
    hits = search_second_brain(root, "terafab")
    assert hits and hits[0]["path"] == "docs/terafab-notes.md"
    doc = read_doc(root, "terafab-notes.md")
    assert "Opportunity" in str(doc["content"])


def test_path_traversal_rejected(tmp_path: Path):
    root = tmp_path / "second-brain"
    _seed(root)
    with pytest.raises(ValueError):
        resolve_under(root.resolve(), "../secret.txt")
    assert list_journals(root, limit=1)[0]["date"] == "2026-04-18"
