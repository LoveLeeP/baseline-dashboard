"""One function that runs everything: extract -> clean -> check -> score. Used by the dashboard and the daily job."""
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from . import demo_data
from .audit import audit_tables
from .integrity import run_checks
from .kobo_client import KoboError, classify_project, fetch_with_cache
from .loader import build_fdaf_tables, load_choice_labels, load_directory, load_item_labels
from .monitoring import build_monitoring, enumerator_scores

BASE = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    """Tiny .env reader (so you don't have to set the token in every terminal)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:      # a real environment variable wins over .env
            os.environ[k] = v


def load_config(path=None):
    _load_dotenv(BASE / ".env")
    cfg = yaml.safe_load(open(path or BASE / "config.yaml", encoding="utf-8"))
    k = cfg.setdefault("kobo", {})
    k["server"] = os.getenv("KOBO_SERVER", k.get("server") or "https://kf.kobotoolbox.org").strip()
    if not k["server"].startswith("http"):
        k["server"] = "https://" + k["server"]
    k["fdaf_asset_uid"] = os.getenv("FDAF_ASSET_UID", k.get("fdaf_asset_uid"))
    k["monitoring_asset_uid"] = os.getenv("MONITORING_ASSET_UID", k.get("monitoring_asset_uid"))
    env_projects = os.getenv("KOBO_PROJECTS")
    if env_projects:
        k["projects"] = [u.strip() for u in env_projects.split(",") if u.strip()]
    k["projects"] = [str(u).strip() for u in (k.get("projects") or []) if u and str(u).strip()]
    cfg["token"] = os.getenv("KOBO_TOKEN", "").strip()
    return cfg


def configured_projects(cfg):
    """[(uid, role-or-None)] - role is None when it must be auto-detected."""
    k, out, seen = cfg["kobo"], [], set()
    for uid in k.get("projects", []):
        if uid not in seen:
            out.append((uid, None)); seen.add(uid)
    for uid, role in ((k.get("fdaf_asset_uid"), "fdaf"), (k.get("monitoring_asset_uid"), "monitoring")):
        if uid and uid not in seen:
            out.append((uid, role)); seen.add(uid)
    return out


def live_ready(cfg):
    return bool(cfg.get("token") and configured_projects(cfg))


def _load_live(cfg):
    """Fetch every configured Kobo project. Returns (fdaf_records, monitoring_records, project_status_rows)."""
    k = cfg["kobo"]
    kw = dict(page_size=k.get("page_size", 1000), timeout=k.get("timeout_seconds", 60))
    roles_file = BASE / "data" / "project_roles.json"
    try:
        known = json.loads(roles_file.read_text(encoding="utf-8"))
    except Exception:
        known = {}
    fdaf, mon, rows, seen_uuid = [], [], [], set()
    for uid, role in configured_projects(cfg):
        row = {"project_uid": uid, "project_name": known.get(uid, {}).get("name", ""), "role": role or known.get(uid, {}).get("role", ""),
               "submissions": 0, "status": ""}
        try:
            if not row["role"] or not row["project_name"]:
                name, detected = classify_project(k["server"], cfg["token"], uid, k.get("timeout_seconds", 60))
                row["project_name"], row["role"] = name, role or detected
                known[uid] = {"name": name, "role": row["role"]}
                roles_file.parent.mkdir(parents=True, exist_ok=True)
                roles_file.write_text(json.dumps(known), encoding="utf-8")
            if row["role"] == "unknown":
                raise KoboError("Could not tell whether this is an FDAF or a Monitoring project. Put its UID under "
                                "fdaf_asset_uid or monitoring_asset_uid in config.yaml.")
            data, src = fetch_with_cache(k["server"], cfg["token"], uid, BASE / "data" / f"raw_{uid}.json", **kw)
            row["submissions"], row["status"] = len(data), src
            if row["role"] == "fdaf":
                for rec in data:
                    u = rec.get("_uuid")
                    if u in seen_uuid:           # same submission present in two projects
                        continue
                    seen_uuid.add(u)
                    rec["_source_form"] = row["project_name"] or uid
                    fdaf.append(rec)
            else:
                mon.extend(data)
        except Exception as exc:                 # one bad project must not take the whole dashboard down
            row["status"] = f"ERROR: {exc}"
        rows.append(row)
    if not fdaf and not any(r["role"] == "fdaf" and not r["status"].startswith("ERROR") for r in rows):
        problems = "; ".join(f"{r['project_uid']}: {r['status']}" for r in rows if r["status"].startswith("ERROR"))
        raise KoboError("No FDAF project could be loaded. " + (problems or "No FDAF project found among the configured UIDs."))
    return fdaf, mon, rows


def run_pipeline(cfg, demo=False):
    ref = cfg["reference"]
    labels = load_choice_labels(BASE / ref["fdaf_xlsform"])
    directory = load_directory(BASE / ref["directory"])
    item_labels = load_item_labels(BASE / ref["monitoring_xlsform"])

    proj_rows = []
    if demo:
        fdaf_raw, mon_raw, truth = demo_data.generate(labels, directory, BASE / ref["monitoring_xlsform"])
        source = "demo (synthetic data)"
    else:
        fdaf_raw, mon_raw, proj_rows = _load_live(cfg)
        source = "live (KoboToolbox): " + "; ".join(
            f"{r['project_name'] or r['project_uid']} [{r['role']}] {r['submissions']} ({r['status']})" for r in proj_rows)
        truth = None

    hh, mem = build_fdaf_tables(fdaf_raw, cfg, labels, directory)
    fdaf_labels = load_item_labels(BASE / ref["fdaf_xlsform"])
    flags, integ, catalogue = run_checks(hh, mem, cfg, labels=fdaf_labels, xlsx_path=BASE / ref["fdaf_xlsform"])
    audit = audit_tables(flags, hh)
    mon, items = build_monitoring(mon_raw, cfg, directory, item_labels)
    enum = enumerator_scores(hh, integ, mon, directory, cfg)

    daily = (hh.groupby(["interview_date", "enumerator_code", "enumerator_label", "title", "region_label",
                         "province_label", "municipality_label", "barangay_label"])
               .agg(surveys=("uuid", "count"), consented=("consented", "sum")).reset_index())
    return {"hh": hh, "mem": mem, "flags": flags, "integrity": integ, "catalogue": catalogue, "monitoring": mon,
            "items": items, "enumerators": enum, "daily": daily, "audit": audit, "directory": directory, "truth": truth,
            "status": {"source": source, "refreshed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "fdaf_records": len(fdaf_raw), "monitoring_records": len(mon_raw),
                       "projects": pd.DataFrame(proj_rows)}}
