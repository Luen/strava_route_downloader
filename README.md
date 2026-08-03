# Strava Route Downloader

Paste a Strava route link and download it as GPX, KML, or GeoJSON.

## Quick start

```bash
docker compose up --build
```

Open http://localhost:7650

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export CACHE_DIR=./cache
flask --app app run --debug
```

## Public vs private routes

Strava treats routes differently depending on how they were created or edited:

| Kind | Visibility | Cookies needed? |
|------|------------|-----------------|
| AI-generated routes (unedited) | Public | No — fetched anonymously |
| AI-generated routes after the owner edits them | Private | Yes — logged-in session |
| Routes created by hand in Strava Route Builder | Private | Yes — logged-in session |

The downloader always tries an anonymous fetch first. If the page has no usable route/polyline data, it retries once with session cookies from `STRAVA_COOKIES_FILE` (when configured).

## Private routes (session cookies)

Use the same cookie-export approach as [strava-heatmap-proxy](https://github.com/patrickziegler/strava-heatmap-proxy):

1. Log in to Strava in your browser and export cookies with [strava-cookie-exporter](https://github.com/patrickziegler/strava-heatmap-proxy#export-cookies) (Firefox / Chrome).
2. Point `STRAVA_COOKIES_FILE` at that JSON file.

```bash
export STRAVA_COOKIES_FILE=$HOME/.config/strava-heatmap-proxy/strava-cookies.json
flask --app app run --debug
```

With Docker Compose, place the exported file at `./strava-cookies/strava-cookies.json` (or set `STRAVA_COOKIES_DIR` to another host directory containing `strava-cookies.json`). The directory is mounted read-only.

Re-export cookies when the session expires. Any convert request can use the configured session, so prefer this on a personal/self-hosted deploy.

## API

`POST /api/convert`

```json
{
  "url": "https://strava.app.link/HawI14bwy4b",
  "format": "gpx"
}
```

Supported formats: `gpx` (default), `kml`, `geojson`.

## Tests

Integration tests hit live Strava URLs (public short links plus a private route). Private-route cases need cookies.

```bash
pip install -r requirements.txt -r requirements-dev.txt
export CACHE_DIR=./cache
export STRAVA_COOKIES_FILE=./strava-cookies/strava-cookies.json
pytest -q
```

Without `STRAVA_COOKIES_FILE`, public-route tests still run; private-route tests are skipped.

## Notes

- Strava **route** URLs are supported (`strava.app.link` short links and `strava.com/routes/...`).
- Public routes work without cookies; private routes need `STRAVA_COOKIES_FILE` and an account that can view them.
- Route data is cached on disk for 7 days to reduce repeat requests to Strava.
- HTTP 200 responses that still fail to parse (missing/invalid route HTML) are negative-cached for 24 hours so a broken page structure is not re-fetched on every request. Auth failures without cookies are also remembered for 24 hours, but will be retried if cookies are added later.
- Activity URLs are not supported.
