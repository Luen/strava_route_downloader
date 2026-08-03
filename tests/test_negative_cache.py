"""Unit tests for negative caching of HTTP 200 parse failures."""

from __future__ import annotations

import pytest

import strava


ROUTE_URL = "https://www.strava.com/routes/3511072076873105326"


def test_http_200_parse_failure_is_negative_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[str, object] = {}

    monkeypatch.setattr(strava.cache, "get", lambda key: store.get(key))
    monkeypatch.setattr(
        strava.cache,
        "set",
        lambda key, value, ttl_seconds=None: store.__setitem__(key, value),
    )
    monkeypatch.setattr(strava, "load_strava_cookies", lambda: None)
    monkeypatch.setattr(
        strava,
        "safe_get",
        lambda url, cookies=None: (url, "<html>no next data</html>", 200),
    )

    with pytest.raises(strava.ParseError, match="Route data not found"):
        strava.fetch_route_data(ROUTE_URL)

    cached = store[strava._route_cache_key("3511072076873105326")]
    assert strava._is_negative_cache(cached)
    assert cached["error_type"] == "ParseError"

    # Second call should raise from cache and not call Strava again.
    def boom(*_args, **_kwargs):
        raise AssertionError("safe_get should not be called for negative cache hits")

    monkeypatch.setattr(strava, "safe_get", boom)
    with pytest.raises(strava.ParseError, match="Route data not found"):
        strava.fetch_route_data(ROUTE_URL)


def test_auth_failure_without_cookies_can_retry_after_cookies_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store: dict[str, object] = {}
    calls = {"n": 0}

    monkeypatch.setattr(strava.cache, "get", lambda key: store.get(key))
    monkeypatch.setattr(
        strava.cache,
        "set",
        lambda key, value, ttl_seconds=None: store.__setitem__(key, value),
    )
    monkeypatch.setattr(strava, "load_strava_cookies", lambda: None)

    def fake_get(url, cookies=None):
        calls["n"] += 1
        return url, "<html><script id=\"__NEXT_DATA__\">{\"props\":{\"pageProps\":{}}}</script></html>", 200

    monkeypatch.setattr(strava, "safe_get", fake_get)

    with pytest.raises(strava.AuthRequiredError):
        strava.fetch_route_data(ROUTE_URL)
    assert calls["n"] == 1

    # Cached auth miss should not refetch while cookies are still absent.
    with pytest.raises(strava.AuthRequiredError):
        strava.fetch_route_data(ROUTE_URL)
    assert calls["n"] == 1

    route_payload = {
        "props": {
            "pageProps": {
                "route": {
                    "title": "Cached Retry Route",
                    "polyline": [[1.0, 2.0], [1.1, 2.1]],
                    "elevation": [],
                    "distanceStream": [],
                }
            }
        }
    }

    def fake_get_authed(url, cookies=None):
        calls["n"] += 1
        if cookies:
            import json

            html = (
                '<html><script id="__NEXT_DATA__">'
                + json.dumps(route_payload)
                + "</script></html>"
            )
            return url, html, 200
        return url, "<html><script id=\"__NEXT_DATA__\">{\"props\":{\"pageProps\":{}}}</script></html>", 200

    monkeypatch.setattr(strava, "load_strava_cookies", lambda: {"_strava4_session": "x"})
    monkeypatch.setattr(strava, "safe_get", fake_get_authed)

    route = strava.fetch_route_data(ROUTE_URL)
    assert route["title"] == "Cached Retry Route"
    assert calls["n"] == 3  # anonymous + authenticated after cookie bypass


def test_non_200_failures_are_not_negative_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[str, object] = {}

    monkeypatch.setattr(strava.cache, "get", lambda key: store.get(key))
    monkeypatch.setattr(
        strava.cache,
        "set",
        lambda key, value, ttl_seconds=None: store.__setitem__(key, value),
    )
    monkeypatch.setattr(strava, "load_strava_cookies", lambda: None)
    monkeypatch.setattr(
        strava,
        "safe_get",
        lambda url, cookies=None: (url, "<html>missing</html>", 404),
    )

    with pytest.raises(strava.ParseError):
        strava.fetch_route_data(ROUTE_URL)

    assert strava._route_cache_key("3511072076873105326") not in store
