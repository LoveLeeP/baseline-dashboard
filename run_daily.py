"""Scheduled job: pull Kobo data, run all checks, write CSV + Excel outputs (for Power BI / Looker Studio / email).

  python run_daily.py              # live data from KoboToolbox
  python run_daily.py --demo       # synthetic data (to test the setup)
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.pipeline import BASE, load_config, run_pipeline  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--out", default=str(BASE / "output"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    D = run_pipeline(load_config(), demo=a.demo)

    sheets = {
        "Daily surveys": D["daily"],
        "Enumerator confidence": D["enumerators"],
        "Monitoring scores": D["monitoring"][["monitoring_date", "monitor_label", "monitor_title", "enumerator_label", "enumerator_title",
                                              "fdaf_family_id", "overall_score", "critical_fail", "consent_declined"]
                                             + [f"s{n}_score" for n in range(1, 10)]],
        "Monitoring items": D["items"][["monitoring_date", "monitor_label", "enumerator_label", "section", "item", "question", "rating", "explanation"]],
        "Integrity flags": D["flags"][["interview_date", "hh_id", "enumerator_label", "title", "municipality_label", "barangay_label",
                                       "rule_id", "severity", "category", "rule", "member_index", "detail"]],
        "Table 1 Summary": D["audit"]["t1"],
        "Table 1 Categories": D["audit"]["t1_category"],
        "Table 1 Error types": D["audit"]["t1_rules"],
        "Table 2 Flag log": D["audit"]["t2"],
        "Integrity by survey": D["integrity"],
        "Rules": D["catalogue"],
    }
    for name, df in sheets.items():
        df.to_csv(out / (name.lower().replace(" ", "_") + ".csv"), index=False, encoding="utf-8-sig")
    xlsx = out / f"FDAF_dashboard_report_{date.today():%Y%m%d}.xlsx"
    with __import__("pandas").ExcelWriter(xlsx, engine="openpyxl") as w:
        for name, df in sheets.items():
            d = df.copy()
            for c in d.columns:  # Excel cannot store timezone-aware datetimes
                if str(d[c].dtype).startswith("datetime64") and getattr(d[c].dt, "tz", None) is not None:
                    d[c] = d[c].dt.tz_localize(None)
            d.to_excel(w, sheet_name=name[:31], index=False)
            ws = w.sheets[name[:31]]
            ws.freeze_panes = "A2"
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(48, max(10, max(len(str(c.value or "")) for c in col[:60]) + 2))
    s = D["status"]
    print(f"{s['source']} | {s['fdaf_records']} FDAF, {s['monitoring_records']} monitoring submissions")
    print(f"Wrote {xlsx} and CSV files in {out}")


if __name__ == "__main__":
    main()
