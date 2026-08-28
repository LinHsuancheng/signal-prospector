from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any


def _sample(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    return text[:head] + "\n\n[正文已截断]\n\n" + text[-(limit - head):]


def score_many(articles: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    import httpx

    prompt = Path(config["prompt"]).read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    limit = int(config.get("max_chars", 4000))
    items = [
        {
            "id": index,
            "source": "browser-social",
            "title": article["title"],
            "sample": _sample(article["content"], limit),
        }
        for index, article in enumerate(articles, start=1)
    ]
    articles_json = json.dumps(items, ensure_ascii=False)
    # Replace only the article placeholder. JSON examples in the prompt may
    # legitimately contain doubled braces and must remain untouched.
    prompt = prompt.replace("{{articles}}", articles_json)
    prompt = prompt.replace("{articles}", articles_json)
    prompt += "\n\n对每个 id 返回 pattern、score 和 reason。"
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": "你为单个用户批量评分文章。只返回 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    if config.get("nonthink"):
        payload["enable_thinking"] = False
        payload["thinking"] = {"type": "disabled"}
    key = os.environ.get(config.get("api_key_env", "OPENAI_API_KEY"), "")
    if not key:
        raise RuntimeError("missing scoring API key")
    for attempt in range(int(config.get("retries", 2)) + 1):
        try:
            response = httpx.post(
                config["base_url"],
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
                timeout=float(config.get("timeout", 180)),
            )
            break
        except httpx.TimeoutException:
            if attempt >= int(config.get("retries", 2)):
                raise
    response.raise_for_status()
    data = json.loads(response.json()["choices"][0]["message"]["content"])
    returned = data.get("items", [data])
    by_id = {int(item["id"]): item for item in returned}
    if set(by_id) != set(range(1, len(articles) + 1)):
        raise ValueError("LLM returned an incomplete batch")
    results = []
    for index in range(1, len(articles) + 1):
        item = by_id[index]
        patterns = item.get("pattern")
        if not isinstance(patterns, list) or not all(isinstance(value, str) for value in patterns):
            raise ValueError(f"LLM returned invalid pattern for id {index}")
        patterns = [value.strip() for value in patterns if value.strip()]
        score = float(item["score"])
        if not math.isfinite(score):
            raise ValueError(f"LLM returned non-finite score for id {index}")
        results.append(
            {
                "pattern": patterns,
                "score": max(0.0, min(10.0, score)),
                "reason": str(item["reason"]).strip(),
                "prompt_version": config["prompt_version"],
                "prompt_hash": prompt_hash,
            }
        )
    return results


def score_one(article: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return score_many([article], config)[0]
