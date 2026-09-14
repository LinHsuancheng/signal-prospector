from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from signal_prospector.inbox import append_pending, organize
from signal_prospector.storage import Store


def _card(article_id: int, score: str = "") -> str:
    return (
        f"# Article {article_id}\n\n"
        f"ID: {article_id}\n"
        f"URL: https://example.com/{article_id}\n\n"
        "### Human Review\n\n"
        f"**human_score:** {score}\n"
        "**human_description:**\n"
    )


def test_organize_keeps_unscored_cards_when_separators_are_missing() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        store = Store(str(root / "store.sqlite"))
        try:
            for article_id in (1, 2, 3):
                store.save_result(
                    {
                        "url": f"https://example.com/{article_id}",
                        "title": f"Article {article_id}",
                        "content": "content",
                        "score": 8,
                        "reason": "reason",
                        "prompt_version": "test",
                        "prompt_hash": "test",
                    },
                    "2026-09-06T00:00:00+00:00",
                )

            inbox = root / "Inbox.md"
            inbox.write_text(_card(1, "7") + _card(2) + _card(3), encoding="utf-8")

            assert organize(store, str(inbox), str(root / "reviewed")) == 1
            remaining = inbox.read_text(encoding="utf-8")
            assert "ID: 1" not in remaining
            assert "ID: 2" in remaining
            assert "ID: 3" in remaining
            assert "---" in remaining
            assert store.db.execute("select count(*) from human_feedback").fetchone()[0] == 1
        finally:
            store.close()


def test_append_pending_keeps_one_separator_between_cards_after_sorting() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        store = Store(str(root / "store.sqlite"))
        try:
            for article_id in (1, 2):
                store.save_result(
                    {
                        "url": f"https://example.com/{article_id}",
                        "title": f"Article {article_id}",
                        "content": "content",
                        "score": 8,
                        "reason": "reason",
                        "prompt_version": "test",
                        "prompt_hash": "test",
                    },
                    "2026-09-06T00:00:00+00:00",
                )

            inbox = root / "Inbox.md"
            append_pending(store, str(inbox))

            text = inbox.read_text(encoding="utf-8")
            assert text.count("\n---\n") == 1
            assert text.count("\n\n---\n\n") == 1
        finally:
            store.close()


def test_organize_normalizes_existing_separator_runs_without_reviews() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        store = Store(str(root / "store.sqlite"))
        try:
            for article_id in (1, 2):
                store.save_result(
                    {
                        "url": f"https://example.com/{article_id}",
                        "title": f"Article {article_id}",
                        "content": "content",
                        "score": 8,
                        "reason": "reason",
                        "prompt_version": "test",
                        "prompt_hash": "test",
                    },
                    "2026-09-06T00:00:00+00:00",
                )

            inbox = root / "Inbox.md"
            inbox.write_text(_card(1) + "\n---\n\n---\n\n---\n\n" + _card(2), encoding="utf-8")

            assert organize(store, str(inbox), str(root / "reviewed")) == 0
            text = inbox.read_text(encoding="utf-8")
            assert text.count("\n---\n") == 1
            assert text.count("\n\n---\n\n") == 1
        finally:
            store.close()
