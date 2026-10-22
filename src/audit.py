"""Audit report in the standard two-table format.

Table 1  Summary of data quality (rows audited, rows flagged, common error types)
Table 2  Flagged submissions log:
         Submission ID / _id | Question Name / Label | Submitted Value | Error Category |
         Flag Reason & Recommended Action | Severity (High / Medium / Low)

Severity mapping: Critical -> High, Major -> Medium, Minor -> Low.
"""
import pandas as pd

T2_COLS = ["Submission ID / _id", "Question Name / Label", "Submitted Value", "Error Category",
           "Flag Reason & Recommended Action", "Severity (High / Medium / Low)"]
ORDER = {"High": 0, "Medium": 1, "Low": 2}
DIM_ORDER = ["Completeness", "Validity", "Consistency", "Relevance", "Plausibility", "Uniqueness", "Timeliness", "Integrity"]


def audit_tables(flags, hh):
    total = len(hh)
    flagged = flags["uuid"].nunique() if len(flags) else 0
    high = flags[flags["audit_severity"] == "High"]["uuid"].nunique() if len(flags) else 0
    info = flags.attrs.get("skip_info") or {}
    t1 = pd.DataFrame([
        ("Total rows (submissions) audited", total),
        ("Total rows flagged (at least one flag)", f"{flagged}  ({flagged / total * 100:.0f}%)" if total else "0"),
        ("Rows with a High-severity flag", f"{high}  ({high / total * 100:.0f}%)" if total else "0"),
        ("Total flags raised", len(flags)),
        ("   High", int((flags["audit_severity"] == "High").sum()) if len(flags) else 0),
        ("   Medium", int((flags["audit_severity"] == "Medium").sum()) if len(flags) else 0),
        ("   Low", int((flags["audit_severity"] == "Low").sum()) if len(flags) else 0),
        ("Skip-rule questions tested against the form's own logic",
         f"{info.get('questions_evaluated', 0)} of {info.get('questions_total', 0)}" if info else "not run"),
    ], columns=["Measure", "Value"])

    if len(flags):
        cat = flags.groupby("audit_category").agg(flags=("rule_id", "count"), rows_affected=("uuid", "nunique")).reset_index()
        cat["% of rows audited"] = (cat["rows_affected"] / total * 100).round(1)
        cat = cat.sort_values("flags", ascending=False).rename(columns={"audit_category": "Error category"})
        rules = flags.groupby(["rule_id", "rule", "audit_severity"]).agg(flags=("uuid", "count"), rows_affected=("uuid", "nunique")) \
            .reset_index().sort_values("flags", ascending=False).head(12)
        rules = rules.rename(columns={"rule_id": "Rule", "rule": "Common error type", "audit_severity": "Severity"})
    else:
        cat = pd.DataFrame(columns=["Error category", "flags", "rows_affected", "% of rows audited"])
        rules = pd.DataFrame(columns=["Rule", "Common error type", "Severity", "flags", "rows_affected"])

    dim = pd.DataFrame({"Quality dimension": DIM_ORDER})
    if len(flags) and "audit_dimension" in flags.columns:
        g = flags.groupby("audit_dimension").agg(flags=("rule_id", "count"), rows_affected=("uuid", "nunique"))
        dim["flags"] = dim["Quality dimension"].map(g["flags"]).fillna(0).astype(int)
        dim["rows_affected"] = dim["Quality dimension"].map(g["rows_affected"]).fillna(0).astype(int)
    else:
        dim["flags"], dim["rows_affected"] = 0, 0
    dim["% of rows audited"] = (dim["rows_affected"] / total * 100).round(1) if total else 0.0

    if len(flags):
        reason = flags["detail"].astype(str) + flags["member_index"].apply(
            lambda m: f" (member #{int(m)})" if pd.notna(m) else "") + ". Action: " + flags["action"].astype(str)
        t2 = pd.DataFrame({
            "Submission ID / _id": flags["kobo_id"].fillna(flags["uuid"]).astype(str),
            "Question Name / Label": flags["question"].where(flags["question"].astype(str) != "", flags["field"]),
            "Submitted Value": flags["value"],
            "Error Category": flags["audit_category"],
            "Flag Reason & Recommended Action": reason,
            "Severity (High / Medium / Low)": flags["audit_severity"],
        })
        t2 = t2.assign(_o=t2["Severity (High / Medium / Low)"].map(ORDER)).sort_values(["_o", "Submission ID / _id"]).drop(columns="_o")
    else:
        t2 = pd.DataFrame(columns=T2_COLS)
    return {"t1": t1, "t1_category": cat, "t1_rules": rules, "t1_dimension": dim, "t2": t2.reset_index(drop=True)}


def to_markdown(df, max_rows=None):
    d = df.head(max_rows) if max_rows else df
    cols = list(d.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in d.itertuples(index=False):
        lines.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in r) + " |")
    return "\n".join(lines)
