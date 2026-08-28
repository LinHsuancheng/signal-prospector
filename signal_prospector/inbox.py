from __future__ import annotations

import re
from datetime import datetime, timezone
import json
from pathlib import Path

from .storage import Store


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_name(url: str) -> str:
    if "zhihu.com" in url:
        return "知乎"
    return url.split("//", 1)[-1].split("/", 1)[0]


def _surface_value(value: object) -> str:
    """Keep the numeric part of social counters, dropping UI labels."""
    text = re.sub(r"\s+", " ", str(value).replace("\u200b", " ")).strip()
    match = re.search(r"([\d,]+)\s*$", text)
    return match.group(1).replace(",", "") if match else text


def _excerpt(text: str, limit: int = 500) -> str:
    """Normalize scraped text into Markdown paragraphs and keep only its prefix."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    truncated = normalized[:limit]
    paragraphs = []
    for part in re.split(r"\n\s*\n+", truncated):
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in part.splitlines()]
        lines = [line for line in lines if line]
        if lines:
            # Two newlines make paragraph breaks render consistently in
            # Obsidian regardless of the viewer's soft-break setting.
            paragraphs.append("\n\n".join(lines))
    excerpt = "\n\n".join(paragraphs).rstrip()
    return excerpt + ("…" if len(normalized) > limit else "")


def _card_matches(text: str) -> list[re.Match[str]]:
    """Find cards using their visible Markdown structure, without hidden IDs."""
    return list(re.finditer(
        r"(?ms)^# [^\n]+\n\nID: (\d+)\nURL: .+?"
        r"(?=^---\s*$\n\n^# [^\n]+\n\nID: \d+\nURL: |\Z)",
        text,
    ))


def append_pending(store: Store, path: str) -> None:
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    text = file.read_text(encoding="utf-8") if file.exists() else ""
    for row in store.pending_inbox():
        if not re.search(rf"(?m)^ID: {re.escape(str(row['id']))}$", text):
            patterns = json.loads(row["llm_pattern"] or "[]")
            surface = json.loads(row["surface_meta"] or "{}")
            excerpt = _excerpt(row["content"])
            surface_tags = " ".join(
                f"#{key} {_surface_value(value)}"
                for key, value in surface.items()
                if _surface_value(value)
            )
            separator = "\n---\n\n" if text.strip() else "\n"
            pattern_tags = " ".join(f"`{pattern}`" for pattern in patterns)
            metadata = f"#source {_source_name(row['url'])} #score {float(row['llm_score']):g}\n\n"
            if surface_tags:
                metadata += f"{surface_tags}\n\n"
            if pattern_tags:
                metadata += f"{pattern_tags}\n"
            block = separator + (
                f"# {row['title']}\n\n"
                f"ID: {row['id']}\n"
                f"URL: {row['url']}\n\n"
                f"{metadata}"
                "### Content\n"
                f"{excerpt}\n\n"
                "[原文 ↗]("
                f"{row['url']})\n\n"
                "### Human Review\n\n\n"
                "**human_score:**\n"
                "**human_description:**\n"
            )
            with file.open("a", encoding="utf-8") as output:
                output.write(block)
            text += block
        store.mark_inbox_appended(row["id"], now())

    matches = _card_matches(text)
    if len(matches) < 2:
        return
    scores = {
        int(row["id"]): float(row["llm_score"])
        for row in store.all_articles()
    }
    blocks = {int(match.group(1)): match.group(0).rstrip() for match in matches}
    ordered = sorted(blocks, key=lambda article_id: (-scores.get(article_id, 0), article_id))
    sorted_blocks = "\n\n---\n\n".join(blocks[article_id] for article_id in ordered) + "\n"
    prefix = text[:matches[0].start()]
    suffix = text[matches[-1].end():]
    file.write_text(prefix + sorted_blocks + suffix, encoding="utf-8")


def organize(store: Store, inbox_path: str, reviewed_dir: str) -> int:
    file = Path(inbox_path)
    if not file.exists():
        return 0
    text = file.read_text(encoding="utf-8")
    matches = _card_matches(text)
    completed: list[tuple[str, str, int, str]] = []
    for match in matches:
        article_id = match.group(1)
        block = match.group(0)
        score_match = re.search(r"^\*\*human_score:\*\*\s*(\d+)\s*$", block, re.M)
        if not score_match:
            continue
        score = int(score_match.group(1))
        if not 0 <= score <= 10:
            raise ValueError(f"invalid human_score for article {article_id}")
        description_match = re.search(r"^\*\*human_description:\*\*\s*(.*)$", block, re.M)
        description = description_match.group(1).strip() if description_match else ""
        completed.append((block, article_id, score, description))
    if not completed:
        return 0
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    reviewed_file = Path(reviewed_dir) / f"{timestamp}.md"
    reviewed_file.parent.mkdir(parents=True, exist_ok=True)
    reviewed_file.write_text(
        "# Human Review\n\n" + "\n".join(item[0] for item in completed),
        encoding="utf-8",
    )
    for _, article_id, score, description in completed:
        store.save_human(int(article_id), score, description, now())
    remaining = text
    for block, _, _, _ in completed:
        remaining = remaining.replace(block, "", 1)
    remaining = re.sub(r"(?:^|\n)---\s*(?=\n|$)", "\n", remaining)
    temporary = file.with_suffix(file.suffix + ".tmp")
    temporary.write_text(remaining.lstrip(), encoding="utf-8")
    temporary.replace(file)
    return len(completed)
