from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from signal_prospector.cli import _cdp_available, command_all, ensure_browser


def _config(tmp_path: Path) -> dict:
    return {
        "browser": {
            "cdp_endpoint": "http://127.0.0.1:9222",
            "executable": "/usr/bin/google-chrome",
            "profile": str(tmp_path / "profile"),
            "port": 9222,
        },
        "paths": {"db": str(tmp_path / "data" / "store.sqlite")},
    }


def test_ensure_browser_starts_chrome_when_cdp_is_unavailable(tmp_path: Path) -> None:
    config = _config(tmp_path)
    process = Mock(pid=1234)

    with patch("signal_prospector.cli._cdp_available", side_effect=[False, True]), \
         patch("signal_prospector.cli.subprocess.Popen", return_value=process) as popen:
        assert ensure_browser(config) == "http://127.0.0.1:9222"

    popen.assert_called_once()


def test_ensure_browser_reuses_existing_cdp_browser(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with patch("signal_prospector.cli._cdp_available", return_value=True), \
         patch("signal_prospector.cli.subprocess.Popen") as popen:
        assert ensure_browser(config) == "http://127.0.0.1:9222"

    popen.assert_not_called()


def test_cdp_probe_bypasses_environment_proxy() -> None:
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value = object()

    with patch("signal_prospector.cli.build_opener", return_value=opener) as build_opener:
        assert _cdp_available("http://127.0.0.1:9222") is True

    build_opener.assert_called_once()
    proxy_handler = build_opener.call_args.args[0]
    assert proxy_handler.proxies == {}
    opener.open.assert_called_once_with(
        "http://127.0.0.1:9222/json/version", timeout=2
    )


def test_command_all_organizes_before_washing_100_items(tmp_path: Path) -> None:
    config = _config(tmp_path)
    calls: list[tuple[str, object]] = []

    with patch("signal_prospector.cli.command_organize", side_effect=lambda _: calls.append(("organize", None)) or 0), \
         patch("signal_prospector.cli.command_wash", side_effect=lambda _, media, number: calls.append(("wash", (media, number))) or 0):
        assert command_all(config, "zhihu") == 0

    assert calls == [("organize", None), ("wash", ("zhihu", 100))]


def test_command_all_allows_overriding_number(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with patch("signal_prospector.cli.command_organize", return_value=0), \
         patch("signal_prospector.cli.command_wash", return_value=0) as wash:
        assert command_all(config, "zhihu", 25) == 0

    wash.assert_called_once_with(config, "zhihu", 25)
