import os

from flask import Flask, jsonify, make_response, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import strava
from strava import AuthRequiredError, FetchError, ParseError, ValidationError

app = Flask(__name__)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)


@app.after_request
def set_security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.post("/api/convert")
@limiter.limit("20 per minute")
def convert():
    payload = request.get_json(silent=True) or {}
    url = payload.get("url", "")
    output_format = (payload.get("format") or "gpx").lower()

    try:
        content, filename, mime_type = strava.convert_route(url, output_format)
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except AuthRequiredError as exc:
        return jsonify({"error": str(exc)}), 422
    except ParseError as exc:
        return jsonify({"error": str(exc)}), 422
    except FetchError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception:
        return jsonify({"error": "Unexpected server error."}), 500

    response = make_response(content)
    response.headers["Content-Type"] = mime_type
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
