from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: str) -> None:
        self.path = str(Path(path).expanduser())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            create table if not exists processed_urls (
                url_hash text primary key,
                canonical_url text not null,
                first_processed_at text not null,
                last_seen_at text not null
            );
            create table if not exists llm_articles (
                id integer primary key,
                url_hash text unique not null,
                url text not null,
                title text not null,
                author text,
                content text not null,
                llm_score real not null,
                llm_pattern text not null default '[]',
                llm_reason text not null,
                prompt_version text not null,
                prompt_hash text not null,
                scored_at text not null,
                inbox_appended_at text,
                surface_meta text not null default '{}'
            );
            create table if not exists human_feedback (
                article_id integer primary key,
                human_score integer not null check(human_score between 0 and 10),
                human_description text not null default '',
                updated_at text not null,
                foreign key(article_id) references llm_articles(id)
            );
            """
        )
        columns = {row[1] for row in self.db.execute("pragma table_info(llm_articles)")}
        if "llm_pattern" not in columns:
            self.db.execute("alter table llm_articles add column llm_pattern text not null default '[]'")
        if "surface_meta" not in columns:
            self.db.execute("alter table llm_articles add column surface_meta text not null default '{}' ")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def processed(self, value: str) -> bool:
        return self.db.execute(
            "select 1 from processed_urls where url_hash = ?", (value,)
        ).fetchone() is not None

    def touch_processed(self, value: str, url: str, now: str) -> None:
        self.db.execute(
            """
            insert into processed_urls(url_hash, canonical_url, first_processed_at, last_seen_at)
            values (?, ?, ?, ?)
            on conflict(url_hash) do update set last_seen_at = excluded.last_seen_at
            """,
            (value, url, now, now),
        )
        self.db.commit()

    def all_articles(self) -> list[sqlite3.Row]:
        return list(self.db.execute("select id, llm_score from llm_articles"))

    def save_result(
        self, article: dict[str, Any], now: str, threshold: float = 5.0
    ) -> int | None:
        value = url_hash(article["url"])
        self.db.execute("begin")
        try:
            self.db.execute(
                "insert into processed_urls values (?, ?, ?, ?)",
                (value, article["url"], now, now),
            )
            if article["score"] < threshold:
                self.db.commit()
                return None
            cur = self.db.execute(
                """
                insert into llm_articles(
                    url_hash, url, title, author, content, llm_score, llm_pattern, llm_reason,
                    prompt_version, prompt_hash, scored_at
                    , surface_meta
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    value, article["url"], article["title"], article.get("author"),
                    article["content"], article["score"], json.dumps(article.get("pattern", []), ensure_ascii=False), article["reason"],
                    article["prompt_version"], article["prompt_hash"], now,
                    json.dumps(article.get("surface_meta") or {}, ensure_ascii=False),
                ),
            )
            self.db.commit()
            return int(cur.lastrowid)
        except Exception:
            self.db.rollback()
            raise

    def pending_inbox(self) -> list[sqlite3.Row]:
        return list(self.db.execute(
            "select * from llm_articles where inbox_appended_at is null order by id"
        ))

    def mark_inbox_appended(self, article_id: int, now: str) -> None:
        self.db.execute(
            "update llm_articles set inbox_appended_at = ? where id = ?",
            (now, article_id),
        )
        self.db.commit()

    def save_human(self, article_id: int, score: int, description: str, now: str) -> None:
        self.db.execute(
            """
            insert into human_feedback(article_id, human_score, human_description, updated_at)
            values (?, ?, ?, ?)
            on conflict(article_id) do update set
                human_score = excluded.human_score,
                human_description = excluded.human_description,
                updated_at = excluded.updated_at
            """,
            (article_id, score, description, now),
        )
        self.db.commit()
