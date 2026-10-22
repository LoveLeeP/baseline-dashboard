"""Synthetic Kobo-style submissions (same key structure as the real API) used to test and demo the dashboard.
Deliberate errors are planted and returned as `truth` so the accuracy checker can be verified."""
import random
import re
from datetime import date, datetime, timedelta, timezone

import openpyxl

PH = timezone(timedelta(hours=8))
TODAY = date(2026, 10, 18)
MUNI_GPS = {"sablayan": (12.83, 120.77), "brookes_point": (8.77, 117.84), "valderrama": (11.02, 122.07),
            "binalbagan": (10.20, 122.86), "calinog": (11.12, 122.52), "kabasalan": (7.78, 122.76),
            "titay": (7.80, 122.53), "alabel": (6.10, 125.29), "columbio": (6.70, 124.88), "maluso": (6.55, 121.88)}
FIRST = ["Maria", "Juan", "Ana", "Pedro", "Rosa", "Jose", "Luz", "Carlo", "Liza", "Mario", "Nena", "Ramon", "Gina", "Ben"]
LAST = ["Santos", "Reyes", "Cruz", "Bautista", "Garcia", "Mendoza", "Flores", "Ramos", "Aquino", "Dela Cruz", "Tadi"]
BAD_ENUMS = {"E004", "E019", "E030", "E040"}   # enumerators with a much higher error rate


def _norm(s):
    return re.sub(r"[^a-z]", "", str(s).split(",")[0].lower())


def _muni_barangays(xlsx):
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    rows = list(wb["choices"].iter_rows(values_only=True))
    h = list(rows[0])
    out = {}
    for r in rows[1:]:
        if r[0] == "program_barangay":
            out.setdefault(r[h.index("municipality")], []).append(r[1])
    return out


def _name(rng):
    return f"{rng.choice(LAST)}, {rng.choice(FIRST)}, {rng.choice(LAST)}"


def _dob(age, on, rng):
    return (on - timedelta(days=int(age * 365.25 + rng.randint(0, 360)))).isoformat()


def _schooling(age):
    if age < 3: return "not_yet_school_age"
    if age < 5: return "day_care"
    if age == 5: return "kindergarten"
    if age <= 11: return f"grade_{age - 5}"
    if age <= 15: return f"grade_{age - 5}"
    if age <= 17: return f"grade_{age - 5}"
    return "completed_schooling"


def _member(rel, sex, age, on, rng, name=None):
    st = _schooling(age)
    m = {"member_full_name": name or _name(rng), "member_relationship": rel, "member_sex": sex,
         "member_dob": _dob(age, on, rng), "member_age": str(age), "member_schooling_status": st,
         "member_civil_status": "single" if age < 18 else ("married" if rel in ("hh_head", "spouse") else "single"),
         "member_special_status": "none", "member_leadership_role": "none" if age >= 15 else ""}
    if age < 6:
        m["member_nutrition_status"] = "none_identified"
    if sex == "female" and age <= 60:
        m["member_plw_status"] = "none"
    m["member_same_icc"] = "1"
    if st == "completed_schooling":
        m["member_educ_attainment"] = rng.choice(["elem_grad", "jhs_grad", "shs_grad", "college_grad"])
        if age < 21 and m["member_educ_attainment"] == "college_grad":   # nobody finishes college at 18-20
            m["member_educ_attainment"] = "shs_grad"
    if st.startswith("grade_") or st in ("kindergarten", "day_care"):
        m.update({"attending_regularly": rng.choice(["4", "4", "3"]), "dropout_risk": rng.choice(["4", "3"]),
                  "has_scholarship": "0"})
    m["member_is_child_u6"] = "1" if age < 6 else "0"
    m["member_is_infant_u2"] = "1" if age < 2 else "0"
    m["member_is_learner"] = "0" if st in ("not_yet_school_age", "completed_schooling") else "1"
    if m["member_is_learner"] == "1":
        m["learner_commitment"] = "4"   # required learner question in the real form
    if age >= 15:
        m.update({"member_occupation": rng.choice(["63", "9", "5"]), "member_occupation_other": "Farmer", "member_employment_status": rng.choice(
            ["self_employed", "seasonal", "unpaid_family_worker", "employed_casual"])})
    return m


def _household(rng, code, muni, brgy, day, k, province, region, is_bad, start):
    on = day
    head_age = rng.randint(26, 62)
    head_sex = rng.choice(["male", "female"])
    used = set()

    def nm():
        while True:
            n_ = _name(rng)
            if n_ not in used:
                used.add(n_)
                return n_
    hname = nm()
    members = [_member("hh_head", head_sex, head_age, on, rng, hname),
               _member("spouse", "female" if head_sex == "male" else "male", max(18, head_age + rng.randint(-5, 5)), on, rng, nm())]
    for _ in range(rng.randint(0, 4)):
        members.append(_member("son_daughter", rng.choice(["male", "female"]), rng.randint(0, min(19, head_age - 15)), on, rng, nm()))
    if rng.random() < 0.15:
        members.append(_member("parent", rng.choice(["male", "female"]), head_age + rng.randint(20, 28), on, rng, nm()))
    lat, lon = MUNI_GPS[muni]
    lat += rng.uniform(-0.05, 0.05); lon += rng.uniform(-0.05, 0.05)
    n = len(members)
    dur = rng.randint(14 + 3 * n, 35 + 4 * n)
    end = start + timedelta(minutes=dur)
    sub = (end + timedelta(minutes=rng.randint(5, 300))).astimezone(timezone.utc)
    src = rng.sample(["crop_farming", "livestock", "small_business", "wage_employment", "remittances"], rng.randint(1, 3))
    farm = "crop_farming" in src
    income = rng.randint(3, 25) * 1000
    hh_id = f"{brgy[:3]}-{day.strftime('%y%m%d')}-{rng.randint(1000, 9999)}"
    G = "consent_gated_content/"
    rec = {
        "_uuid": f"u-{code}-{day.isoformat()}-{k}", "_id": rng.randint(10 ** 6, 10 ** 7),
        "_submission_time": sub.strftime("%Y-%m-%dT%H:%M:%S"), "_submitted_by": code.lower(),
        "start": start.isoformat(), "end": end.isoformat(), "today": day.isoformat(),
        "enumerator_code": code, "enumerator_name": "x", "enumerator_role": "Enumerator" if code.startswith("E") else "Community Facilitator",
        "interview_language": "filipino", "program_region": region, "province": province, "municipality": muni,
        "barangay": brgy, "hh_id": hh_id, "informed_consent": "1",
        "gps_coordinate": f"{lat:.6f} {lon:.6f} 20.0 {rng.choice([5, 8, 12, 20])}.0",
        "_geolocation": [lat, lon], "hh_head_name": hname, "hh_head_gender": head_sex, "hh_head_contact": f"09{rng.randint(100000000, 999999999)}",
        "respondent_name": hname, "respondent_relationship": "hh_head", "respondent_contact": f"09{rng.randint(100000000, 999999999)}",
        "is_ip_family": "1", "icc_ip_group": rng.choice(["Tagbanua", "Subanen", "Tboli", "B'laan"]), "gida_area": "1",
        G + "hh_size_count": str(n), G + "hh_child_u6_count": str(sum(1 for m in members if int(m["member_age"]) < 6)),
        G + "hh_infant_u2_count": str(sum(1 for m in members if int(m["member_age"]) < 2)),
        G + "hh_has_learners": "1" if any(m["member_is_learner"] == "1" for m in members) else "0",
        G + "hh_supplemental_feeding_eligible_count": "0",
        G + "hh_shock_risk_resilience_echo": "none_shock", G + "fourps_beneficiary": "0",
        G + "hh_shock_risk": "none_shock", G + "hh_challenges_top3": "income water", G + "hh_assets_owned": "tv radio_audio",
        G + "housing_tenure": "owned", G + "land_tenure": "owned_untitled",
        G + "livelihood_sources": " ".join(src), G + "primary_livelihood": src[0], G + "monthly_income": str(income),
        G + "basic_needs_sufficiency": rng.choice(["2", "3", "3"]),
        G + "severe_food_insecurity": rng.choice(["4", "3", "2"]), G + "produces_own_food": "1" if farm else "0",
        G + "drinking_water_source": rng.choice(["protected_deep_well", "communal_faucet", "deep_well_handpump"]),
        G + "water_access_status": rng.choice(["3", "2"]), G + "water_collection_time": rng.choice(["3", "2"]),
        G + "water_safety_confidence": rng.choice(["3", "2"]), G + "toilet_quality": rng.choice(["4", "2", "3"]),
        G + "family_nutrition_ability": rng.choice(["3", "2"]), G + "family_voice": rng.choice(["2", "3", "4"]),
        G + "governance_cycle_participation": "none_gov_cycle", G + "community_org_participation": "none_org",
        G + "environmental_practices": "none_env",
        G + "leaders_assistance_confidence": rng.choice(["1", "2", "3"]),
        G + "ipra_awareness": rng.choice(["1", "2", "3"]), G + "food_from_production_months": rng.choice(["2", "3", "1"]),
            }
    if any(m["member_is_learner"] == "1" for m in members):
        rec[G + "school_community_engagement"] = rng.choice(["2", "3"])
    if rec[G + "severe_food_insecurity"] != "4":
        rec[G + "food_insecurity_reason"] = rng.choice(["no_money", "price_increase", "job_loss"])
    if "livestock" in src:
        rec[G + "livestock_raised"] = "poultry"
    if int(rec[G + "hh_infant_u2_count"]) > 0:
        rec[G + "caregiver_feeding_practice"] = rng.choice(["4", "3"])
    # Section 9 (staff assessment) consistent with the system-calculated values
    score = rng.randint(30, 90)
    band = "Critical" if score < 40 else "At Risk" if score < 60 else "Stable" if score < 80 else "Thriving"
    urgent = rng.random() < 0.2
    sugg = {"suggest_education": rng.random() < 0.4, "suggest_hapag_asa": rng.random() < 0.3, "suggest_agriculture": farm and rng.random() < 0.5,
            "suggest_water": rng.random() < 0.2, "suggest_governance": rng.random() < 0.2}
    sp = "high" if (urgent or band == "Critical") else ("medium" if band == "At Risk" else "low")
    codes = {"suggest_education": "education_prog", "suggest_hapag_asa": "hapag_asa_prog", "suggest_agriculture": "agriculture_prog",
             "suggest_water": "water_prog", "suggest_governance": "governance_prog"}
    recd = [codes[k] for k, v in sugg.items() if v] or ["none_recommended"]
    rec.update({G + "family_development_score": str(score), G + "hds_band": band, G + "flag_any_urgent": "1" if urgent else "0",
                G + "flag_dropout_risk": "1" if urgent else "0", G + "flag_no_toilet": "0", G + "flag_child_nutrition": "0",
                G + "suggested_priority": sp, G + "family_priority": sp, G + "recommended_programs": " ".join(recd),
                G + "immediate_referral_needed": "1" if urgent else "0", G + "enumerator_remarks": rng.choice(["", "", "Family cooperative", "Needs follow-up visit", "Mother was the main respondent", "Farm visited during interview", "Child was at school", "Interview done at home", "Head was away, spouse answered", "Family asked about the scholarship program"])})
    for k, v in sugg.items():
        rec[G + k] = "1" if v else "0"
    if urgent:
        rec[G + "referral_reason"] = "dropout_risk"; rec[G + "referred_to"] = "school"
    if farm:
        rec.update({G + "cultivates_farmland": "1", G + "climate_resilience_confidence": rng.choice(["2", "3", "1"]),
                    G + "farm_hectares": str(round(rng.uniform(0.5, 3), 1)), G + "market_sold_proportion": "2",
                    G + "harvest_food_proportion": "2", G + "harvest_shared_proportion": "1",
                    G + "home_produced_food_types": "vegetables rice_staples", G + "sustainable_practices": "organic_fertilizer"})
    if not ({"crop_farming", "livestock"} & set(src)):          # farm occupations only where the family farms
        for m in members:
            if m.get("member_occupation") in ("61", "62", "63"):
                m["member_occupation"] = "9"
    rec["hh_members"] = [{("hh_members/" + k_): v for k_, v in m.items()} for m in members]
    return rec


def _members(rec):
    return [{k.split("/")[-1]: v for k, v in m.items()} for m in rec["hh_members"]]


def _set_members(rec, members):
    rec["hh_members"] = [{("hh_members/" + k): v for k, v in m.items()} for m in members]


G = "consent_gated_content/"


def _inject(rec, rid, rng, pool):
    """Plant one specific error. Returns True if applied."""
    ms = _members(rec)
    partners = set()
    if rid == "MB07":
        ms[-1]["member_sex"] = "male"; ms[-1]["member_plw_status"] = "pregnant"
    elif rid == "MB03":
        ms.append(_member("son_daughter", "male", 7, date.fromisoformat(rec["today"]), rng)); ms[-1]["member_schooling_status"] = "grade_9"
    elif rid == "MB10":
        head = int(ms[0]["member_age"])
        ms.append(_member("son_daughter", "male", head - 3, date.fromisoformat(rec["today"]), rng))
    elif rid == "MB12":
        ms[0]["member_special_status"] = "pwd"; ms[0]["member_disability_type"] = ""
    elif rid == "MB05":
        ms.append(_member("son_daughter", "male", 9, date.fromisoformat(rec["today"]), rng)); ms[-1]["member_occupation"] = "9"
    elif rid == "MB04":
        ms[1]["member_schooling_status"] = "never_attended"; ms[1]["member_educ_attainment"] = "jhs_grad"
    elif rid == "HH03":
        ms[1]["member_relationship"] = "hh_head"
    elif rid == "SO01":
        rec[G + "hh_assets_owned"] = "none tv"
    elif rid == "LV01":
        rec[G + "primary_livelihood"] = "government_employment"
    elif rid == "LV08":
        rec[G + "cultivates_farmland"] = "1"; rec[G + "livelihood_sources"] += " crop_farming"
        rec[G + "market_sold_proportion"] = "4"; rec[G + "harvest_food_proportion"] = "4"; rec[G + "harvest_shared_proportion"] = "2"
        rec[G + "farm_hectares"] = "1.0"
    elif rid == "LV04":
        rec[G + "monthly_income"] = "950000"
    elif rid == "WS01":
        rec[G + "drinking_water_source"] = "level3_piped"; rec[G + "water_collection_time"] = "1"
    elif rid == "HH04":
        rec["hh_head_name"] = "Quimpo, Zacharias, Lim"
    elif rid == "HH07":
        end = datetime.fromisoformat(rec["start"]) + timedelta(minutes=4); rec["end"] = end.isoformat()
    elif rid == "HH14":
        rec["gps_coordinate"] = "40.712800 -74.006000 10.0 5.0"; rec["_geolocation"] = [40.7128, -74.006]
    elif rid == "HH12":
        rec["gps_coordinate"] = ""; rec["_geolocation"] = [None, None]
    elif rid == "HH11":
        rec["is_ip_family"] = "1"; rec["icc_ip_group"] = ""
    elif rid == "HH01":
        other = rng.choice([p for p in pool if p["hh_id"] != rec["hh_id"]]); rec["hh_id"] = other["hh_id"]; partners.add(other["_uuid"])
    elif rid == "HH15":
        other = rng.choice([p for p in pool if p["_uuid"] != rec["_uuid"]])
        rec["gps_coordinate"] = other["gps_coordinate"]; rec["_geolocation"] = other["_geolocation"]; partners.add(other["_uuid"])
    elif rid == "SO05":
        other = rng.choice([p for p in pool if p["barangay"] == rec["barangay"] and p["_uuid"] != rec["_uuid"]] or [None])
        if other is None:
            return set()
        rec["hh_head_name"] = other["hh_head_name"]; rec["respondent_name"] = other["hh_head_name"]
        om = _members(other)[0]
        ms[0]["member_full_name"] = other["hh_head_name"]; ms[0]["member_dob"] = om["member_dob"]; ms[0]["member_age"] = om["member_age"]
        partners.add(other["_uuid"])
    elif rid == "SO03":
        for f in ("water_access_status", "water_safety_confidence", "basic_needs_sufficiency", "family_nutrition_ability",
                  "family_voice", "leaders_assistance_confidence", "climate_resilience_confidence", "food_from_production_months",
                  "severe_food_insecurity", "toilet_quality", "ipra_awareness", "school_community_engagement"):
            rec[G + f] = "4"
    elif rid == "MB20":
        ms[-1]["member_full_name"] = "juan santos"
    elif rid == "TX01":
        ms[-1]["member_remarks"] = "asdfghj"; rec[G + "enumerator_remarks"] = "test test"
    elif rid == "TX03":
        rec[G + "enumerator_remarks"] = "www.facebook.com/page"
    elif rid == "CT01":
        rec["hh_head_contact"] = "12345"
    elif rid == "HH20":
        rec["today"] = "2025-11-01"
    elif rid == "LV12":
        rec[G + "livelihood_sources"] = "none_livelihood"; rec[G + "primary_livelihood"] = "none_livelihood"; rec[G + "monthly_income"] = "0"
        rec[G + "cultivates_farmland"] = "0"
        for m in ms:
            if int(m["member_age"]) >= 15: m["member_employment_status"] = "employed_regular"
    elif rid == "MB21":
        ms[1]["member_special_status"] = "none pwd"; ms[1]["member_disability_type"] = "visual"
    elif rid == "S901":
        rec[G + "flag_any_urgent"] = "1"; rec[G + "suggested_priority"] = "high"; rec[G + "family_priority"] = "low"; rec[G + "enumerator_remarks"] = ""
        rec[G + "immediate_referral_needed"] = "1"; rec[G + "referral_reason"] = "dropout_risk"; rec[G + "referred_to"] = "school"; rec[G + "flag_dropout_risk"] = "1"
    elif rid == "S902":
        rec[G + "flag_any_urgent"] = "1"; rec[G + "immediate_referral_needed"] = "0"; rec[G + "suggested_priority"] = "high"; rec[G + "family_priority"] = "high"
        rec.pop(G + "referral_reason", None); rec.pop(G + "referred_to", None)
    elif rid == "S903":
        rec[G + "flag_any_urgent"] = "0"; rec[G + "hds_band"] = "Thriving"; rec[G + "family_development_score"] = "88"
        rec[G + "suggested_priority"] = "low"; rec[G + "family_priority"] = "low"; rec[G + "immediate_referral_needed"] = "1"
        rec[G + "referral_reason"] = "other"; rec[G + "referral_reason_other"] = "Family asked for help"; rec[G + "referred_to"] = "lgu"
    elif rid == "S904":
        rec[G + "suggest_water"] = "1"; rec[G + "recommended_programs"] = "education_prog"
    elif rid == "S905":
        rec[G + "family_development_score"] = "30"; rec[G + "hds_band"] = "Thriving"
    elif rid == "S906":
        rec[G + "flag_any_urgent"] = "1"; rec[G + "immediate_referral_needed"] = "1"; rec[G + "suggested_priority"] = "high"; rec[G + "family_priority"] = "high"
        rec[G + "referral_reason"] = "no_toilet"; rec[G + "referred_to"] = "rhu"; rec[G + "flag_no_toilet"] = "0"
    elif rid == "SKIP01":
        rec[G + "referral_reason"] = "dropout_risk"; rec[G + "immediate_referral_needed"] = "0"; rec[G + "flag_any_urgent"] = "0"
        rec[G + "suggested_priority"] = "low"; rec[G + "family_priority"] = "low"
    elif rid == "MB22":
        ms.append(_member("son_daughter", "male", 14, date.fromisoformat(rec["today"]), rng))
        ms[-1]["member_schooling_status"] = "out_of_school"; ms[-1]["member_educ_attainment"] = "college_grad"
    elif rid == "MB23":
        ms[1]["member_employment_status"] = "employed_regular"; ms[1]["member_occupation"] = "not_applicable"
    elif rid == "MB24":
        ms[0]["member_civil_status"] = "single"
    elif rid == "MB25":
        ms[:] = [m for m in ms if int(m["member_age"]) >= 18]; ms[0]["member_special_status"] = "solo_parent"
    elif rid == "MB26":
        ms[:] = [m for m in ms if int(m["member_age"]) >= 3]
        mom = _member("other_relative", "female", 30, date.fromisoformat(rec["today"]), rng); mom["member_plw_status"] = "lactating"
        ms.append(mom)
    elif rid == "MB27":
        kid = _member("son_daughter", "male", 12, date.fromisoformat(rec["today"]), rng)
        kid["dropout_risk"] = "4"; kid["learner_commitment"] = "1"; kid["attending_regularly"] = "3"
        ms.append(kid)
    elif rid == "MB28":
        rec[G + "livelihood_sources"] = "small_business"; rec[G + "primary_livelihood"] = "small_business"
        ms[0]["member_occupation"] = "61"; ms[0]["member_employment_status"] = "self_employed"
    elif rid == "HH22":
        ages = [int(m["member_age"]) for m in ms]
        rec[G + "hh_senior_count"] = str(sum(a >= 60 for a in ages) + 2)
        rec[G + "hh_school_age_count"] = str(sum(5 <= a <= 17 for a in ages) + 1)
    elif rid == "HH23":
        rec[G + "hh_shock_risk"] = "flood_typhoon"; rec[G + "hh_shock_risk_resilience_echo"] = "drought"
    elif rid == "HH24":
        rec[G + "housing_tenure"] = "informal_settler"; rec[G + "land_tenure"] = "owned_titled"
    elif rid == "HH25":
        rec[G + "hh_assets_owned"] = "fourwheel_vehicle aircon"; rec[G + "monthly_income"] = "2000"
    elif rid == "HH26":
        rec[G + "fourps_beneficiary"] = "1"; rec[G + "monthly_income"] = "140000"
    elif rid == "HH27":
        rec[G + "family_nutrition_ability"] = "4"; rec[G + "severe_food_insecurity"] = "0"
    elif rid == "HH28":
        n0 = datetime.fromisoformat(rec["start"]).replace(hour=23, minute=50)
        rec["start"] = n0.isoformat(); rec["end"] = (n0 + timedelta(minutes=40)).isoformat()
    elif rid == "HH29":
        if not rec.get("gps_coordinate"):
            return set()
        lat, lon = [float(x) for x in rec["gps_coordinate"].split()[:2]]
        rec["gps_coordinate"] = f"{lat + 0.5:.6f} {lon:.6f} 8.0 5.0"; rec["_geolocation"] = [lat + 0.5, lon]
    else:
        return set()
    _set_members(rec, ms)
    if rid in ("MB07", "MB03", "MB10", "MB05", "MB22", "MB25", "MB26", "MB27"):
        rec[G + "hh_size_count"] = str(len(ms))
        rec[G + "hh_child_u6_count"] = str(sum(1 for m in ms if int(m["member_age"]) < 6))
    return {rec["_uuid"]} | partners


RULE_IDS = ["MB20", "TX01", "TX03", "CT01", "HH20", "LV12", "MB21", "S901", "S902", "S903", "S904", "S905", "S906", "SKIP01", "MB07", "MB03", "MB10", "MB12", "MB05", "MB04", "HH03", "SO01", "LV01", "LV08", "LV04", "WS01", "HH04",
            "HH07", "HH14", "HH12", "HH11", "HH01", "HH15", "SO05", "SO03",
            "MB22", "MB23", "MB24", "MB25", "MB26", "MB27", "MB28", "HH22", "HH23", "HH24", "HH25", "HH26", "HH27", "HH28", "HH29"]


def generate(labels, directory, monitoring_xlsx, seed=7, days=14):
    rng = random.Random(seed)
    brg = _muni_barangays(monitoring_xlsx.parent / "FDAF_master.xlsx")
    muni_label = {_norm(v): k for k, v in labels["program_municipality"].items()}
    prov_of = {}
    wb = openpyxl.load_workbook(monitoring_xlsx.parent / "FDAF_master.xlsx", read_only=True)
    rows = list(wb["choices"].iter_rows(values_only=True)); h = list(rows[0])
    for r in rows[1:]:
        if r[0] == "program_municipality":
            prov_of[r[1]] = r[h.index("province")]
    reg_of = {r[1]: r[h.index("program_region")] for r in rows[1:] if r[0] == "program_province"}

    people = directory[directory["code"].str.match(r"^(E\d+|CF0[1-9])$")]
    recs, truth = [], {}
    for p in people.itertuples():
        muni = muni_label.get(_norm(p.home_area)) or rng.choice(list(MUNI_GPS))
        if p.title == "Community Facilitator" and not p.home_area:
            continue
        for d in range(days):
            day = TODAY - timedelta(days=d)
            if day.weekday() == 6 or rng.random() < 0.25:
                continue
            cur = datetime(day.year, day.month, day.day, rng.randint(8, 9), rng.randint(0, 59), tzinfo=PH)
            for k in range(rng.randint(1, 4)):
                b = rng.choice(brg[muni])
                rec = _household(rng, p.code, muni, b, day, k, prov_of[muni], reg_of[prov_of[muni]], p.code in BAD_ENUMS, cur)
                cur = datetime.fromisoformat(rec["end"]) + timedelta(minutes=rng.randint(10, 45))
                recs.append(rec)
    # one consent-declined survey per ~40
    for r in rng.sample(recs, max(3, len(recs) // 40)):
        r["informed_consent"] = "0"; r["hh_members"] = []
        for kk in ("hh_head_name", "hh_head_gender", "hh_head_contact", "respondent_name", "respondent_relationship",
                   "respondent_contact", "is_ip_family", "icc_ip_group", "gida_area", "gps_coordinate", "_geolocation"):
            r.pop(kk, None)
        for kk in [k for k in r if k.startswith(G)]:
            del r[kk]
    # plant errors
    pool = [r for r in recs if r["informed_consent"] == "1"]
    for rid in RULE_IDS:
        for _ in range(3):
            tgt = rng.choice(pool)
            got = _inject(tgt, rid, rng, pool)
            if got:
                truth.setdefault(rid, set()).update(got)
    # bad enumerators: extra random errors
    for r in pool:
        if r["enumerator_code"] in BAD_ENUMS and rng.random() < 0.45:
            rid = rng.choice(["MB07", "MB03", "MB10", "MB12", "LV01", "SO01", "HH07", "LV08"])
            got = _inject(r, rid, rng, pool)
            if got:
                truth.setdefault(rid, set()).update(got)
    # copy-paste clones (same enumerator, same answers)
    for _ in range(3):
        src = rng.choice([r for r in pool if r["enumerator_code"] not in ()])
        clone = {k: (list(v) if isinstance(v, list) else v) for k, v in src.items()}
        clone["_uuid"] = src["_uuid"] + "-clone"; clone["hh_id"] = src["hh_id"][:-4] + "9999"
        clone["hh_head_name"] = "Santos, Clone, Head"; clone["respondent_name"] = "Santos, Clone, Head"
        clone["gps_coordinate"] = src["gps_coordinate"].replace(".", ",", 0)
        lat, lon = [float(x) for x in src["gps_coordinate"].split()[:2]]
        clone["gps_coordinate"] = f"{lat + 0.01:.6f} {lon + 0.01:.6f} 20.0 8.0"; clone["_geolocation"] = [lat + 0.01, lon + 0.01]
        clone["start"] = (datetime.fromisoformat(src["start"]) + timedelta(hours=3)).isoformat()
        clone["end"] = (datetime.fromisoformat(src["end"]) + timedelta(hours=3)).isoformat()
        recs.append(clone)
        truth.setdefault("SO06", set()).update({src["_uuid"], clone["_uuid"]})
    # overlapping interviews
    byk = {}
    for r in recs:
        byk.setdefault((r["enumerator_code"], r["today"]), []).append(r)
    cands = [v for v in byk.values() if len(v) >= 2]
    for v in rng.sample(cands, 3):
        v.sort(key=lambda r: r["start"])
        v[1]["start"] = (datetime.fromisoformat(v[0]["start"]) + timedelta(minutes=2)).isoformat()
        v[1]["end"] = (datetime.fromisoformat(v[1]["start"]) + timedelta(minutes=30)).isoformat()
        truth.setdefault("SO09", set()).add(v[1]["_uuid"])
    # impossible travel: the enumerator's last interview of the day starts 15 min after the previous one ended, ~44 km away
    taken = set().union(*truth.values())
    by2 = {}
    for r in recs:
        if r["_uuid"] not in taken and r.get("gps_coordinate") and r["informed_consent"] == "1":
            by2.setdefault((r["enumerator_code"], r["today"]), []).append(r)
    pairs = [v for v in by2.values() if len(v) >= 2]
    for v in rng.sample(pairs, min(3, len(pairs))):
        v.sort(key=lambda r: r["start"])
        a, b = v[-2], v[-1]
        b["start"] = (datetime.fromisoformat(a["end"]) + timedelta(minutes=15)).isoformat()
        b["end"] = (datetime.fromisoformat(b["start"]) + timedelta(minutes=30)).isoformat()
        lat, lon = [float(x) for x in a["gps_coordinate"].split()[:2]]
        b["gps_coordinate"] = f"{lat + 0.4:.6f} {lon:.6f} 8.0 5.0"; b["_geolocation"] = [lat + 0.4, lon]
        truth.setdefault("SO12", set()).add(b["_uuid"])
    return recs, _monitoring(rng, recs, directory, monitoring_xlsx), truth


def _monitoring(rng, recs, directory, xlsx):
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    names = [r[1] for r in wb["survey"].iter_rows(min_row=2, values_only=True)
             if r[1] and re.match(r"^s\d_\d\d_", r[1]) and not r[1].endswith("_expl")]
    monitors = ["CF01", "CF02", "CF03", "AC01", "AC02", "SPM01", "MES01"]
    out = []
    by_enum = {}
    for r in recs:
        if r["informed_consent"] == "1":
            by_enum.setdefault(r["enumerator_code"], []).append(r)
    for code, lst in by_enum.items():
        for j in range(rng.choice([0, 1, 2, 3, 4])):
            s = rng.choice(lst)
            bad = code in BAD_ENUMS
            p = [0.5, 0.3, 0.2] if bad else [0.88, 0.09, 0.03]
            rec = {"_uuid": f"m-{code}-{j}", "_id": rng.randint(10 ** 6, 10 ** 7),
                   "_submission_time": f"{(TODAY - timedelta(days=rng.randint(0, 10))).isoformat()}T05:00:00",
                   "monitoring_info/monitor_code": rng.choice(monitors), "monitoring_info/monitoring_date": (TODAY - timedelta(days=rng.randint(0, 10))).isoformat(),
                   "monitoring_info/enumerator_monitored": code, "monitoring_info/fdaf_family_id": s["hh_id"],
                   "monitoring_info/interview_date": s["today"], "s1/g_consent": "yes"}
            pts, app = {}, {}
            for n in names:
                sec = n[1]
                rating = rng.choices(["yes", "partly", "no"], p)[0]
                rec[f"s{sec}/{n}"] = rating
                rec[f"s{sec}/{n}_expl"] = "Reviewed against FDAF record"
                pts[sec] = pts.get(sec, 0) + {"yes": 1, "partly": 0.5, "no": 0}[rating]
                app[sec] = app.get(sec, 0) + 1
            for sec in pts:
                rec[f"s{sec}/s{sec}_overall_comment"] = "Demo comment"
                rec[f"summary/s{sec}_points"] = str(pts[sec]); rec[f"summary/s{sec}_applicable"] = str(app[sec])
            out.append(rec)
    return out
