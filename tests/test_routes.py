"""Live Strava route conversion checks (public + private)."""

from __future__ import annotations

import pytest

import strava

PUBLIC_ROUTES = [
    "https://strava.app.link/M0wOQGVRw4b",
    "https://strava.app.link/Cq6hSFbmx4b",
]

PRIVATE_ROUTES = [
    "https://www.strava.com/routes/3511072076873105326",
]


def _assert_gpx(content: str, filename: str, mime: str) -> None:
    assert mime == "application/gpx+xml"
    assert filename.endswith(".gpx")
    assert content.lstrip().startswith("<?xml")
    assert "<gpx" in content
    assert "<trkpt" in content
    assert content.count("<trkpt") >= 2


@pytest.mark.parametrize("url", PUBLIC_ROUTES)
def test_public_route_converts_without_cookies(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRAVA_COOKIES_FILE", raising=False)
    content, filename, mime = strava.convert_route(url, "gpx")
    _assert_gpx(content, filename, mime)


@pytest.mark.parametrize("url", PRIVATE_ROUTES)
def test_private_route_converts_with_cookies(url: str) -> None:
    cookies = strava.load_strava_cookies()
    if not cookies:
        pytest.skip("STRAVA_COOKIES_FILE not configured or unreadable")

    content, filename, mime = strava.convert_route(url, "gpx")
    _assert_gpx(content, filename, mime)


@pytest.mark.parametrize("url", PRIVATE_ROUTES)
def test_private_route_requires_cookies(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRAVA_COOKIES_FILE", raising=False)
    # Bypass disk cache so we exercise the anonymous fetch path.
    monkeypatch.setattr(strava.cache, "get", lambda _key: None)
    monkeypatch.setattr(
        strava.cache, "set", lambda _key, _value, ttl_seconds=None: None
    )

    with pytest.raises(strava.AuthRequiredError):
        strava.convert_route(url, "gpx")
