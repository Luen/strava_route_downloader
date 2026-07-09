# Strava Route Downloader

Paste a public Strava route link and download it as GPX, KML, or GeoJSON.

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

## API

`POST /api/convert`

```json
{
  "url": "https://strava.app.link/HawI14bwy4b",
  "format": "gpx"
}
```

Supported formats: `gpx` (default), `kml`, `geojson`.

## Notes

- Only public Strava **route** URLs are supported (`strava.app.link` short links and `strava.com/routes/...`).
- Route data is cached on disk for 7 days to reduce repeat requests to Strava.
- Activity URLs and private routes are not supported.
