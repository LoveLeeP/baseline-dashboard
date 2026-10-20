"""Automated accuracy / data-integrity checker for the FDAF.

Each rule compares answers that should agree with each other (e.g. age vs schooling, livelihood vs income)
and returns flags. Severity: Critical (data cannot be trusted), Major (likely wrong), Minor (please verify).
Flags carry the Family ID and member number only - never names - so they are safe to share.
"""
import difflib
import re
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

DEFAULTS = {
    "min_interview_minutes": 10, "minutes_per_member": 2, "max_interview_minutes": 240, "late_submission_days": 7,
    "gps_accuracy_max_m": 50, "max_surveys_per_enumerator_per_day": 10, "working_hours": [5, 21],
    "max_monthly_income": 150000, "max_farm_hectares": 20, "low_income_per_capita": 1500,
    "high_income_per_capita": 15000, "straightline_min_answers": 7,
    "severity_weights": {"Critical": 25, "Major": 10, "Minor": 3},
    "project_start_date": "2026-01-01", "max_household_size": 12,
}
RULES = []


def rule(rid, severity, level, category, title):
    def deco(fn):
        RULES.append(dict(id=rid, severity=severity, level=level, category=category, title=title, fn=fn))
        return fn
    return deco


# ---------------- helpers ----------------
def toks(v):
    return set(str(v).split()) if isinstance(v, str) and v.strip() else set()


def s(v):
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v).strip()


def norm_name(v):
    return re.sub(r"[^a-z ]", "", s(v).lower().replace(",", " ")).split()


def name_sim(a, b):
    ta, tb = sorted(norm_name(a)), sorted(norm_name(b))
    if not ta or not tb:
        return 1.0
    if ta == tb:
        return 1.0
    return difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()


def F(uuid, detail, mi=None, sev=None):
    d = {"uuid": uuid, "member_index": mi, "detail": detail}
    if sev:
        d["sev"] = sev
    return d


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


# ================= HOUSEHOLD-LEVEL RULES =================
@rule("HH01", "Critical", "household", "Identity", "Duplicate Family ID")
def hh01(hh, mem, T):
    d = hh[hh["hh_id"].notna() & hh.duplicated("hh_id", keep=False)]
    return [F(r.uuid, f"Family ID {r.hh_id} appears in more than one submission") for r in d.itertuples()]


@rule("HH02", "Critical", "household", "Process", "Members recorded although consent not given")
def hh02(hh, mem, T):
    out = []
    for r in hh.itertuples():
        if s(r.informed_consent) == "0" and r.n_members > 0:
            out.append(F(r.uuid, "Consent = No but a member roster was recorded"))
        elif s(r.informed_consent) == "":
            out.append(F(r.uuid, "Consent answer is missing"))
    return out


@rule("HH03", "Critical", "household", "Identity", "Not exactly one Family Head in roster")
def hh03(hh, mem, T):
    cnt = mem[mem["member_relationship"] == "hh_head"].groupby("uuid").size()
    out = []
    for r in hh[hh["consented"]].itertuples():
        n = int(cnt.get(r.uuid, 0))
        if n != 1:
            out.append(F(r.uuid, f"{n} family head(s) in the roster (expected 1)"))
    return out


@rule("HH04", "Major", "household", "Identity", "Family head name differs from roster head")
def hh04(hh, mem, T):
    heads = mem[mem["member_relationship"] == "hh_head"].drop_duplicates("uuid").set_index("uuid")["member_full_name"]
    return [F(r.uuid, "Head name in Section 1 does not match the roster head")
            for r in hh.itertuples() if r.uuid in heads.index and name_sim(r.hh_head_name, heads[r.uuid]) < 0.6]


@rule("HH05", "Major", "household", "Identity", "Family head gender differs from roster head sex")
def hh05(hh, mem, T):
    heads = mem[mem["member_relationship"] == "hh_head"].drop_duplicates("uuid").set_index("uuid")["member_sex"]
    return [F(r.uuid, f"Head gender '{r.hh_head_gender}' vs roster sex '{heads[r.uuid]}'")
            for r in hh.itertuples()
            if r.uuid in heads.index and s(r.hh_head_gender) and s(heads[r.uuid]) and s(r.hh_head_gender) != s(heads[r.uuid])]


@rule("HH06", "Major", "household", "Identity", "Respondent relationship does not match respondent name")
def hh06(hh, mem, T):
    out = []
    for r in hh.itertuples():
        same = name_sim(r.respondent_name, r.hh_head_name) >= 0.8 and s(r.respondent_name) and s(r.hh_head_name)
        if s(r.respondent_relationship) == "hh_head" and s(r.respondent_name) and not same:
            out.append(F(r.uuid, "Respondent is marked 'Family Head' but the name differs from the head"))
        elif s(r.respondent_relationship) and s(r.respondent_relationship) != "hh_head" and same:
            out.append(F(r.uuid, "Respondent has the head's name but a different relationship"))
    return out


@rule("HH07", "Major", "household", "Process", "Interview too short for household size")
def hh07(hh, mem, T):
    out = []
    for r in hh[hh["consented"]].itertuples():
        need = T["min_interview_minutes"] + T["minutes_per_member"] * r.n_members
        if pd.notna(r.duration_min) and r.duration_min < need:
            out.append(F(r.uuid, f"{r.duration_min:.0f} min recorded; at least {need:.0f} min expected for {r.n_members} members"))
    return out


@rule("HH08", "Minor", "household", "Process", "Interview unusually long")
def hh08(hh, mem, T):
    return [F(r.uuid, f"{r.duration_min:.0f} min recorded") for r in hh.itertuples()
            if pd.notna(r.duration_min) and r.duration_min > T["max_interview_minutes"]]


@rule("HH09", "Major", "household", "Process", "Device date inconsistent with submission")
def hh09(hh, mem, T):
    out = []
    for r in hh.itertuples():
        if pd.isna(r.interview_date) or pd.isna(r.submission_time_dt):
            continue
        sub = r.submission_time_dt.tz_localize(None).normalize()
        start = r.start_dt.tz_localize(None).normalize() if pd.notna(r.start_dt) else r.interview_date
        if r.interview_date > sub + pd.Timedelta(days=1):
            out.append(F(r.uuid, "Interview date is after the submission date"))
        elif abs((r.interview_date - start).days) > 1:
            out.append(F(r.uuid, "Interview date differs from the start timestamp (device clock?)"))
    return out


@rule("HH10", "Minor", "household", "Process", "Late submission")
def hh10(hh, mem, T):
    out = []
    for r in hh.itertuples():
        if pd.notna(r.interview_date) and pd.notna(r.submission_time_dt):
            lag = (r.submission_time_dt.tz_localize(None).normalize() - r.interview_date).days
            if lag > T["late_submission_days"]:
                out.append(F(r.uuid, f"Submitted {lag} days after the interview"))
    return out


@rule("HH11", "Major", "household", "Identity", "IP family flag inconsistent with ICC/IP group")
def hh11(hh, mem, T):
    out = []
    for r in hh[hh["consented"]].itertuples():
        if s(r.is_ip_family) == "1" and not s(r.icc_ip_group):
            out.append(F(r.uuid, "IP family = Yes but no ICC/IP group recorded"))
        if s(r.is_ip_family) == "0" and s(r.icc_ip_group):
            out.append(F(r.uuid, "IP family = No but an ICC/IP group is recorded"))
    return out


@rule("HH12", "Major", "household", "Location", "GPS missing")
def hh12(hh, mem, T):
    return [F(r.uuid, "No GPS coordinate captured") for r in hh[hh["consented"]].itertuples() if pd.isna(r.lat)]


@rule("HH13", "Minor", "household", "Location", "Poor GPS accuracy")
def hh13(hh, mem, T):
    return [F(r.uuid, f"GPS accuracy {r.gps_acc:.0f} m") for r in hh.itertuples()
            if pd.notna(r.gps_acc) and r.gps_acc > T["gps_accuracy_max_m"]]


@rule("HH14", "Critical", "household", "Location", "GPS outside the Philippines")
def hh14(hh, mem, T):
    return [F(r.uuid, f"Coordinates ({r.lat:.3f}, {r.lon:.3f}) are outside the Philippines") for r in hh.itertuples()
            if pd.notna(r.lat) and not (4.5 <= r.lat <= 21.5 and 116 <= r.lon <= 127)]


@rule("HH15", "Major", "household", "Location", "Same GPS point used by different families")
def hh15(hh, mem, T):
    g = hh[hh["lat"].notna()].copy()
    g["k"] = g["lat"].round(4).astype(str) + "," + g["lon"].round(4).astype(str)
    d = g[g.duplicated("k", keep=False) & g["hh_id"].ne("")]
    d = d.groupby("k").filter(lambda x: x["hh_id"].nunique() > 1)
    return [F(r.uuid, "GPS point shared with another family (possible copied location)") for r in d.itertuples()]


@rule("HH16", "Major", "household", "Demographics", "Household size calculation does not match roster")
def hh16(hh, mem, T):
    out = []
    for r in hh.itertuples():
        if pd.notna(r.hh_size_count) and int(r.hh_size_count) != r.n_members:
            out.append(F(r.uuid, f"hh_size_count={int(r.hh_size_count)} but {r.n_members} members in roster"))
    u6 = mem[mem["age_calc"] < 6].groupby("uuid").size()
    for r in hh.itertuples():
        if pd.notna(r.hh_child_u6_count) and int(r.hh_child_u6_count) != int(u6.get(r.uuid, 0)):
            out.append(F(r.uuid, f"hh_child_u6_count={int(r.hh_child_u6_count)} but {int(u6.get(r.uuid, 0))} recomputed from DOB"))
    return out


@rule("HH17", "Major", "household", "Demographics", "No adult (18+) in household")
def hh17(hh, mem, T):
    adults = mem[mem["age_calc"] >= 18].groupby("uuid").size()
    return [F(r.uuid, "Every member is under 18") for r in hh[hh["consented"] & (hh["n_members"] > 0)].itertuples()
            if int(adults.get(r.uuid, 0)) == 0]


@rule("HH18", "Major", "household", "Demographics", "More than one spouse in roster")
def hh18(hh, mem, T):
    c = mem[mem["member_relationship"] == "spouse"].groupby("uuid").size()
    return [F(u, f"{n} members marked as Spouse") for u, n in c.items() if n > 1]


# ---- livelihood / income / food ----
@rule("LV01", "Major", "household", "Livelihood", "Primary livelihood not among livelihood sources")
def lv01(hh, mem, T):
    return [F(r.uuid, f"Primary livelihood '{r.primary_livelihood}' is not in the selected sources")
            for r in hh.itertuples()
            if s(r.primary_livelihood) and toks(r.livelihood_sources) and s(r.primary_livelihood) not in toks(r.livelihood_sources)]


@rule("LV02", "Major", "household", "Livelihood", "'No livelihood' selected together with other sources")
def lv02(hh, mem, T):
    return [F(r.uuid, "'None' livelihood selected with other livelihood sources") for r in hh.itertuples()
            if "none_livelihood" in toks(r.livelihood_sources) and len(toks(r.livelihood_sources)) > 1]


@rule("LV03", "Minor", "household", "Livelihood", "Income does not match livelihood")
def lv03(hh, mem, T):
    out = []
    for r in hh[hh["consented"]].itertuples():
        src = toks(r.livelihood_sources) - {"none_livelihood"}
        if pd.notna(r.monthly_income):
            if r.monthly_income == 0 and src and s(r.primary_livelihood) not in ("", "none_livelihood"):
                out.append(F(r.uuid, "Income is 0 although livelihood sources were recorded"))
            if r.monthly_income > 0 and s(r.primary_livelihood) == "none_livelihood":
                out.append(F(r.uuid, "Income recorded although primary livelihood is 'None'"))
    return out


@rule("LV04", "Major", "household", "Livelihood", "Implausible monthly income")
def lv04(hh, mem, T):
    return [F(r.uuid, f"Monthly income {r.monthly_income:,.0f}") for r in hh.itertuples()
            if pd.notna(r.monthly_income) and (r.monthly_income < 0 or r.monthly_income > T["max_monthly_income"])]


@rule("LV05", "Minor", "household", "Livelihood", "Income per person does not match 'basic needs' answer")
def lv05(hh, mem, T):
    out = []
    for r in hh.itertuples():
        if pd.notna(r.monthly_income) and r.n_members > 0:
            pc = r.monthly_income / r.n_members
            if s(r.basic_needs_sufficiency) == "4" and pc < T["low_income_per_capita"]:
                out.append(F(r.uuid, f"'Always able' to meet needs but income per person is only {pc:,.0f}"))
            if s(r.basic_needs_sufficiency) == "0" and pc > T["high_income_per_capita"]:
                out.append(F(r.uuid, f"'Not able' to meet needs but income per person is {pc:,.0f}"))
    return out


@rule("LV06", "Major", "household", "Livelihood", "Farmland answers inconsistent with livelihood")
def lv06(hh, mem, T):
    out = []
    for r in hh[hh["consented"]].itertuples():
        if s(r.cultivates_farmland) == "1" and "crop_farming" not in toks(r.livelihood_sources):
            out.append(F(r.uuid, "Cultivates farmland but crop farming is not a livelihood source"))
        if s(r.cultivates_farmland) == "0" and pd.notna(r.farm_hectares) and r.farm_hectares > 0:
            out.append(F(r.uuid, "Farm hectares recorded although the family does not cultivate farmland"))
    return out


@rule("LV07", "Major", "household", "Livelihood", "Farm size missing or implausible")
def lv07(hh, mem, T):
    out = []
    for r in hh.itertuples():
        if s(r.cultivates_farmland) == "1" and (pd.isna(r.farm_hectares) or r.farm_hectares <= 0):
            out.append(F(r.uuid, "Cultivates farmland but farm hectares is missing or 0"))
        if pd.notna(r.farm_hectares) and r.farm_hectares > T["max_farm_hectares"]:
            out.append(F(r.uuid, f"{r.farm_hectares:g} hectares recorded"))
    return out


@rule("LV08", "Major", "household", "Livelihood", "Harvest proportions add up to more than 100%")
def lv08(hh, mem, T):
    lower = {"4": 76, "3": 51, "2": 26, "1": 1, "0": 0}
    out = []
    for r in hh.itertuples():
        vals = [lower.get(s(x)) for x in (r.market_sold_proportion, r.harvest_food_proportion, r.harvest_shared_proportion)]
        if all(v is not None for v in vals) and sum(vals) > 100:
            out.append(F(r.uuid, "Sold + eaten + shared proportions cannot exceed 100%"))
    return out


@rule("LV09", "Major", "household", "Food security", "Food insecurity contradicts 'basic needs' answer")
def lv09(hh, mem, T):
    out = []
    for r in hh.itertuples():
        if s(r.severe_food_insecurity) == "0" and s(r.basic_needs_sufficiency) == "4":
            out.append(F(r.uuid, "Often goes without food but 'always able' to meet basic needs"))
        if s(r.severe_food_insecurity) == "4" and s(r.food_insecurity_reason):
            out.append(F(r.uuid, "Never food insecure but a reason for food insecurity is recorded"))
    return out


@rule("LV10", "Major", "household", "Food security", "Own-food production inconsistent with food types")
def lv10(hh, mem, T):
    out = []
    for r in hh.itertuples():
        if s(r.produces_own_food) == "1" and not toks(r.home_produced_food_types):
            out.append(F(r.uuid, "Produces own food but no food types recorded"))
        if s(r.produces_own_food) == "0" and toks(r.home_produced_food_types):
            out.append(F(r.uuid, "Does not produce own food but food types are recorded"))
    return out


@rule("LV11", "Minor", "household", "Livelihood", "Livestock / fishing recorded without matching livelihood")
def lv11(hh, mem, T):
    out = []
    for r in hh.itertuples():
        if toks(r.livestock_raised) and "livestock" not in toks(r.livelihood_sources):
            out.append(F(r.uuid, "Livestock raised but not a livelihood source"))
        if s(r.fishing_activity) and "fisheries" not in toks(r.livelihood_sources):
            out.append(F(r.uuid, "Fishing activity recorded but fisheries is not a livelihood source"))
    return out


# ---- water / sanitation ----
@rule("WS01", "Major", "household", "WASH", "Water source inconsistent with collection time")
def ws01(hh, mem, T):
    out = []
    far = {"river_lake", "unprotected_spring", "unprotected_dug_well", "communal_faucet", "protected_spring"}
    for r in hh.itertuples():
        if s(r.drinking_water_source) == "level3_piped" and s(r.water_collection_time) not in ("", "4"):
            out.append(F(r.uuid, "Piped connection but water is not inside the house/yard"))
        if s(r.water_collection_time) == "4" and s(r.drinking_water_source) in far:
            out.append(F(r.uuid, f"Water 'inside house/yard' but source is {r.drinking_water_source}"))
    return out


@rule("WS02", "Minor", "household", "WASH", "Unsafe water source but full confidence in water safety")
def ws02(hh, mem, T):
    unsafe = {"river_lake", "unprotected_spring", "unprotected_dug_well"}
    return [F(r.uuid, "Unsafe source but 'very confident' water is safe and always available") for r in hh.itertuples()
            if s(r.drinking_water_source) in unsafe and s(r.water_safety_confidence) == "4" and s(r.water_access_status) == "4"]


# ---- multi-select / response-pattern checks ----
NONE_OPTIONS = {"hh_assets_owned": "none", "hh_shock_risk": "none_shock", "hh_challenges_top3": "no_challenges",
                "sustainable_practices": "none_practice", "environmental_practices": "none_env",
                "community_org_participation": "none_org", "recommended_programs": "none_recommended", "governance_cycle_participation": "none_gov_cycle",
                "school_engagement_type_answer": "none_engagement"}


@rule("SO01", "Major", "household", "Response pattern", "'None' selected together with other options")
def so01(hh, mem, T):
    out = []
    for r in hh.itertuples():
        for col, none in NONE_OPTIONS.items():
            t = toks(getattr(r, col, ""))
            if none in t and len(t) > 1:
                out.append({**F(r.uuid, f"'{none}' selected together with other options in {col}"), "field": col, "value": " ".join(sorted(t))})
    return out


@rule("SO02", "Minor", "household", "Response pattern", "More than 3 family challenges selected")
def so02(hh, mem, T):
    return [{**F(r.uuid, f"{len(toks(r.hh_challenges_top3))} challenges selected (top 3 expected)"), "field": "hh_challenges_top3",
             "value": s(r.hh_challenges_top3)} for r in hh.itertuples() if len(toks(r.hh_challenges_top3)) > 3]


STRAIGHT = ["water_access_status", "water_safety_confidence", "basic_needs_sufficiency", "family_nutrition_ability",
            "family_voice", "leaders_assistance_confidence", "climate_resilience_confidence",
            "food_from_production_months", "severe_food_insecurity", "toilet_quality", "ipra_awareness",
            "school_community_engagement", "manapack_consistency", "caregiver_feeding_practice"]


@rule("SO03", "Minor", "household", "Response pattern", "Identical answers across many scale questions")
def so03(hh, mem, T):
    out = []
    for r in hh[hh["consented"]].itertuples():
        vals = [s(getattr(r, c, "")) for c in STRAIGHT]
        vals = [v for v in vals if v != ""]
        if len(vals) >= T["straightline_min_answers"]:
            top, n_top = Counter(vals).most_common(1)[0]
            if n_top / len(vals) >= 0.9:
                out.append(F(r.uuid, f"{n_top} of {len(vals)} scale questions answered '{top}'"))
    return out


@rule("SO05", "Major", "household", "Process", "Possible duplicate interview (same head name, barangay and birth date)")
def so05(hh, mem, T):
    heads = mem[mem["member_relationship"] == "hh_head"].drop_duplicates("uuid")
    hd = {u: str(v) for u, v in zip(heads["uuid"], heads["dob"])}
    g = hh.copy()
    g["hdob"] = g["uuid"].map(hd).fillna("nodob").astype(str)
    g["k"] = g["hh_head_name"].apply(lambda v: " ".join(sorted(norm_name(v)))) + "|" + g["barangay"].astype(str) + "|" + g["hdob"]
    d = g[g["hh_head_name"].notna() & g.duplicated("k", keep=False)]
    d = d.groupby("k").filter(lambda x: x["uuid"].nunique() > 1)
    return [F(r.uuid, "Another submission has the same head name, barangay and birth date") for r in d.itertuples()]


FP_SKIP = {"uuid", "_id", "_submission_time", "_submitted_by", "start", "end", "today", "hh_id", "hh_head_name",
           "respondent_name", "gps_coordinate", "lat", "lon", "gps_acc", "interview_date", "duration_min",
           "n_members", "enumerator_name"}


@rule("SO06", "Major", "household", "Response pattern", "Identical answer set in different surveys (possible copy-paste)")
def so06(hh, mem, T):
    cols = [c for c in HH_FP_COLS(hh) if c not in FP_SKIP]
    sig = defaultdict(list)
    msig = mem.assign(sg=lambda d: d["member_sex"].astype(str) + d["age_calc"].astype(str) + d["member_relationship"].astype(str)) \
        .groupby("uuid")["sg"].apply(lambda x: "|".join(sorted(x)))
    for r in hh[hh["consented"]].itertuples():
        vals = [s(getattr(r, c, "")) for c in cols]
        if sum(v != "" for v in vals) < 25:
            continue
        sig[(r.enumerator_code, "|".join(vals), msig.get(r.uuid, ""))].append(r.uuid)
    out = []
    for k, ids in sig.items():
        if len(ids) > 1:
            out += [F(u, f"Same answers as {len(ids) - 1} other survey(s) by this enumerator") for u in ids]
    return out


def HH_FP_COLS(hh):
    return [c for c in hh.columns if not c.endswith("_dt") and not c.endswith("_label") and c not in
            ("consented", "title", "home_area", "enumerator_label", "enumerator_code")]


@rule("SO07", "Minor", "household", "Process", "Interview outside working hours")
def so07(hh, mem, T):
    lo, hi = T["working_hours"]
    return [F(r.uuid, f"Interview started at {r.start_dt.hour:02d}:{r.start_dt.minute:02d}") for r in hh.itertuples()
            if pd.notna(r.start_dt) and not (lo <= r.start_dt.hour < hi)]


@rule("SO08", "Minor", "household", "Process", "Very high number of surveys by one enumerator in a day")
def so08(hh, mem, T):
    out = []
    g = hh[hh["start_dt"].notna()].sort_values("start_dt")
    for (code, day), grp in g.groupby(["enumerator_code", "interview_date"]):
        if len(grp) > T["max_surveys_per_enumerator_per_day"]:
            for r in grp.iloc[T["max_surveys_per_enumerator_per_day"]:].itertuples():
                out.append(F(r.uuid, f"{len(grp)} surveys on {day.date()} (limit {T['max_surveys_per_enumerator_per_day']})"))
    return out


@rule("SO09", "Major", "household", "Process", "Overlapping interviews by the same enumerator")
def so09(hh, mem, T):
    out = []
    g = hh[hh["start_dt"].notna() & hh["end_dt"].notna()].sort_values("start_dt")
    for code, grp in g.groupby("enumerator_code"):
        prev = None
        for r in grp.itertuples():
            if prev is not None and r.start_dt < prev.end_dt - pd.Timedelta(minutes=1):
                out.append(F(r.uuid, "Started before this enumerator's previous interview ended"))
            prev = r if prev is None or r.end_dt > prev.end_dt else prev
    return out


@rule("SO11", "Minor", "household", "Location", "Survey outside the enumerator's home area")
def so11(hh, mem, T):
    def k(x):
        return re.sub(r"[^a-z]", "", s(x).split(",")[0].lower())
    return [F(r.uuid, f"Enumerator's area is {r.home_area}; survey was in {r.municipality_label}") for r in hh.itertuples()
            if s(r.home_area) and k(r.home_area) and k(r.home_area) != k(r.municipality_label)
            and r.title == "Enumerator"]


# ================= MEMBER-LEVEL RULES =================
AGE_RANGE = {  # schooling status -> (min age, max age) allowed
    "day_care": (1, 8), "kindergarten": (3, 10), "als": (10, 100), "tvet_year1": (15, 100), "tvet_year2": (15, 100),
    **{f"grade_{g}": (g + 3, g + 14) for g in range(1, 13)},
    **{f"college_{o}": (15, 100) for o in ("1st_year", "2nd_year", "3rd_year", "4th_year", "5th_year")},
}


@rule("MB01", "Critical", "member", "Demographics", "Date of birth missing, in the future or implausible")
def mb01(hh, mem, T):
    out = []
    for r in mem.itertuples():
        if pd.isna(r.dob):
            out.append(F(r.uuid, "Date of birth missing", r.member_index))
        elif r.dob > r.interview_date or (pd.notna(r.age_calc) and r.age_calc > 110):
            out.append(F(r.uuid, f"Date of birth gives age {r.age_calc:.0f}", r.member_index))
    return out


@rule("MB02", "Major", "member", "Demographics", "Recorded age differs from age calculated from date of birth")
def mb02(hh, mem, T):
    return [F(r.uuid, f"Age {r.member_age:.0f} recorded vs {r.age_calc:.0f} from DOB", r.member_index) for r in mem.itertuples()
            if pd.notna(r.member_age) and pd.notna(r.age_calc) and abs(r.member_age - r.age_calc) > 1]


@rule("MB03", "Major", "member", "Education", "Age does not fit the grade / schooling level")
def mb03(hh, mem, T):
    out = []
    for r in mem.itertuples():
        st = s(r.member_schooling_status)
        if st in AGE_RANGE and pd.notna(r.age_calc):
            lo, hi = AGE_RANGE[st]
            if not (lo <= r.age_calc <= hi):
                out.append(F(r.uuid, f"Age {r.age_calc:.0f} is unusual for '{st}'", r.member_index))
        if st == "not_yet_school_age" and pd.notna(r.age_calc) and r.age_calc >= 7:
            out.append(F(r.uuid, f"Age {r.age_calc:.0f} but 'not yet school age'", r.member_index))
    return out


@rule("MB04", "Major", "member", "Education", "Education attainment inconsistent with schooling status or age")
def mb04(hh, mem, T):
    out = []
    for r in mem.itertuples():
        st, ea = s(r.member_schooling_status), s(r.member_educ_attainment)
        if st == "never_attended" and ea not in ("", "no_formal"):
            out.append(F(r.uuid, f"Never attended school but attainment is '{ea}'", r.member_index))
        if st == "completed_schooling" and ea in ("no_formal", "not_applicable"):
            out.append(F(r.uuid, "Completed schooling but attainment is 'no formal education'", r.member_index))
        if ea in ("jhs_grad", "shs_grad", "tech_voc_grad", "college_undergrad", "college_grad", "postgrad") \
                and pd.notna(r.age_calc) and r.age_calc < 12:
            out.append(F(r.uuid, f"Age {r.age_calc:.0f} but attainment is '{ea}'", r.member_index))
    return out


@rule("MB05", "Major", "member", "Employment", "Child with occupation or employment")
def mb05(hh, mem, T):
    out = []
    for r in mem.itertuples():
        if pd.notna(r.age_calc) and r.age_calc < 15:
            if s(r.member_occupation) not in ("", "not_applicable") or s(r.member_employment_status) not in ("", "not_applicable", "student"):
                out.append(F(r.uuid, f"Age {r.age_calc:.0f} but occupation/employment recorded", r.member_index))
    return out


@rule("MB06", "Major", "member", "Employment", "Employment status inconsistent with age or schooling")
def mb06(hh, mem, T):
    out = []
    for r in mem.itertuples():
        es, st = s(r.member_employment_status), s(r.member_schooling_status)
        if es == "student" and st in ("out_of_school", "never_attended", "completed_schooling"):
            out.append(F(r.uuid, f"Employment 'student' but schooling is '{st}'", r.member_index))
        if es == "retired" and pd.notna(r.age_calc) and r.age_calc < 40:
            out.append(F(r.uuid, f"Age {r.age_calc:.0f} but 'retired'", r.member_index))
        if s(r.member_occupation) == "other_occ" and not s(r.member_occupation_other):
            out.append(F(r.uuid, "Occupation 'Other' without a specification", r.member_index))
    return out


@rule("MB07", "Critical", "member", "Demographics", "Pregnant/lactating status impossible for sex or age")
def mb07(hh, mem, T):
    out = []
    for r in mem.itertuples():
        p = s(r.member_plw_status)
        if p not in ("", "none"):
            if s(r.member_sex) == "male":
                out.append(F(r.uuid, "Male member recorded as pregnant/lactating", r.member_index))
            elif pd.notna(r.age_calc) and (r.age_calc < 12 or r.age_calc > 55):
                out.append(F(r.uuid, f"Age {r.age_calc:.0f} recorded as pregnant/lactating", r.member_index))
    return out


@rule("MB08", "Major", "member", "Demographics", "Civil status impossible for age")
def mb08(hh, mem, T):
    out = []
    ever = {"married", "living_in", "separated", "divorced", "annulled", "widowed"}
    for r in mem.itertuples():
        if s(r.member_civil_status) in ever and pd.notna(r.age_calc) and r.age_calc < 15:
            out.append(F(r.uuid, f"Age {r.age_calc:.0f} but civil status '{r.member_civil_status}'", r.member_index))
        if s(r.member_relationship) == "spouse" and s(r.member_civil_status) == "single":
            out.append(F(r.uuid, "Spouse recorded with civil status 'single'", r.member_index))
    return out


@rule("MB09", "Major", "member", "Demographics", "Relationship inconsistent with sex")
def mb09(hh, mem, T):
    out = []
    for r in mem.itertuples():
        if (s(r.member_relationship) == "step_father" and s(r.member_sex) == "female") or \
                (s(r.member_relationship) == "step_mother" and s(r.member_sex) == "male"):
            out.append(F(r.uuid, f"'{r.member_relationship}' with sex '{r.member_sex}'", r.member_index))
    return out


@rule("MB10", "Major", "member", "Demographics", "Relationship inconsistent with age gap to the family head")
def mb10(hh, mem, T):
    heads = mem[mem["member_relationship"] == "hh_head"].drop_duplicates("uuid").set_index("uuid")["age_calc"]
    out = []
    for r in mem.itertuples():
        ha = heads.get(r.uuid, np.nan)
        if pd.isna(ha) or pd.isna(r.age_calc):
            continue
        rel, gap = s(r.member_relationship), ha - r.age_calc
        if rel in ("son_daughter", "foster_child", "adopted_child", "stepson_stepdaughter") and gap < 12:
            out.append(F(r.uuid, f"Child is only {gap:.0f} years younger than the head (head {ha:.0f}, member {r.age_calc:.0f})", r.member_index))
        if rel in ("parent", "step_father", "step_mother") and -gap < 12:
            out.append(F(r.uuid, f"Parent is only {-gap:.0f} years older than the head", r.member_index))
        if rel == "grandchild" and gap < 24:
            out.append(F(r.uuid, f"Grandchild is only {gap:.0f} years younger than the head", r.member_index))
        if rel == "grandparent" and -gap < 24:
            out.append(F(r.uuid, f"Grandparent is only {-gap:.0f} years older than the head", r.member_index))
        if rel == "spouse" and abs(gap) > 35:
            out.append(F(r.uuid, f"Spouse age gap of {abs(gap):.0f} years", r.member_index))
    return out


@rule("MB11", "Major", "member", "Demographics", "Family head is a minor")
def mb11(hh, mem, T):
    return [F(r.uuid, f"Family head age {r.age_calc:.0f}", r.member_index) for r in mem.itertuples()
            if s(r.member_relationship) == "hh_head" and pd.notna(r.age_calc) and r.age_calc < 18]


@rule("MB12", "Major", "member", "Demographics", "Disability answers inconsistent")
def mb12(hh, mem, T):
    out = []
    for r in mem.itertuples():
        t = toks(r.member_special_status)
        if "pwd" in t and not s(r.member_disability_type):
            out.append(F(r.uuid, "PWD selected but disability type missing", r.member_index))
        if "pwd" not in t and s(r.member_disability_type):
            out.append(F(r.uuid, "Disability type recorded but PWD not selected", r.member_index))
    return out


@rule("MB13", "Major", "member", "Demographics", "Leadership roles inconsistent with age or 'None'")
def mb13(hh, mem, T):
    adult_roles = {"barangay_official", "bhw", "bns", "ipmr", "tribal_leader", "council_of_elders"}
    out = []
    for r in mem.itertuples():
        t = toks(r.member_leadership_role)
        if pd.notna(r.age_calc) and r.age_calc < 18 and (t & adult_roles):
            out.append(F(r.uuid, f"Age {r.age_calc:.0f} holding an adult leadership role", r.member_index))
    return out


@rule("MB14", "Major", "member", "Education", "Learner answers inconsistent with schooling status")
def mb14(hh, mem, T):
    out = []
    active = set(AGE_RANGE) - {"als"}
    for r in mem.itertuples():
        st, att, dr = s(r.member_schooling_status), s(r.attending_regularly), s(r.dropout_risk)
        if st in active and att == "0":
            out.append(F(r.uuid, f"Enrolled ('{st}') but 'not currently attending'", r.member_index))
        if st in ("out_of_school", "never_attended") and att not in ("", "0"):
            out.append(F(r.uuid, f"'{st}' but attendance answer is {att}", r.member_index))
        if dr == "4" and att in ("0", "1"):
            out.append(F(r.uuid, "Dropout 'very unlikely' but rarely/not attending", r.member_index))
    return out


@rule("MB15", "Major", "member", "Education", "Scholarship answers inconsistent")
def mb15(hh, mem, T):
    out = []
    for r in mem.itertuples():
        if s(r.has_scholarship) == "1" and not s(r.scholarship_provider):
            out.append(F(r.uuid, "Scholarship = Yes but no provider", r.member_index))
        if s(r.has_scholarship) == "0" and s(r.scholarship_provider):
            out.append(F(r.uuid, "Scholarship = No but a provider is recorded", r.member_index))
    return out


@rule("MB16", "Major", "member", "Demographics", "Duplicate member names or same birthday for many members")
def mb16(hh, mem, T):
    out = []
    for u, g in mem.groupby("uuid"):
        names = [" ".join(norm_name(x)) for x in g["member_full_name"]]
        for i, n in enumerate(names):
            if n and names.count(n) > 1 and names.index(n) == i:
                out.append(F(u, "Duplicate member names in the roster", int(g.iloc[i]["member_index"])))
        dobs = g["dob"].dropna()
        if len(dobs) and dobs.value_counts().iloc[0] >= 4:
            out.append(F(u, f"{dobs.value_counts().iloc[0]} members share the same date of birth"))
    return out


@rule("MB17", "Minor", "member", "Demographics", "Invalid or placeholder member name")
def mb17(hh, mem, T):
    bad = {"na", "n/a", "none", "test", "xxx", "unknown", "asdf"}
    return [F(r.uuid, "Member name is blank, too short or a placeholder", r.member_index) for r in mem.itertuples()
            if len(s(r.member_full_name)) < 3 or s(r.member_full_name).lower() in bad or re.search(r"\d", s(r.member_full_name))]


@rule("MB18", "Major", "member", "Nutrition", "Child nutrition answer recorded for a child aged 6 or above")
def mb18(hh, mem, T):
    return [F(r.uuid, f"Age {r.age_calc:.0f} but child nutrition status recorded", r.member_index) for r in mem.itertuples()
            if s(r.member_nutrition_status) and pd.notna(r.age_calc) and r.age_calc >= 6]


@rule("MB19", "Major", "member", "Demographics", "'Not in same ICC/IP group' without a specification")
def mb19(hh, mem, T):
    return [F(r.uuid, "Answered 'No, specify' but nothing specified", r.member_index) for r in mem.itertuples()
            if s(r.member_same_icc) == "0" and not s(r.member_icc_specify)]



# ================= NEW: names, free text, contacts, dates, multi-select, Section 9 =================
NAME_OK = re.compile(r"^[A-Za-zÀ-ÿñÑ .,'\-]+$")


def name_issues(v):
    """Check 'Last Name, First Name, Middle Name' (e.g. Dela Cruz, Juan, Santos). Returns [(severity, message)]."""
    v = s(v)
    if not v:
        return []
    out = []
    if not NAME_OK.match(v):
        out.append(("Major", "Name contains digits or symbols"))
    commas = v.count(",")
    parts = [p.strip() for p in v.split(",")]
    if commas == 0:
        out.append(("Major", "Not in 'Last Name, First Name, Middle Name' format (no commas)"))
    else:
        if any(p == "" for p in parts):
            out.append(("Major", "Empty part in the name (double or trailing comma)"))
        if commas == 1:
            out.append(("Minor", "Middle name part missing (expected 'Last, First, Middle')"))
        if commas > 2:
            out.append(("Minor", "More than 3 comma-separated parts"))
        if re.search(r",\S", v):
            out.append(("Minor", "Missing space after a comma"))
        if parts[0] and len(parts[0]) < 2 or (len(parts) > 1 and 0 < len(parts[1]) < 2):
            out.append(("Major", "Last name or first name is a single letter"))
    letters = re.sub(r"[^A-Za-zÀ-ÿñÑ]", "", v)
    if len(letters) >= 4 and (letters.isupper() or letters.islower()):
        out.append(("Minor", "Name is all capitals or all lowercase (use Title Case)"))
    return out


@rule("MB20", "Minor", "member", "Open text", "Member name not in the required format (Last Name, First Name, Middle Name)")
def mb20(hh, mem, T):
    return [F(r.uuid, msg, r.member_index, sev) for r in mem.itertuples() for sev, msg in name_issues(r.member_full_name)]


@rule("HH19", "Minor", "household", "Open text", "Family head / respondent name not in the required format")
def hh19(hh, mem, T):
    out = []
    for r in hh[hh["consented"]].itertuples():
        for fld in ("hh_head_name", "respondent_name"):
            for sev, msg in name_issues(getattr(r, fld, "")):
                out.append(F(r.uuid, f"{fld}: {msg}", None, sev))
    return out


TEST_WORDS = {"test", "testing", "tester", "asdf", "asdfg", "asdfgh", "asdfghjkl", "qwerty", "qwe", "qwert", "zxcv", "xxx", "xxxx",
              "xx", "aaa", "aaaa", "sample", "dummy", "lorem", "ipsum", "abc", "abcd", "abcde", "sdfsdf", "hjkl", "jkl", "wala",
              "sdf", "dfg", "fgh", "lalala", "blabla", "bla", "nothing", "unknown", "noname", "xyz"}
KEYBOARD = ["qwer", "wert", "erty", "rtyu", "tyui", "yuio", "uiop", "asdf", "sdfg", "dfgh", "fghj", "ghjk", "hjkl", "zxcv", "xcvb",
            "cvbn", "vbnm", "qaz", "wsx", "edc", "1234", "abcd"]
FILLER = {"ok", "okay", "yes", "no", "y", "n", "na", "n/a", "none", "wala", "basta", "hindi", "oo", "-", ".", "..", "...", "x", "nil", "null"}
NAME_FIELDS = ("hh_head_name", "respondent_name", "member_full_name")
OPTIONAL_TEXT = ("member_remarks", "enumerator_remarks")            # 'none' / 'n/a' is an acceptable answer here
SPECIFY_FIELDS = ("member_icc_specify", "member_occupation_other", "referral_reason_other", "agri_commodities", "icc_ip_group")
FREE_TEXT_HH = ["hh_head_name", "respondent_name", "icc_ip_group", "agri_commodities", "referral_reason_other", "enumerator_remarks"]
FREE_TEXT_MEM = ["member_full_name", "member_icc_specify", "member_occupation_other", "member_remarks", "school_name"]


def gibberish_reason(text, field):
    t = s(text)
    low = t.lower()
    words = re.findall(r"[a-zñ0-9]+", low)
    letters = re.sub(r"[^a-zñ]", "", low)
    if not t:
        return None
    if field in OPTIONAL_TEXT and low in FILLER:
        return None
    if field in NAME_FIELDS and low in FILLER:
        return "no real name (placeholder)"
    if any(w in TEST_WORDS for w in words) and (field in NAME_FIELDS or len(words) <= 3):
        return "test / placeholder entry"
    if len(letters) >= 4 and any(k in letters for k in KEYBOARD):
        return "keyboard pattern (e.g. asdf, qwerty)"
    if re.search(r"(.)\1{3,}", low):
        return "same character repeated"
    if len(letters) >= 6 and re.search(r"([a-zñ]{2,4})\1{2,}", letters):
        return "repeating pattern (e.g. hahaha)"
    if len(letters) >= 5 and sum(ch in "aeiouy" for ch in letters) / len(letters) < 0.1:
        return "no vowels (keyboard smash)"
    if re.search(r"[^aeiouy\W\d_]{6,}", low):
        return "long run of consonants (keyboard smash)"
    if len(words) >= 5 and Counter(words).most_common(1)[0][1] / len(words) > 0.5:
        return "the same word repeated"
    return None


@rule("TX01", "Major", "any", "Open text", "Gibberish, keyboard smash or test entry in a text answer")
def tx01(hh, mem, T):
    out = []
    for r in hh.to_dict("records"):
        for fld in FREE_TEXT_HH:
            why = gibberish_reason(r.get(fld), fld)
            if why:
                out.append({**F(r["uuid"], f"{fld}: {why}", None, "Major" if fld in NAME_FIELDS else "Minor"), "field": fld, "value": s(r.get(fld))[:60]})
    for r in mem.to_dict("records"):
        for fld in FREE_TEXT_MEM:
            why = gibberish_reason(r.get(fld), fld)
            if why:
                out.append({**F(r["uuid"], f"{fld}: {why}", r["member_index"], "Major" if fld in NAME_FIELDS else "Minor"), "field": fld, "value": s(r.get(fld))[:60]})
    return out


@rule("TX02", "Minor", "household", "Open text", "Identical free-text copied across many surveys, or repetitive text")
def tx02(hh, mem, T):
    out = []
    for fld in ("enumerator_remarks", "referral_reason_other"):
        if fld not in hh.columns:
            continue
        g = hh[hh[fld].astype(str).str.len() >= 15]
        per_enum = g.groupby("enumerator_code").size()
        for (code, txt), grp in g.groupby(["enumerator_code", g[fld].astype(str).str.strip().str.lower()]):
            if len(grp) >= 6 and len(grp) / per_enum[code] >= 0.4:
                out += [{**F(u, f"{fld}: identical text used in {len(grp)} surveys by this enumerator"), "field": fld,
                         "value": s(grp.iloc[0][fld])[:60]} for u in grp["uuid"]]
    if "member_remarks" in mem.columns:
        g = mem[mem["member_remarks"].astype(str).str.len() >= 15]
        for (code, txt), grp in g.groupby([g["enumerator_code"], g["member_remarks"].astype(str).str.strip().str.lower()]):
            if len(grp) >= 6:
                out += [{**F(r.uuid, f"member_remarks: identical text used {len(grp)} times by this enumerator", r.member_index),
                         "field": "member_remarks", "value": s(r.member_remarks)[:60]} for r in grp.itertuples()]
    return out


@rule("TX03", "Minor", "any", "Open text", "Text answer is a non-answer, too short, or not an answer (URL / number / question)")
def tx03(hh, mem, T):
    out = []

    def check(rec, fld, uid, mi):
        txt = s(rec.get(fld))
        if not txt:
            return
        low = txt.lower()
        if fld in OPTIONAL_TEXT and low in FILLER:
            return
        why = None
        if fld in SPECIFY_FIELDS or fld == "school_name":
            if low in FILLER or len(txt) < 3 and fld != "icc_ip_group":
                why = "filler or too short to be a real answer"
        if not why and re.search(r"https?://|www\.|@\w+\.\w+", low):
            why = "contains a web address or e-mail instead of an answer"
        if not why and re.search(r"\d{7,}", txt) and fld not in ("hh_head_contact", "respondent_contact", "hh_id"):
            why = "contains a long number (phone/ID) instead of an answer"
        if not why and txt.endswith("?"):
            why = "is a question, not an answer"
        if not why and re.sub(r"[\W\d_]", "", txt) == "" and fld not in ("hh_head_contact", "respondent_contact", "hh_id"):
            why = "has no letters"
        if why:
            out.append({**F(uid, f"{fld}: {why}", mi), "field": fld, "value": txt[:60]})
    for r in hh.to_dict("records"):
        for fld in FREE_TEXT_HH:
            check(r, fld, r["uuid"], None)
    for r in mem.to_dict("records"):
        for fld in FREE_TEXT_MEM:
            check(r, fld, r["uuid"], r["member_index"])
    return out


def _phone(v):
    return re.sub(r"[\s\-()]", "", s(v))


@rule("CT01", "Minor", "household", "Contact", "Invalid or placeholder contact number")
def ct01(hh, mem, T):
    out = []
    for r in hh.itertuples():
        for fld in ("hh_head_contact", "respondent_contact"):
            v = _phone(getattr(r, fld, ""))
            if not v:
                continue
            if not re.fullmatch(r"(09\d{9}|\+?639\d{9})", v):
                out.append({**F(r.uuid, f"{fld}: not a valid Philippine mobile number"), "field": fld, "value": v})
            elif len(set(v[-9:])) <= 2 or v[-9:] in ("123456789", "987654321"):
                out.append({**F(r.uuid, f"{fld}: looks like a placeholder number"), "field": fld, "value": v})
    return out


@rule("CT02", "Minor", "household", "Contact", "Same contact number used by many different families")
def ct02(hh, mem, T):
    rows = []
    for r in hh.itertuples():
        for fld in ("hh_head_contact", "respondent_contact"):
            v = _phone(getattr(r, fld, ""))
            if v:
                rows.append((v, r.uuid, r.hh_id, fld))
    df = pd.DataFrame(rows, columns=["v", "uuid", "hh", "fld"])
    out = []
    if df.empty:
        return out
    for v, g in df.groupby("v"):
        if g["hh"].nunique() >= 4:
            out += [{**F(u, f"Contact number shared by {g['hh'].nunique()} families"), "field": fl, "value": v} for u, fl in zip(g["uuid"], g["fld"])]
    return out


@rule("HH20", "Major", "household", "Process", "Impossible or out-of-range interview dates/times")
def hh20(hh, mem, T):
    out = []
    start = pd.Timestamp(T.get("project_start_date", "2026-01-01"))
    for r in hh.itertuples():
        if pd.notna(r.interview_date) and r.interview_date < start:
            out.append(F(r.uuid, f"Interview date {r.interview_date.date()} is before the project start ({start.date()})"))
        if pd.notna(r.duration_min) and r.duration_min < 0:
            out.append(F(r.uuid, "End time is earlier than start time (device clock error)"))
    return out


@rule("HH21", "Minor", "household", "Demographics", "Unusually large household")
def hh21(hh, mem, T):
    return [F(r.uuid, f"{r.n_members} members recorded", None, "Major" if r.n_members > 20 else "Minor")
            for r in hh.itertuples() if r.n_members > T.get("max_household_size", 12)]


@rule("MB21", "Major", "member", "Multi-select", "'None' selected together with other options (member questions)")
def mb21(hh, mem, T):
    out = []
    for r in mem.itertuples():
        for col, none in (("member_special_status", "none"), ("member_leadership_role", "none")):
            t = toks(getattr(r, col, ""))
            if none in t and len(t) > 1:
                out.append({**F(r.uuid, f"'{none}' selected together with other options in {col}", r.member_index), "field": col,
                            "value": " ".join(sorted(t))})
    return out


EMPLOYED = {"employed_regular", "employed_casual", "self_employed", "unpaid_family_worker", "seasonal"}


@rule("LV12", "Major", "household", "Livelihood", "Members employed but family reports no livelihood (or the reverse)")
def lv12(hh, mem, T):
    out = []
    emp = mem[mem["member_employment_status"].isin(EMPLOYED)].groupby("uuid").size()
    adults = mem[mem["age_calc"] >= 15]
    for r in hh[hh["consented"]].itertuples():
        src = toks(r.livelihood_sources)
        n_emp = int(emp.get(r.uuid, 0))
        if src == {"none_livelihood"} and n_emp > 0:
            out.append(F(r.uuid, f"{n_emp} member(s) employed but livelihood source is 'None'"))
        elif n_emp == 0 and (src & {"wage_employment", "government_employment"}):
            a = adults[adults["uuid"] == r.uuid]
            if len(a) and not a["member_employment_status"].isin(EMPLOYED | {"student"}).any() and a["member_employment_status"].astype(str).ne("").all():
                out.append(F(r.uuid, "Wage/government employment is a livelihood source but no adult is recorded as employed", None, "Minor"))
    return out


PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2}
SUGGEST_MAP = {"suggest_education": "education_prog", "suggest_hapag_asa": "hapag_asa_prog", "suggest_agriculture": "agriculture_prog",
               "suggest_water": "water_prog", "suggest_governance": "governance_prog"}
REASON_FLAG = {"suspicion_undernourished": "flag_child_nutrition", "confirmed_malnutrition": "flag_child_nutrition",
               "dropout_risk": "flag_dropout_risk", "no_education_support": "flag_no_education_support",
               "food_insecurity": "flag_severe_food_insecurity", "disaster_shock": "flag_shock_disaster",
               "no_toilet": "flag_no_toilet", "unsafe_water": "flag_unsafe_water_source"}


@rule("S901", "Minor", "household", "Section 9", "Final family priority is lower than the system-suggested priority")
def s901(hh, mem, T):
    out = []
    for r in hh[hh["consented"]].itertuples():
        fp, sp = PRIORITY_RANK.get(s(getattr(r, "family_priority", "")).lower()), PRIORITY_RANK.get(s(getattr(r, "suggested_priority", "")).lower())
        if fp is not None and sp is not None and fp < sp:
            out.append(F(r.uuid, f"Priority set to '{r.family_priority}' but the system suggested '{r.suggested_priority}'"
                         + ("" if s(getattr(r, "enumerator_remarks", "")) else " and no remarks explain the difference"),
                         None, "Major" if sp - fp >= 2 else "Minor"))
    return out


@rule("S902", "Major", "household", "Section 9", "Urgent flags raised but no immediate referral recorded")
def s902(hh, mem, T):
    return [F(r.uuid, "Urgent flag(s) raised by the system but 'Immediate referral needed' = No")
            for r in hh[hh["consented"]].itertuples()
            if s(getattr(r, "flag_any_urgent", "")) == "1" and s(getattr(r, "immediate_referral_needed", "")) == "0"]


@rule("S903", "Minor", "household", "Section 9", "Referral recorded without any urgent flag or critical/at-risk score")
def s903(hh, mem, T):
    return [F(r.uuid, "Immediate referral = Yes but no urgent flag and the score band is Stable/Thriving")
            for r in hh[hh["consented"]].itertuples()
            if s(getattr(r, "immediate_referral_needed", "")) == "1" and s(getattr(r, "flag_any_urgent", "")) == "0"
            and s(getattr(r, "hds_band", "")) in ("Stable", "Thriving")]


@rule("S904", "Minor", "household", "Section 9", "Recommended programs omit programs the system suggested")
def s904(hh, mem, T):
    out = []
    for r in hh[hh["consented"]].itertuples():
        rec = toks(getattr(r, "recommended_programs", ""))
        if not rec and not s(getattr(r, "recommended_programs", "")):
            continue
        miss = [code for col, code in SUGGEST_MAP.items() if s(getattr(r, col, "")) == "1" and code not in rec]
        if miss:
            out.append(F(r.uuid, "Suggested but not recommended: " + ", ".join(m.replace("_prog", "") for m in miss)))
    return out


@rule("S905", "Major", "household", "Section 9", "Score band or suggested priority does not match the recorded score/flags")
def s905(hh, mem, T):
    out = []
    for r in hh[hh["consented"]].itertuples():
        sc = num(getattr(r, "family_development_score", np.nan))
        band = s(getattr(r, "hds_band", ""))
        if pd.notna(sc) and band:
            exp = "Critical" if sc < 40 else "At Risk" if sc < 60 else "Stable" if sc < 80 else "Thriving"
            if band != exp:
                out.append(F(r.uuid, f"Score {sc:.1f} should be '{exp}' but band is '{band}'"))
        sp, urg = s(getattr(r, "suggested_priority", "")).lower(), s(getattr(r, "flag_any_urgent", ""))
        if sp and band and urg != "":
            exp_p = "high" if (urg == "1" or band == "Critical") else ("medium" if band == "At Risk" else "low")
            if sp != exp_p:
                out.append(F(r.uuid, f"Suggested priority '{sp}' does not follow from band '{band}' and urgent flag {urg}"))
    return out


@rule("S906", "Minor", "household", "Section 9", "Referral reason not supported by the system flags")
def s906(hh, mem, T):
    out = []
    for r in hh[hh["consented"]].itertuples():
        for reason in toks(getattr(r, "referral_reason", "")):
            f = REASON_FLAG.get(reason)
            if f and s(getattr(r, f, "")) == "0":
                out.append(F(r.uuid, f"Referral reason '{reason}' but the system flag '{f}' is not raised"))
    return out


# ================= audit metadata: category, fields shown, recommended action =================
C_LOGIC, C_TEXT, C_OUT, C_MS = ("Logic & Skip Rule Violations", "Open-Text Quality & Gibberish",
                                "Outliers & Data Entry Errors", "Multi-Select Conflicts")
SEV_AUDIT = {"Critical": "High", "Major": "Medium", "Minor": "Low"}
META = {
 "HH01": (C_OUT, ["hh_id"], "Confirm whether the family was interviewed twice or the ID was mistyped; keep one record and correct or delete the duplicate."),
 "HH02": (C_LOGIC, ["informed_consent"], "Consent was not given, so no household data should exist. Remove the data or correct the consent answer after confirming with the enumerator."),
 "HH03": (C_LOGIC, ["member_relationship"], "Every family needs exactly one Family Head. Correct the relationship of the members in the roster."),
 "HH04": (C_LOGIC, ["hh_head_name"], "Make the head's name in Section 1 identical to the head in the roster."),
 "HH05": (C_LOGIC, ["hh_head_gender", "member_sex"], "Correct the head's gender in Section 1 or the head's sex in the roster."),
 "HH06": (C_LOGIC, ["respondent_name", "respondent_relationship", "hh_head_name"], "Correct the respondent's relationship or name so they agree."),
 "HH07": (C_OUT, ["duration_min", "start", "end"], "Interview was too short to ask every question. Call the family to verify the interview took place; consider re-interview."),
 "HH08": (C_OUT, ["duration_min", "start", "end"], "Check for a forgotten 'finish' or a device clock error."),
 "HH09": (C_OUT, ["today", "start"], "Check the device date/time settings and correct the interview date."),
 "HH10": (C_OUT, ["today"], "Remind the enumerator to submit on the day of the interview."),
 "HH11": (C_LOGIC, ["is_ip_family", "icc_ip_group"], "Make the IP family answer and the ICC/IP group agree."),
 "HH12": (C_OUT, ["gps_coordinate"], "GPS is required. Ask the enumerator to revisit/verify the location."),
 "HH13": (C_OUT, ["gps_coordinate"], "Accuracy is poor; verify the location is the family's home."),
 "HH14": (C_OUT, ["gps_coordinate"], "Coordinates are outside the Philippines. Treat the location as invalid and re-capture."),
 "HH15": (C_OUT, ["gps_coordinate"], "The same point was recorded for different families. Verify the interviews really took place at different homes."),
 "HH16": (C_LOGIC, ["hh_size_count", "hh_child_u6_count"], "Household size/child counts do not match the roster. Check whether the roster or the calculation was altered."),
 "HH17": (C_LOGIC, ["member_age"], "A family with only minors needs verification: confirm the roster and the head."),
 "HH18": (C_LOGIC, ["member_relationship"], "Only one member can be the Spouse of the head. Correct the relationships."),
 "HH19": (C_TEXT, ["hh_head_name", "respondent_name"], "Rewrite the name as 'Last Name, First Name, Middle Name' (e.g. Dela Cruz, Juan, Santos), in Title Case."),
 "HH20": (C_OUT, ["today", "start", "end"], "The interview dates/times are impossible. Check the device clock and correct the date."),
 "HH21": (C_OUT, ["hh_size_count"], "Confirm the household size, and that other households were not merged into one roster."),
 "LV01": (C_LOGIC, ["primary_livelihood", "livelihood_sources"], "The primary livelihood must be one of the selected sources. Correct one of the two answers."),
 "LV02": (C_LOGIC, ["livelihood_sources"], "'None' cannot be selected with other sources. Correct the livelihood answer."),
 "LV03": (C_LOGIC, ["monthly_income", "primary_livelihood", "livelihood_sources"], "Income and livelihood disagree. Re-ask the income and livelihood questions."),
 "LV04": (C_OUT, ["monthly_income"], "The income figure is implausible (possible extra zeros or wrong unit). Verify with the family."),
 "LV05": (C_LOGIC, ["monthly_income", "basic_needs_sufficiency", "hh_size_count"], "Income per person and 'basic needs' answer do not fit. Re-ask both questions."),
 "LV06": (C_LOGIC, ["cultivates_farmland", "livelihood_sources", "farm_hectares"], "Farmland answers disagree with the family's livelihood. Correct them."),
 "LV07": (C_OUT, ["farm_hectares"], "Farm size is missing, zero or very large. Verify the area and unit."),
 "LV08": (C_LOGIC, ["market_sold_proportion", "harvest_food_proportion", "harvest_shared_proportion"], "Sold + eaten + shared cannot add up to more than 100%. Re-ask the three questions."),
 "LV09": (C_LOGIC, ["severe_food_insecurity", "basic_needs_sufficiency", "food_insecurity_reason"], "Food-insecurity answers contradict each other. Re-ask."),
 "LV10": (C_LOGIC, ["produces_own_food", "home_produced_food_types"], "Own-food production and the list of food types disagree. Correct."),
 "LV11": (C_LOGIC, ["livestock_raised", "fishing_activity", "livelihood_sources"], "Livestock/fishing was recorded but is not a livelihood source. Confirm and correct."),
 "LV12": (C_LOGIC, ["livelihood_sources", "member_employment_status"], "Members' employment and the family's livelihood sources disagree. Correct both sections."),
 "WS01": (C_LOGIC, ["drinking_water_source", "water_collection_time"], "The water source and the collection time cannot both be true. Re-ask."),
 "WS02": (C_LOGIC, ["drinking_water_source", "water_safety_confidence", "water_access_status"], "Unsafe source but full confidence in water safety. Re-ask the questions."),
 "SO01": (C_MS, [], "'None' cannot be selected together with other options. Correct the multi-select answer."),
 "SO02": (C_MS, ["hh_challenges_top3"], "Only the top 3 challenges should be selected. Remove the extra choices."),
 "SO03": (C_OUT, ["water_access_status", "water_safety_confidence", "basic_needs_sufficiency", "family_nutrition_ability", "family_voice", "leaders_assistance_confidence", "climate_resilience_confidence", "food_from_production_months", "severe_food_insecurity", "toilet_quality"], "Nearly all scale questions have the same answer (straight-lining). Check the enumerator is reading each question and recording the family's real answer."),
 "SO05": (C_OUT, ["hh_head_name"], "Another submission has the same head, barangay and birth date. Likely a duplicate interview; keep one."),
 "SO06": (C_OUT, ["hh_head_name"], "This survey has the same answers as another by the same enumerator (copy-paste). Verify both interviews took place."),
 "SO07": (C_OUT, ["start"], "Interview was started outside normal hours. Verify it took place."),
 "SO08": (C_OUT, ["today"], "Unusually many surveys in a day. Check quality and that interviews were not rushed."),
 "SO09": (C_OUT, ["start", "end"], "Started before the same enumerator's previous interview ended. Verify both interviews took place."),
 "SO11": (C_OUT, ["municipality"], "Survey is outside the enumerator's home area. Confirm the deployment was authorized."),
 "MB01": (C_OUT, ["member_dob"], "Date of birth is missing, in the future or implausible. Correct it."),
 "MB02": (C_LOGIC, ["member_age", "member_dob"], "Recorded age and date of birth disagree. Correct whichever is wrong."),
 "MB03": (C_LOGIC, ["member_schooling_status", "member_age"], "The age is unusual for this grade/schooling level. Verify age and grade."),
 "MB04": (C_LOGIC, ["member_schooling_status", "member_educ_attainment"], "Education attainment contradicts the schooling status or age. Correct."),
 "MB05": (C_LOGIC, ["member_age", "member_occupation", "member_employment_status"], "Occupation/employment recorded for a child under 15. Correct the age or remove the entry."),
 "MB06": (C_LOGIC, ["member_employment_status", "member_schooling_status", "member_occupation"], "Employment status disagrees with age/schooling/occupation. Correct."),
 "MB07": (C_LOGIC, ["member_sex", "member_plw_status", "member_age"], "Pregnant/lactating status is impossible for this sex/age. Correct the sex, age or status."),
 "MB08": (C_LOGIC, ["member_civil_status", "member_age", "member_relationship"], "Civil status is impossible for the age/relationship. Correct."),
 "MB09": (C_LOGIC, ["member_relationship", "member_sex"], "Relationship and sex do not fit (step-father/step-mother). Correct."),
 "MB10": (C_LOGIC, ["member_relationship", "member_age"], "The age gap to the head does not fit the relationship (e.g. child too close in age). Verify ages and relationships."),
 "MB11": (C_OUT, ["member_age", "member_relationship"], "The Family Head is under 18. Verify who the head is and the age."),
 "MB12": (C_LOGIC, ["member_special_status", "member_disability_type"], "PWD status and disability type disagree. Correct."),
 "MB13": (C_LOGIC, ["member_leadership_role", "member_age"], "A minor is recorded in an adult leadership role. Verify age and role."),
 "MB14": (C_LOGIC, ["member_schooling_status", "attending_regularly", "dropout_risk"], "Attendance/dropout answers contradict the schooling status. Re-ask."),
 "MB15": (C_LOGIC, ["has_scholarship", "scholarship_provider"], "Scholarship answer and provider disagree. Correct."),
 "MB16": (C_OUT, ["member_full_name", "member_dob"], "Duplicate names or the same birth date for many members: check for copy-paste in the roster."),
 "MB17": (C_TEXT, ["member_full_name"], "The name is blank, too short, contains digits or is a placeholder. Re-enter the real name."),
 "MB18": (C_LOGIC, ["member_nutrition_status", "member_age"], "Child nutrition status applies only to children under 6. Correct the age or remove the answer."),
 "MB19": (C_LOGIC, ["member_same_icc", "member_icc_specify"], "'No, specify' was chosen but nothing was specified. Add the ICC/IP group."),
 "MB20": (C_TEXT, ["member_full_name"], "Rewrite the name as 'Last Name, First Name, Middle Name' (e.g. Dela Cruz, Juan, Santos), in Title Case."),
 "MB21": (C_MS, [], "'None' cannot be selected together with other options. Correct the multi-select answer."),
 "TX01": (C_TEXT, [], "The text looks like a test entry, keyboard smash or placeholder. Replace it with the real answer."),
 "TX02": (C_TEXT, [], "The same text is repeated across surveys or within the answer. Check for copy-paste and replace with specific information."),
 "TX03": (C_TEXT, [], "The text is not a real answer (filler, link, number, question). Replace it with the real answer."),
 "CT01": (C_OUT, ["hh_head_contact", "respondent_contact"], "Use an 11-digit mobile number starting with 09 (or +639). Re-enter it, or leave blank if there is none."),
 "CT02": (C_OUT, ["hh_head_contact", "respondent_contact"], "The same number appears for many families. Confirm it belongs to this family (not the enumerator's number)."),
 "S901": (C_LOGIC, ["family_priority", "suggested_priority", "enumerator_remarks"], "Priority is lower than the system suggestion. Confirm the decision and record the reason in the remarks."),
 "S902": (C_LOGIC, ["immediate_referral_needed", "flag_any_urgent", "flag_summary_text"], "Urgent flags exist but no referral was made. Review the flags and refer, or document why not."),
 "S903": (C_LOGIC, ["immediate_referral_needed", "flag_any_urgent", "hds_band"], "Referral recorded without supporting flags. Confirm the reason."),
 "S904": (C_LOGIC, ["recommended_programs", "suggested_programs_text"], "Add the suggested programs or record why they were not recommended."),
 "S905": (C_LOGIC, ["family_development_score", "hds_band", "suggested_priority", "flag_any_urgent"], "The score band or suggested priority does not follow from the score/flags. The calculation may have been altered; escalate to M&E."),
 "S906": (C_LOGIC, ["referral_reason", "flag_summary_text"], "A referral reason is not supported by the data. Verify the reason or the underlying answers."),
 "SKIP01": (C_LOGIC, [], "An answer exists for a question that should have been skipped."),
 "SKIP02": (C_LOGIC, [], "A required question that applies is blank."),
}


def _fmt(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d %H:%M") if v.hour or v.minute else v.strftime("%Y-%m-%d")
    return str(v)


def _enrich(flags, hh, mem, labels):
    hh_idx = {r["uuid"]: r for r in hh.to_dict("records")}
    mem_idx = {(r["uuid"], r["member_index"]): r for r in mem.to_dict("records")}
    fields, values, questions, actions, cats = [], [], [], [], []
    for f in flags.to_dict("records"):
        cat, meta_fields, action = META.get(f["rule_id"], (C_LOGIC, [], ""))
        fld = f.get("field")
        flist = [x for x in str(fld).split(",") if x and x != "nan"] if isinstance(fld, str) else meta_fields
        base = hh_idx.get(f["uuid"], {})
        mi = f.get("member_index")
        row = {**base, **mem_idx.get((f["uuid"], mi), {})} if pd.notna(mi) else base
        val = f.get("value")
        if not isinstance(val, str) or val == "" and flist:
            parts = [(x, _fmt(row.get(x))) for x in flist]
            val = parts[0][1] if len(parts) == 1 else "; ".join(f"{x}={v}" for x, v in parts if v != "")
        fields.append(", ".join(flist))
        values.append(str(val)[:140])
        questions.append(" | ".join(f"{x} - {labels.get(x, '')}".strip(" -") for x in flist)[:200])
        a = f.get("action")
        actions.append(a if isinstance(a, str) and a else action)
        cats.append(cat)
    flags["field"], flags["value"], flags["question"], flags["action"], flags["audit_category"] = fields, values, questions, actions, cats
    flags["audit_severity"] = flags["severity"].map(SEV_AUDIT)
    return flags


CTX = ["hh_id", "kobo_id", "interview_date", "enumerator_code", "enumerator_label", "title", "municipality_label", "barangay_label"]
FLAG_COLS = ["uuid", "member_index", "detail", "rule_id", "severity", "level", "category", "rule", "field", "value", "action"]


# ================= runner =================
def run_checks(hh, mem, cfg=None, labels=None, xlsx_path=None):
    """Return (flags DataFrame, per-survey integrity DataFrame, rule catalogue DataFrame)."""
    T = {**DEFAULTS, **((cfg or {}).get("thresholds") or {})}
    labels = labels or {}
    cat = pd.DataFrame([{"id": r["id"], "severity": r["severity"], "level": r["level"], "category": r["category"], "title": r["title"]}
                        for r in RULES] + [{"id": "SKIP01", "severity": "Major", "level": "any", "category": "Skip logic",
                                            "title": "Answer recorded for a question that should have been skipped (tests every skip rule in the form)"},
                                           {"id": "SKIP02", "severity": "Major", "level": "any", "category": "Skip logic",
                                            "title": "Required question left blank although it applies"}])
    empty_cols = FLAG_COLS + CTX + ["question", "audit_category", "audit_severity"]
    if hh.empty:
        flags = pd.DataFrame(columns=empty_cols)
        integ = pd.DataFrame(columns=["uuid"] + CTX + ["Critical", "Major", "Minor", "integrity_score", "clean"])
        return flags, integ, cat
    if "kobo_id" not in hh.columns:
        hh = hh.assign(kobo_id=hh["uuid"])
    rows = []
    for rl in RULES:
        try:
            res = rl["fn"](hh, mem, T)
        except Exception as exc:  # one broken rule must never stop the dashboard
            res = []
            print(f"[integrity] rule {rl['id']} failed: {exc}")
        for f in res:
            f = dict(f)
            sev = f.pop("sev", None) or rl["severity"]
            rows.append({**f, "rule_id": rl["id"], "severity": sev, "level": rl["level"], "category": rl["category"], "rule": rl["title"]})
    skip_info = None
    if xlsx_path:
        try:
            from .skiplogic import audit_skip_logic
            sk, skip_info = audit_skip_logic(hh, mem, xlsx_path)
            rows += sk
        except Exception as exc:
            print(f"[integrity] skip-logic audit failed: {exc}")
    flags = pd.DataFrame(rows)
    for c in FLAG_COLS:
        if c not in flags.columns:
            flags[c] = np.nan
    flags = flags[FLAG_COLS].copy()
    flags["uuid"] = flags["uuid"].astype(object)
    flags = flags.merge(hh[["uuid"] + CTX], on="uuid", how="left")
    flags = _enrich(flags, hh, mem, labels)
    flags.attrs["skip_info"] = skip_info

    w = T["severity_weights"]
    pen = flags.assign(p=flags["severity"].map(w)).groupby("uuid")["p"].sum()
    cnt = flags.pivot_table(index="uuid", columns="severity", values="rule_id", aggfunc="count", fill_value=0)
    integ = hh[["uuid"] + CTX].copy()
    for sev in ("Critical", "Major", "Minor"):
        integ[sev] = integ["uuid"].map(cnt[sev] if sev in cnt else pd.Series(dtype=int)).fillna(0).astype(int)
    integ["integrity_score"] = (100 - integ["uuid"].map(pen).fillna(0)).clip(lower=0)
    integ["clean"] = (integ["Critical"] == 0) & (integ["Major"] == 0)
    return flags, integ, cat
