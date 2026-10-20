"""Pull submissions from the KoboToolbox API (v2) with pagination, retries and an offline cache."""
import json
import time
from pathlib import Path

import requests


class KoboError(RuntimeError):
    pass


def fetch_submissions(server, token, asset_uid, page_size=1000, timeout=60, retries=3):
    """Return every submission of one project as a list of dicts (raw Kobo JSON)."""
    if not token:
        raise KoboError("KOBO_TOKEN is not set. Create an API token in KoboToolbox (Account Settings > Security).")
    if not asset_uid:
        raise KoboError("Asset UID is empty. Put the project's UID in config.yaml or as an environment variable.")
    url = f"{server.rstrip('/')}/api/v2/assets/{asset_uid}/data/"
    params = {"format": "json", "limit": page_size}
    headers = {"Authorization": f"Token {token}"}
    results = []
    while url:
        for attempt in range(1, retries + 1):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=timeout)
                if resp.status_code == 401:
                    raise KoboError("Kobo rejected the token (401). Check KOBO_TOKEN and the server address.")
                if resp.status_code == 404:
                    raise KoboError("Project not found (404). Check the asset UID and the server address.")
                resp.raise_for_status()
                break
            except KoboError:
                raise
            except requests.RequestException as exc:
                if attempt == retries:
                    raise KoboError(f"Could not reach Kobo after {retries} tries: {exc}") from exc
                time.sleep(2 * attempt)
        payload = resp.json()
        results.extend(payload.get("results", []))
        url = payload.get("next")
        params = None  # 'next' already carries the query string
    return results


def fetch_with_cache(server, token, asset_uid, cache_path, **kw):
    """Fetch from Kobo and save a local copy; if Kobo is unreachable, fall back to the last saved copy."""
    cache_path = Path(cache_path)
    try:
        data = fetch_submissions(server, token, asset_uid, **kw)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        return data, "live"
    except KoboError:
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8")), "cached"
        raise


# ---------------------------------------------------------------------------------------------
# Project discovery: you only list project UIDs; the dashboard works out which is which.
# ---------------------------------------------------------------------------------------------
def _get_json(url, token, params=None, timeout=60):
    resp = requests.get(url, headers={"Authorization": f"Token {token}"}, params=params, timeout=timeout)
    if resp.status_code == 401:
        raise KoboError("Kobo rejected the token (401). Check KOBO_TOKEN - and that it was created on the same server "
                        "as the 'server' in config.yaml (kf.kobotoolbox.org vs eu.kobotoolbox.org).")
    if resp.status_code in (403, 404):
        raise KoboError(f"Kobo says {resp.status_code} for this project. Either the UID is wrong, the project is on a different "
                        f"server, or the account that owns this token has no 'View submissions' permission on it.")
    resp.raise_for_status()
    return resp.json()


def classify_project(server, token, uid, timeout=60):
    """Return (name, role) where role is 'fdaf' or 'monitoring' (or 'unknown'), decided from the form's own field names."""
    base = f"{server.rstrip('/')}/api/v2/assets/{uid}/"
    try:
        info = _get_json(base, token, {"format": "json"}, timeout)
    except requests.RequestException as exc:
        raise KoboError(f"Could not reach Kobo for project {uid}: {exc}") from exc
    name = info.get("name") or uid
    fields = set()
    for row in (info.get("content") or {}).get("survey", []) or []:
        for key in ("name", "$autoname"):
            if row.get(key):
                fields.add(row[key])
    low = name.lower()
    is_monitor_name = any(w in low for w in ("monitor", "quality", "compliance"))
    if "hh_members" in fields or "hh_head_name" in fields or (("family development" in low or "fdaf" in low) and not is_monitor_name):
        return name, "fdaf"
    if "enumerator_monitored" in fields or "monitor_code" in fields or is_monitor_name:
        return name, "monitoring"
    # last resort: look at one submission
    try:
        sample = _get_json(base + "data/", token, {"format": "json", "limit": 1}, timeout).get("results", [])
    except requests.RequestException:
        sample = []
    keys = " ".join(sample[0].keys()) if sample else ""
    if "hh_members" in keys or "hh_head_name" in keys:
        return name, "fdaf"
    if "enumerator_monitored" in keys:
        return name, "monitoring"
    return name, "unknown"
