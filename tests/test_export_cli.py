"""Builds a Kobo-style EXPORT (xlsx) from synthetic data and audits it through audit_export.py.
Usage: python -m tests.test_export_cli"""
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import demo_data  # noqa: E402
from src.loader import load_choice_labels, load_directory  # noqa: E402
from src.pipeline import BASE, load_config  # noqa: E402

cfg = load_config()
ref = cfg["reference"]
recs, _, truth = demo_data.generate(load_choice_labels(BASE / ref["fdaf_xlsform"]), load_directory(BASE / ref["directory"]), BASE / ref["monitoring_xlsform"])
main, members = [], []
for i, r in enumerate(recs, 1):
    row = {k: v for k, v in r.items() if k not in ("hh_members", "_geolocation")}
    row["_index"] = i
    main.append(row)
    for j, m in enumerate(r["hh_members"], 1):
        members.append({**m, "_parent_index": i, "_index": j})
tmp = Path(tempfile.mkdtemp())
with pd.ExcelWriter(tmp / "export.xlsx") as w:
    pd.DataFrame(main).to_excel(w, sheet_name="Pagyabong FDAF", index=False)
    pd.DataFrame(members).to_excel(w, sheet_name="hh_members", index=False)
res = subprocess.run([sys.executable, str(ROOT / "audit_export.py"), str(tmp / "export.xlsx"), "--out", str(tmp), "--rows", "5"],
                     capture_output=True, text=True)
print(res.stdout[-2600:]); print(res.stderr[-800:])
assert res.returncode == 0, "audit_export failed"
t2 = pd.read_csv(tmp / "audit_flagged_submissions_log.csv", dtype=str)
assert list(t2.columns) == ["Submission ID / _id", "Question Name / Label", "Submitted Value", "Error Category",
                            "Flag Reason & Recommended Action", "Severity (High / Medium / Low)"], list(t2.columns)
assert set(t2["Severity (High / Medium / Low)"]) <= {"High", "Medium", "Low"}
print(f"\nexport audit OK: {len(t2)} flags, columns match the required Table 2 format")
