"""Audit a KoboToolbox EXPORT file (no API needed) and print the two-table report.

  python audit_export.py my_export.xlsx                       # Excel export: main sheet + hh_members sheet
  python audit_export.py main.csv --members hh_members.csv    # CSV export (repeat group is a separate CSV)

Export settings in Kobo (Downloads > Export): format XLS or CSV, value and header format = "XML values and headers",
"Include groups in headers" on or off (both work), include all versions.  Output: Table 1 and Table 2 on screen and in
audit_report.xlsx / audit_flagged_submissions_log.csv.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.audit import audit_tables, to_markdown  # noqa: E402
from src.integrity import run_checks  # noqa: E402
from src.loader import build_fdaf_tables, load_choice_labels, load_directory, load_item_labels  # noqa: E402
from src.pipeline import BASE, load_config  # noqa: E402


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v).strip()


def _norm_cols(df):
    df = df.copy()
    df.columns = [str(c).split("/")[-1] if not str(c).startswith("_") else str(c) for c in df.columns]
    return df.loc[:, ~df.columns.duplicated()]


def read_export(path, members_path=None):
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        sheets = pd.read_excel(path, sheet_name=None, dtype=object)
        names = list(sheets)
        main = _norm_cols(sheets[names[0]])
        mem = next((_norm_cols(v) for k, v in sheets.items() if k.lower() == "hh_members" or "_parent_index" in v.columns), None)
    else:
        main = _norm_cols(pd.read_csv(path, dtype=object, sep=None, engine="python"))
        mem = _norm_cols(pd.read_csv(members_path, dtype=object, sep=None, engine="python")) if members_path else None
    if "_uuid" not in main.columns:
        main["_uuid"] = [f"row{i + 1}" for i in range(len(main))]
    if "_index" not in main.columns:
        main["_index"] = range(1, len(main) + 1)
    members = {}
    if mem is not None and "_parent_index" in mem.columns:
        for rec in mem.to_dict("records"):
            members.setdefault(_clean(rec.get("_parent_index")), []).append({k: _clean(v) for k, v in rec.items() if _clean(v) is not None})
    records = []
    for rec in main.to_dict("records"):
        d = {k: _clean(v) for k, v in rec.items() if _clean(v) is not None}
        d["hh_members"] = members.get(_clean(rec.get("_index")), [])
        records.append(d)
    return records, mem is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("--members", help="CSV of the hh_members repeat group (CSV exports only)")
    ap.add_argument("--out", default=".")
    ap.add_argument("--rows", type=int, default=40, help="rows of Table 2 to print")
    a = ap.parse_args()
    cfg = load_config()
    ref = cfg["reference"]
    records, has_members = read_export(a.export, a.members)
    if not records:
        sys.exit("No rows found in the export.")
    if not has_members:
        print("NOTE: no hh_members sheet/CSV found - family-member checks are skipped.\n")
    sample = [r.get("informed_consent") for r in records if r.get("informed_consent")]
    if sample and all(v not in ("0", "1") for v in sample[:20]):
        print("WARNING: answers look like labels (e.g. 'Yes'). Re-export with 'XML values and headers' so the codes match the form.\n")
    labels = load_choice_labels(BASE / ref["fdaf_xlsform"])
    directory = load_directory(BASE / ref["directory"])
    hh, mem = build_fdaf_tables(records, cfg, labels, directory)
    flags, integ, _ = run_checks(hh, mem, cfg, labels=load_item_labels(BASE / ref["fdaf_xlsform"]), xlsx_path=BASE / ref["fdaf_xlsform"])
    A = audit_tables(flags, hh)

    print("## Table 1: Summary of Data Quality\n")
    print(to_markdown(A["t1"]))
    print("\nCommon error categories\n")
    print(to_markdown(A["t1_category"]))
    print("\nMost common error types\n")
    print(to_markdown(A["t1_rules"]))
    print("\nData-quality dimensions\n")
    print(to_markdown(A["t1_dimension"]))
    print(f"\n## Table 2: Flagged Submissions Log (first {a.rows} of {len(A['t2'])})\n")
    print(to_markdown(A["t2"], a.rows))

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out / "audit_report.xlsx", engine="openpyxl") as w:
        A["t1"].to_excel(w, sheet_name="Table 1 Summary", index=False)
        A["t1_category"].to_excel(w, sheet_name="Table 1 Categories", index=False)
        A["t1_rules"].to_excel(w, sheet_name="Table 1 Error types", index=False)
        A["t1_dimension"].to_excel(w, sheet_name="Table 1 Dimensions", index=False)
        A["t2"].to_excel(w, sheet_name="Table 2 Flag log", index=False)
        for ws in w.sheets.values():
            ws.freeze_panes = "A2"
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(70, max(12, max(len(str(c.value or "")) for c in col[:80]) + 2))
    A["t2"].to_csv(out / "audit_flagged_submissions_log.csv", index=False, encoding="utf-8-sig")
    print(f"\nSaved {out / 'audit_report.xlsx'} and audit_flagged_submissions_log.csv")


if __name__ == "__main__":
    main()
