"""Connection doctor.  Run:  python check_kobo.py
Tests the token, the server and every project in config.yaml one by one, and says what to fix."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import requests  # noqa: E402

from src.kobo_client import KoboError, classify_project, fetch_submissions  # noqa: E402
from src.pipeline import configured_projects, load_config  # noqa: E402


def main():
    cfg = load_config()
    k, token = cfg["kobo"], cfg["token"]
    print(f"Server : {k['server']}")
    if not token:
        print("\nPROBLEM: KOBO_TOKEN is not set.\n"
              "  Easiest fix: copy .env.example to .env, then paste your token after KOBO_TOKEN=\n"
              "  (Kobo > Account Settings > Security > API Token).")
        return 1
    print(f"Token  : {token[:4]}...{token[-3:]}  ({len(token)} characters)")
    projects = configured_projects(cfg)
    if not projects:
        print("\nPROBLEM: no projects listed in config.yaml under kobo > projects.")
        return 1
    try:  # token / server test on an endpoint that exists for every account
        r = requests.get(f"{k['server'].rstrip('/')}/api/v2/assets/", headers={"Authorization": f"Token {token}"},
                         params={"format": "json", "limit": 1}, timeout=30)
    except requests.RequestException as exc:
        print(f"\nPROBLEM: cannot reach {k['server']}: {exc}\n  Check your internet connection / proxy / server address.")
        return 1
    if r.status_code == 401:
        print("\nPROBLEM: Kobo rejected the token (401).\n  - Copy the token again (no spaces, no quotes).\n"
              "  - Make sure the token comes from the same server as 'server' in config.yaml:\n"
              "    kf.kobotoolbox.org (Global) vs eu.kobotoolbox.org (EU).")
        return 1
    print(f"Login  : OK (HTTP {r.status_code})\n")
    bad, n_fdaf = 0, 0
    for uid, role in projects:
        try:
            name, detected = classify_project(k["server"], token, uid)
            role = role or detected
            data = fetch_submissions(k["server"], token, uid, page_size=k.get("page_size", 1000))
            print(f"  OK   {uid}  [{role:10}] {len(data):5} submissions  - {name}")
            n_fdaf += role == "fdaf"
            if role == "unknown":
                bad += 1
                print("       ^ could not tell FDAF from Monitoring: set it under fdaf_asset_uid / monitoring_asset_uid in config.yaml")
        except KoboError as exc:
            bad += 1
            print(f"  FAIL {uid}: {exc}")
    print()
    if n_fdaf == 0:
        print("PROBLEM: no FDAF project could be read, so the dashboard has nothing to show.")
        return 1
    print("All good - start the dashboard with:  streamlit run app.py" if not bad else
          "The dashboard will still start with the projects marked OK; fix the FAIL lines to include the rest.")
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main())
