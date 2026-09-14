from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import time
import tomllib
from urllib.request import ProxyHandler, build_opener

from .browser import collect_pages
from .inbox import append_pending, organize
from .scoring import score_many
from .storage import Store, url_hash


def load_config(path: str) -> tuple[dict, Path]:
    config_path = Path(path).resolve()
    with config_path.open("rb") as source:
        config = tomllib.load(source)
    root = config_path.parent
    load_env(root / ".env")
    paths = config.setdefault("paths", {})
    vault_configured = bool(paths.get("vault"))
    vault = Path(paths.get("vault", "")).expanduser()
    if not vault.is_absolute():
        vault = root / vault if vault_configured else root
    paths["vault"] = str(vault.resolve())
    for key in ("db", "inbox", "reviewed_dir", "prompt"):
        value = Path(paths[key]).expanduser()
        if not value.is_absolute():
            value = vault if vault_configured and key in ("inbox", "reviewed_dir") else root
            value = value / paths[key]
        paths[key] = str(value.resolve())
    browser = config.setdefault("browser", {})
    browser["profile"] = str((root / browser["profile"]).resolve())
    return config, root


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _cdp_available(endpoint: str) -> bool:
    if not endpoint.startswith(("http://", "https://")):
        return False
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(endpoint.rstrip("/") + "/json/version", timeout=2):
            return True
    except Exception:
        return False


def ensure_browser(config: dict) -> str:
    browser = config["browser"]
    endpoint = browser["cdp_endpoint"]
    if _cdp_available(endpoint):
        return endpoint

    log = Path(config["paths"]["db"]).parent / "chrome.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    port = int(browser["port"])
    with log.open("a", encoding="utf-8") as output:
        process = subprocess.Popen(
            [
                browser["executable"],
                f"--remote-debugging-port={port}",
                f"--user-data-dir={browser['profile']}",
                "--no-first-run",
                "--disable-default-apps",
                "--new-window",
                "--start-maximized",
                "about:blank",
            ],
            stdout=output,
            stderr=output,
            start_new_session=True,
        )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if _cdp_available(endpoint):
            return endpoint
        time.sleep(0.2)
    raise RuntimeError(
        f"Chrome started (pid={process.pid}) but CDP was not ready at {endpoint}"
    )


def command_browser(config: dict) -> int:
    print(f"Chrome CDP ready: {ensure_browser(config)}")
    return 0


def command_organize(config: dict) -> int:
    store = Store(config["paths"]["db"])
    try:
        count = organize(
            store,
            config["paths"]["inbox"],
            config["paths"]["reviewed_dir"],
        )
    finally:
        store.close()
    print(f"organized: {count}")
    return 0


def command_all(config: dict, media_name: str, number: int | None = None) -> int:
    result = command_organize(config)
    if result != 0:
        return result
    return command_wash(config, media_name, 100 if number is None else number)


def process_candidates(store: Store, candidates: list[dict], config: dict) -> tuple[int, int, int, int]:
    local_seen: set[str] = set()
    processed_count = 0
    scored_count = 0
    saved_count = 0
    failed_count = 0
    pending: list[dict] = []
    for candidate in candidates:
        value = url_hash(candidate["url"])
        if value in local_seen:
            continue
        local_seen.add(value)
        if store.processed(value):
            store.touch_processed(value, candidate["url"], now())
            processed_count += 1
            continue
        pending.append(candidate)

    if not pending:
        return processed_count, 0, 0, 0

    try:
        results = score_many(
            pending, {**config["scoring"], "prompt": config["paths"]["prompt"]}
        )
    except Exception as exc:
        print(f"[batch-skip] {type(exc).__name__}: {exc}")
        return processed_count, 0, 0, len(pending)

    for candidate, result in zip(pending, results):
        try:
            article = {**candidate, **result}
            article_id = store.save_result(
                article, now(), float(config["scoring"]["threshold"])
            )
            scored_count += 1
            if article_id is not None:
                saved_count += 1
            print(
                f"[score] {candidate['title'][:80]} -> {result['score']}",
                flush=True,
            )
        except Exception as exc:
            failed_count += 1
            print(f"[skip] {candidate['url']}: {type(exc).__name__}: {exc}")
    return processed_count, scored_count, saved_count, failed_count


def command_wash(config: dict, media_name: str, number: int | None = None) -> int:
    if number is not None and number <= 0:
        raise SystemExit("--number must be a positive integer")
    pages = [page for page in config.get("pages", []) if page.get("name") == media_name]
    if not pages:
        raise SystemExit(f"unknown media: {media_name}")
    paths = config["paths"]
    store = Store(paths["db"])
    try:
        append_pending(store, paths["inbox"])
        browser = config["browser"]
        try:
            endpoint = ensure_browser(config)
            print(f"Chrome CDP ready: {endpoint}", flush=True)
        except Exception as exc:
            print(
                f"[wash-error] {type(exc).__name__}: {_short_error(exc)}",
                flush=True,
            )
            return 1
        rounds = max(1, int(pages[0].get("rounds", 1)))
        remaining = number
        totals = [0, 0, 0, 0]
        for round_number in range(rounds):
            try:
                candidates = collect_pages(browser["cdp_endpoint"], pages)
            except Exception as exc:
                # Keep transient browser/network failures from exposing a
                # Playwright traceback to users running the CLI on a desktop.
                print(
                    f"[wash-error] {type(exc).__name__}: {_short_error(exc)}",
                    flush=True,
                )
                return 1
            if remaining is not None:
                # `process_candidates` also filters processed URLs, but doing
                # it here lets --number mean exactly N new answers overall,
                # rather than N items including duplicates from refreshes.
                candidates = [
                    candidate for candidate in candidates
                    if not store.processed(url_hash(candidate["url"]))
                ][:remaining]
            print(
                f"wash {media_name}: round={round_number + 1}/{rounds} "
                f"candidates={len(candidates)}",
                flush=True,
            )
            counts = process_candidates(store, candidates, config)
            for index, count in enumerate(counts):
                totals[index] += count
            if remaining is not None:
                remaining -= len(candidates)
            append_pending(store, paths["inbox"])
            if remaining == 0:
                break
            if round_number + 1 < rounds:
                print("[round] inbox written; next round will refresh the page", flush=True)
        print(
            f"summary: processed={totals[0]} scored={totals[1]} "
            f"saved_high_score={totals[2]} failed={totals[3]}",
            flush=True,
        )
        if number is not None and remaining > 0:
            print(
                f"[number] requested={number} available_processed={number - remaining}",
                flush=True,
            )
    finally:
        store.close()
    return 0


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_error(exc: Exception) -> str:
    return " ".join(str(exc).split())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prospect")
    parser.add_argument("command", choices=("browser", "wash", "organize", "all"))
    parser.add_argument("media", nargs="?")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument(
        "--number", type=int,
        help="本次 wash 总共处理多少条新的回答（跨 rounds 累计）",
    )
    args = parser.parse_args(argv)
    config, _ = load_config(args.config)
    if args.command == "browser":
        return command_browser(config)
    if args.command == "wash":
        if not args.media:
            parser.error("wash requires <mediaName>")
        return command_wash(config, args.media, args.number)
    if args.command == "organize":
        return command_organize(config)
    if not args.media:
        parser.error("all requires <mediaName>")
    return command_all(config, args.media, args.number)


if __name__ == "__main__":
    raise SystemExit(main())
