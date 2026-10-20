"""Quality & compliance monitoring scores and the combined enumerator confidence level."""
import re

import numpy as np
import pandas as pd

from .loader import normalize_record

SECTION_NAMES = {1: "1 Registration", 2: "2 Family composition", 3: "3 Shock & risk", 4: "4 Education",
                 5: "5 Nutrition & WASH", 6: "6 Livelihood & food", 7: "7 Governance", 8: "8 Resilience", 9: "9 Case assessment"}
REN = {"_uuid": "uuid", "_id": "kobo_id", "_submission_time": "submission_time", "_submitted_by": "submitted_by"}
ITEM_RE = re.compile(r"^s(\d)_(\d{2})_(.+)$")


def _num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def build_monitoring(records, cfg, directory, item_labels=None):
    """Return (one row per monitoring submission, one row per rated item)."""
    tz = cfg.get("timezone", "Asia/Manila")
    mcfg = cfg.get("monitoring", {})
    df = pd.DataFrame([normalize_record(r) for r in records]).rename(columns=REN)
    for c in ("uuid", "monitor_code", "monitor_name", "monitor_role", "monitoring_date", "enumerator_monitored",
              "fdaf_family_id", "interview_date", "g_consent", "submission_time"):
        if c not in df.columns:
            df[c] = np.nan
    df["monitoring_date"] = pd.to_datetime(df["monitoring_date"], errors="coerce").fillna(
        pd.to_datetime(df["submission_time"], errors="coerce", utc=True).dt.tz_convert(tz).dt.tz_localize(None)).dt.normalize()
    df["interview_date"] = pd.to_datetime(df["interview_date"], errors="coerce")

    tot_p, tot_a = 0, 0
    for n in range(1, 10):
        p = _num(df.get(f"s{n}_points", pd.Series(0, index=df.index)))
        a = _num(df.get(f"s{n}_applicable", pd.Series(0, index=df.index)))
        df[f"s{n}_score"] = np.where(a > 0, p / a.replace(0, np.nan) * 100, np.nan)
        df[f"s{n}_applicable_n"] = a
        tot_p, tot_a = tot_p + p, tot_a + a
    df["overall_score"] = np.where(tot_a > 0, tot_p / tot_a.replace(0, np.nan) * 100, np.nan)
    df["items_rated"] = tot_a

    crit_items = [c for c in mcfg.get("critical_items", []) if c in df.columns]
    bad = set(mcfg.get("critical_ratings", ["no"]))
    df["critical_fail"] = False
    for c in crit_items:
        df["critical_fail"] |= df[c].isin(bad)
    df["consent_declined"] = df["g_consent"].astype(str).eq("no")

    d = directory.set_index("code")
    df["enumerator_label"] = df["enumerator_monitored"].map(d["label"]).fillna(df["enumerator_monitored"])
    df["enumerator_title"] = df["enumerator_monitored"].map(d["title"]).fillna("Unknown")
    df["monitor_label"] = df["monitor_code"].map(d["label"]).fillna(df["monitor_code"])
    df["monitor_title"] = df["monitor_code"].map(d["title"]).fillna(df["monitor_role"]).fillna("Unknown")

    # long item table
    item_cols = [c for c in df.columns if ITEM_RE.match(c) and not c.endswith("_expl")]
    long = []
    for c in item_cols:
        sec, num_, field = ITEM_RE.match(c).groups()
        part = df[["uuid", "monitoring_date", "enumerator_monitored", "enumerator_label", "monitor_label", c]].copy()
        part = part[part[c].notna() & (part[c].astype(str) != "")]
        part = part.rename(columns={c: "rating"})
        part["explanation"] = df.loc[part.index, c + "_expl"] if c + "_expl" in df.columns else ""
        part["section"] = int(sec)
        part["item"] = f"Q{sec}.{int(num_)}"
        part["field"] = field
        part["question"] = (item_labels or {}).get(c, field)
        long.append(part)
    items = pd.concat(long, ignore_index=True) if long else pd.DataFrame(
        columns=["uuid", "monitoring_date", "enumerator_monitored", "enumerator_label", "monitor_label", "rating",
                 "explanation", "section", "item", "field", "question"])
    return df.reset_index(drop=True), items


def _level(score, cfg):
    c = cfg.get("confidence", {})
    if pd.isna(score):
        return "No data"
    if score >= c.get("high_min", 90):
        return "High"
    if score >= c.get("medium_min", 75):
        return "Medium"
    return "Low"


def enumerator_scores(hh, integ, mon, directory, cfg):
    """One row per enumerator/CF: surveys, integrity, monitoring, combined confidence."""
    c = cfg.get("confidence", {})
    wm, wi = c.get("weight_monitoring", 0.6), c.get("weight_integrity", 0.4)
    min_mon = cfg.get("monitoring", {}).get("min_monitored_surveys", 2)

    people = directory[directory["code"].str.match(r"^(E\d+|CF\d+)$")][["code", "label", "title", "home_area"]].copy()
    people = people.rename(columns={"code": "enumerator_code", "label": "enumerator_label"})
    extra = set(hh["enumerator_code"]) - set(people["enumerator_code"]) - {""}
    if extra:
        ex = (hh[hh["enumerator_code"].isin(extra)].groupby("enumerator_code")
              .agg(enumerator_label=("enumerator_label", "first"), title=("title", "first"),
                   home_area=("municipality_label", "first")).reset_index())
        ex["title"] = ex["title"].replace("Unknown", "Not in directory")
        people = pd.concat([people, ex[["enumerator_code", "enumerator_label", "title", "home_area"]]], ignore_index=True)

    s = hh.groupby("enumerator_code").agg(surveys=("uuid", "count"), consented=("consented", "sum"),
                                          first_survey=("interview_date", "min"), last_survey=("interview_date", "max"))
    i = integ.groupby("enumerator_code").agg(integrity_score=("integrity_score", "mean"), clean_rate=("clean", "mean"),
                                             critical_flags=("Critical", "sum"), major_flags=("Major", "sum"),
                                             minor_flags=("Minor", "sum"))
    m = mon[~mon["consent_declined"]].groupby("enumerator_monitored").agg(
        monitored=("uuid", "count"), monitoring_score=("overall_score", "mean"),
        last_monitored=("monitoring_date", "max"), critical_fails=("critical_fail", "sum"))
    out = people.merge(s, left_on="enumerator_code", right_index=True, how="left") \
        .merge(i, left_on="enumerator_code", right_index=True, how="left") \
        .merge(m, left_on="enumerator_code", right_index=True, how="left")
    for col in ("surveys", "consented", "monitored", "critical_fails", "critical_flags", "major_flags", "minor_flags"):
        out[col] = out[col].fillna(0).astype(int)
    out["integrity_score"] = out["integrity_score"] * 1.0
    out["clean_rate"] = out["clean_rate"] * 100

    def combine(r):
        mon_s, int_s = r["monitoring_score"], r["integrity_score"]
        if pd.notna(mon_s) and pd.notna(int_s):
            return (wm * mon_s + wi * int_s) / (wm + wi), "Monitoring + integrity"
        if pd.notna(int_s):
            return int_s, "Integrity only (not yet monitored)"
        if pd.notna(mon_s):
            return mon_s, "Monitoring only"
        return np.nan, "No data yet"

    res = out.apply(combine, axis=1, result_type="expand")
    out["confidence_score"], out["basis"] = res[0], res[1]
    out["confidence_level"] = out["confidence_score"].apply(lambda v: _level(v, cfg))
    out["note"] = ""
    capped = out["critical_fails"] > 0
    out.loc[capped, "confidence_level"] = "Low"
    out.loc[capped, "note"] = "Capped to Low: failed a critical monitoring item (consent)"
    prov = (out["monitored"] < min_mon) & out["confidence_score"].notna()
    out.loc[prov, "note"] = (out.loc[prov, "note"] + " Provisional: fewer than " + str(min_mon) + " monitored surveys.").str.strip()
    
    # Filter out enumerators with zero submissions to keep metrics and averages accurate
    out = out[out["surveys"] > 0].reset_index(drop=True)
    
    return out.sort_values(["confidence_score"], na_position="last").reset_index(drop=True)