from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from signal_prospector.browser import _cdp_websocket_url


def test_cdp_websocket_url_is_fetched_without_proxy() -> None:
    opener = MagicMock()
    response = opener.open.return_value.__enter__.return_value
    response.read.return_value = json.dumps(
        {"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/test"}
    ).encode()

    with patch("signal_prospector.browser.build_opener", return_value=opener) as build_opener:
        assert _cdp_websocket_url("http://127.0.0.1:9222") == (
            "ws://127.0.0.1:9222/devtools/browser/test"
        )

    assert build_opener.call_args.args[0].proxies == {}
    opener.open.assert_called_once_with(
        "http://127.0.0.1:9222/json/version", timeout=2
    )
