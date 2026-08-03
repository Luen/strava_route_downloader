from __future__ import annotations

import functools
import html
import ipaddress
import json
import os
import re
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests

import cache

ALLOWED_HOSTS = {"strava.app.link", "www.strava.com", "strava.com"}
SHORT_LINK_HOST = "strava.app.link"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 20
MAX_REDIRECTS = 5
PRIVATE_ROUTE_MESSAGE = (
    "This route could not be found. It may be private, deleted, or unsupported."
)
NO_POLYLINE_MESSAGE = "Route has no GPS data. It may be private or unsupported."
AUTH_FAILED_MESSAGE = (
    "This route appears private and could not be loaded with the configured "
    "session cookies. Export fresh cookies or check that your account can view it."
)

ROUTE_PATH_RE = re.compile(r"^/routes/[^/]+/?$")
ROUTE_ID_RE = re.compile(r"_(\d+)(?:/)?$")
ROUTE_URL_RE = re.compile(r"https://www\.strava\.com/routes/[^\s\"']+")
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)


class StravaError(Exception):
    pass


class ValidationError(StravaError):
    pass


class FetchError(StravaError):
    pass


class ParseError(StravaError):
    pass


class AuthRequiredError(ParseError):
    """Route page loaded but route/polyline is missing — may need a logged-in session."""


def _normalize_input_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise ValidationError("URL is required.")
    if len(cleaned) > 2048:
        raise ValidationError("URL is too long.")
    return cleaned


def _host_allowed(hostname: str) -> bool:
    return hostname.lower() in ALLOWED_HOSTS


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValidationError("Only HTTPS URLs are allowed.")
    if not parsed.hostname or not _host_allowed(parsed.hostname):
        raise ValidationError("Only Strava URLs are allowed.")


def _is_private_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


@functools.lru_cache(maxsize=64)
def _resolve_host_ips(hostname: str) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError("Could not resolve host.") from exc
    return tuple(info[4][0] for info in infos)


def _assert_safe_host(hostname: str) -> None:
    for address in _resolve_host_ips(hostname):
        if _is_private_ip(address):
            raise FetchError("Blocked unsafe host resolution.")


def _request_headers() -> dict[str, str]:
    return {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _add_cookie(cookies: dict[str, str], name: Any, value: Any) -> None:
    if isinstance(name, str) and isinstance(value, str) and name:
        cookies[name] = value


def load_strava_cookies() -> dict[str, str] | None:
    """Load session cookies from STRAVA_COOKIES_FILE (strava-cookie-exporter JSON)."""
    path = os.environ.get("STRAVA_COOKIES_FILE", "").strip()
    if not path:
        return None

    try:
        cookie_path = Path(path).expanduser().resolve(strict=True)
    except OSError:
        return None

    if not cookie_path.is_file():
        return None

    try:
        with cookie_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    cookies: dict[str, str] = {}
    if isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, dict):
                _add_cookie(cookies, entry.get("name"), entry.get("value"))
    elif isinstance(payload, dict):
        for name, value in payload.items():
            if isinstance(value, str):
                _add_cookie(cookies, name, value)
            elif isinstance(value, dict):
                _add_cookie(cookies, value.get("name", name), value.get("value"))

    return cookies or None


def _apply_cookies(session: requests.Session, cookies: dict[str, str]) -> None:
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".strava.com")


def safe_get(url: str, cookies: dict[str, str] | None = None) -> tuple[str, str, int]:
    current = url
    redirects = 0
    status_code = 0

    with requests.Session() as session:
        if cookies:
            _apply_cookies(session, cookies)

        while True:
            parsed = urlparse(current)
            if parsed.scheme != "https":
                raise FetchError("Only HTTPS URLs are allowed.")
            hostname = parsed.hostname
            if not hostname or not _host_allowed(hostname):
                raise FetchError("Redirect target is not allowed.")

            _assert_safe_host(hostname)

            try:
                response = session.get(
                    current,
                    headers=_request_headers(),
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                raise FetchError("Failed to fetch Strava page.") from exc

            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    raise FetchError("Redirect missing location header.")
                if redirects >= MAX_REDIRECTS:
                    raise FetchError("Too many redirects.")
                current = requests.compat.urljoin(current, location)
                redirects += 1
                continue

            if response.status_code not in {200, 404}:
                raise FetchError(f"Strava returned HTTP {response.status_code}.")

            content = response.content
            if len(content) > MAX_RESPONSE_BYTES:
                raise FetchError("Response too large.")
            status_code = response.status_code
            break

    return current, content.decode("utf-8", errors="replace"), status_code


def extract_route_id(slug: str) -> str:
    cleaned = slug.rstrip("/")
    match = ROUTE_ID_RE.search(cleaned)
    if match:
        return match.group(1)
    if cleaned.isdigit():
        return cleaned
    if re.fullmatch(r"\d+e", cleaned):
        return cleaned
    if cleaned:
        return cleaned
    raise ValidationError("Could not determine route ID from URL.")


def canonicalize_route_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if not _host_allowed(hostname):
        raise ValidationError("Only Strava URLs are allowed.")
    if not ROUTE_PATH_RE.match(parsed.path):
        raise ValidationError("URL must point to a Strava route.")

    slug = parsed.path.rstrip("/").split("/")[-1]
    canonical = urlunparse(
        (
            "https",
            "www.strava.com",
            f"/routes/{slug}",
            "",
            "",
            "",
        )
    )
    return canonical


def _short_link_cache_key(url: str) -> str:
    parsed = urlparse(url.lower().rstrip("/"))
    return f"shortlink:{parsed.netloc}{parsed.path}"


def _route_cache_key(route_id: str) -> str:
    return f"route:{route_id}"


CACHE_ERROR_KEY = "__cache_error__"


def _is_negative_cache(value: Any) -> bool:
    return isinstance(value, dict) and value.get(CACHE_ERROR_KEY) is True


def _negative_cache_entry(
    exc: ParseError,
    *,
    auth_attempted: bool,
) -> dict[str, Any]:
    error_type = "AuthRequiredError" if isinstance(exc, AuthRequiredError) else "ParseError"
    return {
        CACHE_ERROR_KEY: True,
        "error_type": error_type,
        "message": str(exc),
        "auth_attempted": auth_attempted,
    }


def _raise_from_negative_cache(entry: dict[str, Any]) -> None:
    message = entry.get("message") or PRIVATE_ROUTE_MESSAGE
    if entry.get("error_type") == "AuthRequiredError":
        raise AuthRequiredError(message)
    raise ParseError(message)


def _cache_http_200_failure(
    cache_key: str,
    status_code: int,
    exc: ParseError,
    *,
    auth_attempted: bool,
) -> None:
    if status_code != 200:
        return
    cache.set(
        cache_key,
        _negative_cache_entry(exc, auth_attempted=auth_attempted),
        ttl_seconds=cache.NEGATIVE_CACHE_TTL_SECONDS,
    )


def resolve_short_link(url: str) -> str:
    _validate_url(url)
    parsed = urlparse(url)
    if parsed.hostname != SHORT_LINK_HOST:
        raise ValidationError("Not a Strava short link.")

    cache_key = _short_link_cache_key(url)
    cached = cache.get(cache_key)
    if cached:
        return cached

    final_url, html_body, _status = safe_get(url)
    try:
        canonical = canonicalize_route_url(final_url)
    except ValidationError:
        canonical = canonicalize_route_url(_extract_route_url_from_branch_page(html_body))
    cache.set(cache_key, canonical)

    final_host = urlparse(final_url).hostname or ""
    if final_host in {"www.strava.com", "strava.com"}:
        _cache_route_html(canonical, html_body)

    return canonical


def _cache_route_html(canonical_url: str, html_body: str) -> None:
    try:
        route_data = extract_route(html_body)
    except ParseError:
        return

    slug = urlparse(canonical_url).path.rsplit("/", 1)[-1]
    cache.set(_route_cache_key(extract_route_id(slug)), route_data)


def _extract_route_url_from_branch_page(html_body: str) -> str:
    match = ROUTE_URL_RE.search(html_body)
    if match:
        return match.group(0)

    raise ParseError("Could not resolve short link to a Strava route.")


def resolve_route_url(url: str) -> str:
    cleaned = _normalize_input_url(url)
    _validate_url(cleaned)
    parsed = urlparse(cleaned)

    if parsed.hostname == SHORT_LINK_HOST:
        return resolve_short_link(cleaned)

    return canonicalize_route_url(cleaned)


def extract_route(html_body: str) -> dict[str, Any]:
    match = NEXT_DATA_RE.search(html_body)
    if not match:
        raise ParseError("Route data not found on page.")

    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ParseError("Route data is invalid.") from exc

    route = payload.get("props", {}).get("pageProps", {}).get("route")
    if not route:
        raise AuthRequiredError(PRIVATE_ROUTE_MESSAGE)

    polyline = route.get("polyline")
    if not polyline:
        raise AuthRequiredError(NO_POLYLINE_MESSAGE)

    return {
        "title": route.get("title") or "strava-route",
        "routeType": route.get("routeType"),
        "polyline": polyline,
        "elevation": route.get("elevation") or [],
        "distanceStream": route.get("distanceStream") or [],
    }


def fetch_route_data(canonical_url: str) -> dict[str, Any]:
    canonical = canonicalize_route_url(canonical_url)
    route_id = extract_route_id(urlparse(canonical).path.rsplit("/", 1)[-1])
    cache_key = _route_cache_key(route_id)

    cached = cache.get(cache_key)
    if cached is not None:
        if not _is_negative_cache(cached):
            return cached

        # Auth failures recorded before cookies existed can be retried once cookies appear.
        if (
            cached.get("error_type") == "AuthRequiredError"
            and not cached.get("auth_attempted")
            and load_strava_cookies()
        ):
            pass
        else:
            _raise_from_negative_cache(cached)

    _, html_body, status_code = safe_get(canonical)
    try:
        route_data = extract_route(html_body)
    except AuthRequiredError as auth_exc:
        cookies = load_strava_cookies()
        if not cookies:
            _cache_http_200_failure(
                cache_key, status_code, auth_exc, auth_attempted=False
            )
            raise
        _, html_body, status_code = safe_get(canonical, cookies=cookies)
        try:
            route_data = extract_route(html_body)
        except AuthRequiredError as retry_exc:
            failure = AuthRequiredError(AUTH_FAILED_MESSAGE)
            _cache_http_200_failure(
                cache_key, status_code, failure, auth_attempted=True
            )
            raise failure from retry_exc
        except ParseError as parse_exc:
            _cache_http_200_failure(
                cache_key, status_code, parse_exc, auth_attempted=True
            )
            raise
    except ParseError as parse_exc:
        _cache_http_200_failure(
            cache_key, status_code, parse_exc, auth_attempted=False
        )
        raise

    cache.set(cache_key, route_data)
    return route_data


def _interpolate_elevation(
    distance_stream: list[float],
    elevation_stream: list[list[float]],
) -> list[float | None]:
    if not distance_stream or not elevation_stream:
        return [None] * len(distance_stream)

    elevations: list[float | None] = []
    index = 0
    for distance in distance_stream:
        while index + 1 < len(elevation_stream) and elevation_stream[index + 1][0] <= distance:
            index += 1

        current = elevation_stream[index]
        if index + 1 < len(elevation_stream):
            nxt = elevation_stream[index + 1]
            span = nxt[0] - current[0]
            if span > 0:
                ratio = (distance - current[0]) / span
                elevations.append(current[1] + ratio * (nxt[1] - current[1]))
                continue

        elevations.append(current[1])

    return elevations


def sanitize_filename(title: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE).strip()
    cleaned = re.sub(r"[-\s]+", "-", cleaned)
    return cleaned[:80] or "strava-route"


def to_gpx(route_data: dict[str, Any]) -> str:
    title = html.escape(route_data["title"])
    polyline = route_data["polyline"]
    elevations = _interpolate_elevation(
        route_data.get("distanceStream") or [],
        route_data.get("elevation") or [],
    )

    points = []
    for index, (lat, lng) in enumerate(polyline):
        ele = elevations[index] if index < len(elevations) else None
        if ele is None:
            points.append(f'      <trkpt lat="{lat:.6f}" lon="{lng:.6f}"></trkpt>')
        else:
            points.append(
                f'      <trkpt lat="{lat:.6f}" lon="{lng:.6f}"><ele>{ele:.2f}</ele></trkpt>'
            )

    body = "\n".join(points)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="Strava Route Downloader" '
        'xmlns="http://www.topografix.com/GPX/1/1">\n'
        "  <trk>\n"
        f"    <name>{title}</name>\n"
        "    <trkseg>\n"
        f"{body}\n"
        "    </trkseg>\n"
        "  </trk>\n"
        "</gpx>\n"
    )


def to_kml(route_data: dict[str, Any]) -> str:
    title = html.escape(route_data["title"])
    polyline = route_data["polyline"]
    elevations = _interpolate_elevation(
        route_data.get("distanceStream") or [],
        route_data.get("elevation") or [],
    )

    coords = []
    for index, (lat, lng) in enumerate(polyline):
        ele = elevations[index] if index < len(elevations) else 0
        coords.append(f"{lng:.6f},{lat:.6f},{ele or 0:.2f}")

    coordinates = " ".join(coords)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "  <Document>\n"
        f"    <name>{title}</name>\n"
        "    <Placemark>\n"
        f"      <name>{title}</name>\n"
        "      <LineString>\n"
        "        <coordinates>\n"
        f"          {coordinates}\n"
        "        </coordinates>\n"
        "      </LineString>\n"
        "    </Placemark>\n"
        "  </Document>\n"
        "</kml>\n"
    )


def to_geojson(route_data: dict[str, Any]) -> str:
    polyline = route_data["polyline"]
    elevations = _interpolate_elevation(
        route_data.get("distanceStream") or [],
        route_data.get("elevation") or [],
    )

    coordinates = []
    for index, (lat, lng) in enumerate(polyline):
        ele = elevations[index] if index < len(elevations) else None
        if ele is None:
            coordinates.append([lng, lat])
        else:
            coordinates.append([lng, lat, ele])

    payload = {
        "type": "Feature",
        "properties": {
            "name": route_data["title"],
            "routeType": route_data.get("routeType"),
        },
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
    }
    return json.dumps(payload, indent=2)


CONVERTERS = {
    "gpx": (to_gpx, "application/gpx+xml", "gpx"),
    "kml": (to_kml, "application/vnd.google-earth.kml+xml", "kml"),
    "geojson": (to_geojson, "application/geo+json", "geojson"),
}


def convert_route(url: str, output_format: str) -> tuple[str, str, str]:
    if output_format not in CONVERTERS:
        raise ValidationError("Unsupported format.")

    canonical_url = resolve_route_url(url)
    route_data = fetch_route_data(canonical_url)
    converter, _, extension = CONVERTERS[output_format]
    content = converter(route_data)
    filename = f"{sanitize_filename(route_data['title'])}.{extension}"
    return content, filename, CONVERTERS[output_format][1]
