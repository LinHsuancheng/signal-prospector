from __future__ import annotations

import re
import json
import time
from urllib.request import ProxyHandler, build_opener
from urllib.parse import urldefrag, urlsplit, urlunsplit
from typing import Any


def _short_error(exc: Exception) -> str:
    return " ".join(str(exc).split())


def canonical_url(value: str) -> str:
    value, _ = urldefrag(value.strip())
    parts = urlsplit(value)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def _cdp_websocket_url(endpoint: str) -> str:
    opener = build_opener(ProxyHandler({}))
    with opener.open(endpoint.rstrip("/") + "/json/version", timeout=2) as response:
        info = json.load(response)
    return str(info["webSocketDebuggerUrl"])


def collect_pages(endpoint: str, pages: list[dict[str, Any]]) -> list[dict[str, str]]:
    from playwright.sync_api import sync_playwright

    found: list[dict[str, str]] = []
    seen: set[str] = set()
    seen_groups: set[str] = set()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(_cdp_websocket_url(endpoint))
        context = browser.contexts[0]
        page = next((p for p in context.pages if p.url != "about:blank"), context.pages[0])
        for spec in pages:
            try:
                page.goto(spec["url"], wait_until="commit", timeout=30000)
            except Exception as exc:
                # A flaky network should only cost us this source page, not the
                # whole wash run (and, importantly, not a Playwright traceback).
                print(
                    f"[page-skip] {spec['url']}: {type(exc).__name__}: {_short_error(exc)}",
                    flush=True,
                )
                continue
            time.sleep(float(spec.get("scroll_wait_seconds", 1)))
            pattern = re.compile(spec["link_pattern"])
            group_pattern = (
                re.compile(spec["group_pattern"]) if spec.get("group_pattern") else None
            )

            def scan() -> None:
                for link in page.locator("a").evaluate_all(
                    """
                    (els, options) => els.map(a => {
                        const title = (a.innerText || a.getAttribute('aria-label') || '').trim();
                        const container = options.container_selector
                            ? a.closest(options.container_selector) : null;
                        const surface = {};
                        for (const [name, selectors] of Object.entries(options.fields || {})) {
                            for (const selector of selectors) {
                                const node = container?.querySelector(selector);
                                const value = (node?.innerText || node?.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim();
                                if (value) { surface[name] = value; break; }
                            }
                        }
                        return {title, url: a.href, surface_meta: surface};
                    })
                    """,
                    spec.get("surface") or {},
                ):
                    url = canonical_url(str(link.get("url") or ""))
                    title = str(link.get("title") or "").replace("\n", " ").strip()
                    if not title or not pattern.search(url) or url in seen:
                        continue
                    group_match = group_pattern.search(url) if group_pattern else None
                    group = group_match.group(0) if group_match else url
                    if group in seen_groups:
                        continue
                    seen.add(url)
                    seen_groups.add(group)
                    found.append({
                        "url": url,
                        "title": title,
                        "source_page": spec["url"],
                        "surface_meta": link.get("surface_meta") or {},
                        "content_stop_markers": spec.get("content_stop_markers", []),
                    })
            scrolls = max(0, int(spec.get("scrolls", 0)))
            wait_seconds = float(spec.get("scroll_wait_seconds", 1))
            for _ in range(scrolls):
                scan()
                page.evaluate(
                    "delta => window.scrollBy(0, delta)",
                    int(spec.get("scroll_delta", 1400)),
                )
                time.sleep(wait_seconds)
            scan()
        for item in found:
            try:
                page.goto(item["url"], wait_until="commit", timeout=30000)
                time.sleep(1)
                item["title"] = page.title() or item["title"]
                import trafilatura
                html = page.content()
                item["content"] = trafilatura.extract(
                    html,
                    url=item["url"],
                    include_comments=False,
                    include_tables=False,
                ) or ""
            except Exception as exc:
                print(
                    f"[article-skip] {item['url']}: {type(exc).__name__}: {_short_error(exc)}",
                    flush=True,
                )
                item["content"] = ""
                continue
            for marker in item.get("content_stop_markers", []):
                item["content"] = re.split(
                    rf"(?m)^[ \t]*{re.escape(str(marker))}[ \t]*$",
                    item["content"],
                    maxsplit=1,
                )[0].rstrip()
        found = [item for item in found if item["content"].strip()]
        # ponytail: the process owns the CDP connection, not the user's browser.
    return found
