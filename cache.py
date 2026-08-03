import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
NEGATIVE_CACHE_TTL_SECONDS = 24 * 60 * 60

# Map allowed CACHE_DIR values to literal paths so env input never reaches Path().
_CACHE_DIR_BY_CONFIG = {
    "./cache": Path("./cache"),
    "cache": Path("./cache"),
    "/data/cache": Path("/data/cache"),
}


def _cache_dir() -> Path:
    raw = os.environ.get("CACHE_DIR", "./cache")
    path = _CACHE_DIR_BY_CONFIG.get(raw)
    if path is None:
        raise ValueError("Invalid CACHE_DIR")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _key_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return _cache_dir() / f"{digest}.json"


def get(key: str) -> Optional[Any]:
    path = _key_path(key)
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return None

    if payload.get("expires_at", 0) <= time.time():
        path.unlink(missing_ok=True)
        return None

    return payload.get("value")


def set(key: str, value: Any, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
    path = _key_path(key)
    payload = {
        "expires_at": time.time() + ttl_seconds,
        "value": value,
    }
    temp_path = path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    temp_path.replace(path)
