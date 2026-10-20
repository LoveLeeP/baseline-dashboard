"""Live-path test with a mocked Kobo API: 2 FDAF projects (one has NO enumerator code, only a typed name with messy
spelling) + 1 monitoring project, listed in random order.  Usage:  python -m tests.test_multi_project"""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import demo_data, kobo_client, pipeline  # noqa: E402
from src.loader import load_choice_labels, load_directory  # noqa: E402

cfg0 = pipeline.load_config()
ref = cfg0["reference"]
labels = load_choice_labels(ROOT / ref["fdaf_xlsform"])
directory = load_directory(ROOT / ref["directory"])
fdaf, mon, _ = demo_data.generate(labels, directory, ROOT / ref["monitoring_xlsform"])
half = len(fdaf) // 2
A, B = fdaf[:half], fdaf[half:]
names = directory.set_index("code")["name"].to_dict()


def key_ending(rec, suffix):
    return next(k for k in rec if k == suffix or k.endswith("/" + suffix))


ORIG = {}
for rec in B:                                   # make project B look like the MINSOC form
    code = rec.pop(key_ending(rec, "enumerator_code"))
    ORIG[rec["_id"]] = code
    for extra in ("enumerator_name", "enumerator_role"):
        try:
            rec.pop(key_ending(rec, extra))
        except StopIteration:
            pass
    parts = names.get(code, "").replace(".", "").split()
    rec["enumerator_name"] = (", ".join(reversed(parts)).upper() if int(rec["_id"]) % 2 else " ".join(reversed(parts))) + " "

PROJECTS = {"aAAA": ("FDAF version A", A), "aBBB": ("FDAF MINSOC version B", B), "aMON": ("Quality and Compliance Monitoring", mon)}


class Resp:
    def __init__(self, j, code=200): self._j, self.status_code = j, code
    def json(self): return self._j
    def raise_for_status(self): pass


def fake_get(url, headers=None, params=None, timeout=None):
    uid = url.split("/assets/")[1].split("/")[0]
    if uid not in PROJECTS:
        return Resp({}, 404)
    name, recs = PROJECTS[uid]
    if url.rstrip("/").endswith("/data"):
        return Resp({"next": None, "results": recs})
    return Resp({"name": name, "content": {"survey": []}})


tmp = Path(tempfile.mkdtemp())
os.environ["KOBO_TOKEN"] = "x"
os.environ["KOBO_PROJECTS"] = "aMON,aBBB,aAAA,aNOPE"        # monitoring first, plus one wrong UID
with mock.patch.object(kobo_client.requests, "get", fake_get), mock.patch.object(pipeline, "BASE", ROOT):
    shutil.rmtree(ROOT / "data", ignore_errors=True)
    D = pipeline.run_pipeline(pipeline.load_config())
shutil.rmtree(ROOT / "data", ignore_errors=True)

hh, proj = D["hh"], D["status"]["projects"].set_index("project_uid")
assert len(hh) == len(fdaf), (len(hh), len(fdaf))
assert proj.loc["aMON", "role"] == "monitoring" and proj.loc["aAAA", "role"] == "fdaf" and proj.loc["aBBB", "role"] == "fdaf"
assert proj.loc["aNOPE", "status"].startswith("ERROR"), "a wrong UID must be reported, not crash the dashboard"
assert hh["source_form"].nunique() == 2
orig = dict(ORIG)
bad = [(i, orig[i], c) for i, c in zip(hh["kobo_id"], hh["enumerator_code"]) if i in orig and orig[i] != c]
assert not bad, f"typed names not matched back to the right enumerator code: {bad[:5]}"
assert len(D["monitoring"]) == len(mon)
print(f"multi-project OK: {len(hh)} surveys from 2 FDAF projects, typed names resolved to {hh['enumerator_code'].nunique()} codes, "
      f"monitoring auto-detected, wrong UID reported as: {proj.loc['aNOPE', 'status'][:40]}...")
