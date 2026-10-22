"""FDAF Monitoring Dashboard  -  run with:  streamlit run app.py"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hmac  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.monitoring import SECTION_NAMES  # noqa: E402
from src.pipeline import live_ready as _live_ready, load_config, run_pipeline  # noqa: E402

st.set_page_config(page_title="FDAF Monitoring Dashboard", page_icon=":bar_chart:", layout="wide")
cfg = load_config()

# --- PASSWORD PROTECTION GATE ---
def check_password():
    """Returns `True` if the user entered the correct password or passed it via URL."""
    query_params = st.query_params
    if "password" in query_params and hmac.compare_digest(query_params["password"], st.secrets.get("password", "")):
        st.session_state["password_correct"] = True
        return True

    def password_entered():
        if hmac.compare_digest(st.session_state["password"], st.secrets.get("password", "")):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.text_input("🔒 Enter Password to Access ❤️leep Dashboard", type="password", on_change=password_entered, key="password")
    if "password_correct" in st.session_state:
        st.error("😕 Password incorrect. Please try again.")
    return False

if not check_password():
    st.stop()
# ---------------------------------

LEVEL_COLORS = {"High": "#c6efce", "Medium": "#ffeb9c", "Low": "#ffc7ce"}
SEV_COLORS = {"Critical": "#ffc7ce", "Major": "#ffeb9c", "Minor": "#ddebf7"}


def show_df(df, **kw):
    try:
        return st.dataframe(df, width="stretch", **kw)
    except Exception:
        return st.dataframe(df, use_container_width=True, **kw)


@st.cache_data(ttl=int(cfg.get("cache_minutes", 10)) * 60, show_spinner="Pulling data from KoboToolbox ...")
def get_data(demo):
    return run_pipeline(cfg, demo=demo)


def style_cells(df, column, colors):
    sty = df.style
    fn = getattr(sty, "map", None) or sty.applymap
    return fn(lambda v: f"background-color: {colors.get(v, '')}", subset=[column])


def score_style(df, cols):
    def f(v):
        if pd.isna(v):
            return ""
        return "background-color: #c6efce" if v >= 90 else ("background-color: #ffeb9c" if v >= 75 else "background-color: #ffc7ce")
    sty = df.style.format({c: "{:.1f}" for c in cols}, na_rep="-")
    fn = getattr(sty, "map", None) or sty.applymap
    return fn(f, subset=cols)


def download(df, name):
    """Provides side-by-side buttons for CSV and Excel exports."""
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            f"📄 Download {name}.csv",
            df.to_csv(index=False).encode("utf-8-sig"),
            f"{name}.csv",
            "text/csv"
        )
    with c2:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")
        st.download_button(
            f"📊 Download {name}.xlsx",
            output.getvalue(),
            f"{name}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# ---------------- sidebar ----------------
live_ready = _live_ready(cfg)
st.sidebar.title("FDAF Dashboard")
mode = st.sidebar.radio("Data source", ["Live (KoboToolbox)", "Demo data"], index=0 if live_ready else 1)
if mode.startswith("Live") and not live_ready:
    st.sidebar.warning("KOBO_TOKEN and/or the project UIDs are not set. Showing demo data.")
    mode = "Demo data"
if st.sidebar.button("Refresh now"):
    st.cache_data.clear()
try:
    D = get_data(mode == "Demo data")
except Exception as exc:
    import traceback
    st.error(f"Could not load data: {exc}")
    st.stop()

# ---- automatic refresh ----
if hasattr(st, "fragment") and mode.startswith("Live"):
    @st.fragment(run_every=f"{max(1, int(cfg.get('cache_minutes', 10)))}m")
    def _auto_refresh():
        if st.session_state.get("_auto_refresh_armed"):
            st.rerun()
        st.session_state["_auto_refresh_armed"] = True
    _auto_refresh()

hh, integ, flags, mon, items, enum, daily = (D[k] for k in ("hh", "integrity", "flags", "monitoring", "items", "enumerators", "daily"))
if hh.empty:
    st.info("No FDAF submissions yet.")
    st.stop()

# ---------------- cascading sidebar filters ----------------
dmin, dmax = hh["interview_date"].min().date(), hh["interview_date"].max().date()
dates = st.sidebar.date_input("Interview dates", (dmin, dmax), min_value=dmin, max_value=dmax)
d0, d1 = (dates if isinstance(dates, tuple) and len(dates) == 2 else (dmin, dmax))

df_filtered = hh[hh["interview_date"].dt.date.between(d0, d1)].copy()

# 1. Area (Municipality)
all_areas = sorted(df_filtered["municipality_label"].dropna().unique())
areas = st.sidebar.multiselect("Area (municipality)", all_areas)
if areas:
    df_filtered = df_filtered[df_filtered["municipality_label"].isin(areas)]

# 2. Barangay (Cascades from Municipality)
all_brgys = sorted(df_filtered["barangay_label"].dropna().unique())
brgys = st.sidebar.multiselect("Barangay", all_brgys)
if brgys:
    df_filtered = df_filtered[df_filtered["barangay_label"].isin(brgys)]

# 3. Enumerator / CF (Cascades from Municipality & Barangay)
all_people = sorted(df_filtered["enumerator_label"].dropna().unique())
people = st.sidebar.multiselect("Enumerator / CF", all_people)
if people:
    df_filtered = df_filtered[df_filtered["enumerator_label"].isin(people)]

# Role / Title
titles = st.sidebar.multiselect("Role / title", sorted(hh["title"].dropna().unique()))
if titles:
    df_filtered = df_filtered[df_filtered["title"].isin(titles)]

# Kobo Form / Project
forms = st.sidebar.multiselect("Kobo form / project", sorted(hh["source_form"].dropna().unique())) if "source_form" in hh.columns else []
if forms and "source_form" in hh.columns:
    df_filtered = df_filtered[df_filtered["source_form"].isin(forms)]

f_hh = df_filtered
ids = set(f_hh["uuid"])
f_int = integ[integ["uuid"].isin(ids)]
f_flags = flags[flags["uuid"].isin(ids)]
codes = set(f_hh["enumerator_code"])
f_mon = mon[mon["enumerator_monitored"].isin(codes) | (not (titles or areas or brgys or people or forms))]
f_mon = f_mon[f_mon["monitoring_date"].between(pd.Timestamp(d0), pd.Timestamp(d1)) | f_mon["monitoring_date"].isna()]
f_enum = enum[enum["enumerator_code"].isin(codes) | (not (titles or areas or brgys or people or forms))]

st.title("FDAF Survey Monitoring")
st.caption(f"Source: {D['status']['source']}  |  refreshed {D['status']['refreshed_at']}  |  "
           f"{len(f_hh):,} surveys in view")
tab_over, tab_daily, tab_mon, tab_int, tab_audit, tab_conf, tab_status = st.tabs(
    ["Overview", "Daily surveys", "Quality & compliance", "Data integrity", "Audit log (Tables 1 & 2)", "Enumerator confidence", "Data status"])

# ---------------- overview ----------------
with tab_over:
    c = st.columns(6)
    c[0].metric("Surveys", f"{len(f_hh):,}")
    c[1].metric("Consent given", f"{int(f_hh['consented'].sum()):,}")
    c[2].metric("Active enumerators/CFs", f_hh["enumerator_code"].nunique())
    c[3].metric("Surveys on latest day", int((f_hh["interview_date"] == f_hh["interview_date"].max()).sum()))
    c[4].metric("Avg monitoring score", "-" if f_mon.empty else f"{f_mon['overall_score'].mean():.1f}%")
    c[5].metric("Surveys with no Critical/Major flag", f"{f_int['clean'].mean() * 100:.0f}%" if len(f_int) else "-")
    st.subheader("Surveys per day")
    per_day = f_hh.groupby(f_hh["interview_date"].dt.date).size().rename("surveys")
    st.bar_chart(per_day)
    lv = f_enum["confidence_level"].value_counts().reindex(["High", "Medium", "Low", "No data"]).fillna(0).astype(int)
    st.subheader("Confidence levels")
    cc = st.columns(4)
    for col, name in zip(cc, lv.index):
        col.metric(name, int(lv[name]))

# ---------------- daily ----------------
def add_total_row(df, label_cols):
    tot = {c: "ALL" for c in label_cols}
    tot[label_cols[0]] = "TOTAL"
    for c in df.columns:
        if c not in label_cols:
            tot[c] = df[c].sum()
    return pd.concat([df, pd.DataFrame([tot])[list(df.columns)]], ignore_index=True)


with tab_daily:
    st.subheader("Daily surveys conducted")
    g_all = f_hh.copy()
    g_all["day"] = g_all["interview_date"].dt.strftime("%Y-%m-%d")
    g_all["consent_n"] = g_all["consented"].astype(int)
    metric = st.radio("Count in the day-by-day tables", ["All surveys", "Consent given only"], horizontal=True)
    g = g_all[g_all["consented"]] if metric.startswith("Consent") else g_all

    n_days = g_all["day"].nunique()
    k = st.columns(6)
    k[0].metric("OVERALL TOTAL surveys", f"{len(g_all):,}")
    k[1].metric("Consent given", f"{int(g_all['consent_n'].sum()):,}")
    k[2].metric("Municipalities", g_all["municipality_label"].nunique())
    k[3].metric("Barangays", g_all["barangay_label"].nunique())
    k[4].metric("Enumerators / CFs", g_all["enumerator_code"].nunique())
    k[5].metric("Avg surveys per field day", f"{len(g_all) / max(n_days, 1):.1f}")

    if g.empty:
        st.info("No surveys match the current selection.")
    else:
        st.markdown("#### Surveys per enumerator per day")
        pe = g.pivot_table(index=["enumerator_label", "title"], columns="day", values="uuid", aggfunc="count", fill_value=0)
        pe["Total"] = pe.sum(axis=1)
        pe = add_total_row(pe.sort_values("Total", ascending=False).reset_index(), ["enumerator_label", "title"])
        show_df(pe, hide_index=True)
        download(pe, "surveys_per_enumerator_per_day")

    def area_table(cols, with_barangays=False):
        agg = {"Surveys": ("uuid", "count"), "Consent given": ("consent_n", "sum"),
               "Enumerators": ("enumerator_code", "nunique"), "Field days": ("day", "nunique")}
        if with_barangays:
            agg["Barangays"] = ("barangay_label", "nunique")
        t = g_all.groupby(cols).agg(**agg).reset_index().sort_values("Surveys", ascending=False)
        t["Avg / field day"] = (t["Surveys"] / t["Field days"].clip(lower=1)).round(1)
        t["% of all surveys"] = (t["Surveys"] / max(len(g_all), 1) * 100).round(1)
        tot = {c: "ALL" for c in cols}
        tot[cols[-1]] = "TOTAL"
        tot.update({"Surveys": len(g_all), "Consent given": int(g_all["consent_n"].sum()),
                    "Enumerators": g_all["enumerator_code"].nunique(), "Field days": n_days,
                    "Avg / field day": round(len(g_all) / max(n_days, 1), 1), "% of all surveys": 100.0})
        if with_barangays:
            tot["Barangays"] = g_all["barangay_label"].nunique()
        return pd.concat([t, pd.DataFrame([tot])[list(t.columns)]], ignore_index=True)

    if not g_all.empty:
        st.markdown("#### Total per municipality")
        tm = area_table(["province_label", "municipality_label"], with_barangays=True)
        show_df(tm, hide_index=True)
        download(tm, "total_per_municipality")

        st.markdown("#### Total per barangay")
        tb = area_table(["municipality_label", "barangay_label"])
        show_df(tb, hide_index=True)
        download(tb, "total_per_barangay")

# ---------------- monitoring ----------------
with tab_mon:
    st.subheader("Quality & compliance monitoring scores")
    if f_mon.empty:
        st.info("No monitoring submissions in view yet.")
    else:
        c = st.columns(4)
        c[0].metric("Monitoring visits", len(f_mon))
        c[1].metric("Average overall score", f"{f_mon['overall_score'].mean():.1f}%")
        c[2].metric("Critical failures (consent)", int(f_mon["critical_fail"].sum()))
        c[3].metric("Consent declined (not scored)", int(f_mon["consent_declined"].sum()))
        scored = f_mon[~f_mon["consent_declined"]]
        tbl = scored.groupby(["enumerator_label", "enumerator_title"]).agg(
            visits=("uuid", "count"), overall=("overall_score", "mean"), **{SECTION_NAMES[n]: (f"s{n}_score", "mean") for n in range(1, 10)}
        ).reset_index().sort_values("overall")
        show_df(score_style(tbl, ["overall"] + [SECTION_NAMES[n] for n in range(1, 10)]), hide_index=True)
        download(tbl, "monitoring_scores_by_enumerator")

    ml = D.get("mon_links")
    if ml is not None and len(ml) > 0:
        any_filter = bool(titles or areas or brgys or people or forms)
        view = ml[ml["enumerator_label"].isin(set(f_hh["enumerator_label"])) | (not any_filter)]
        view = view[view["monitoring_date"].between(pd.Timestamp(d0), pd.Timestamp(d1)) | view["monitoring_date"].isna()]
        st.markdown("**Monitoring visits that do not match the FDAF data**")
        if len(view):
            show_df(view.sort_values("monitoring_date", ascending=False), hide_index=True)
            download(view, "monitoring_link_issues")
        else:
            st.caption("Every monitoring visit in view matches an FDAF survey.")

# ---------------- integrity ----------------
with tab_int:
    st.subheader("Data integrity - answer consistency checks")
    c = st.columns(5)
    c[0].metric("Surveys checked", len(f_int))
    c[1].metric("Critical flags", int(f_int["Critical"].sum()))
    c[2].metric("Major flags", int(f_int["Major"].sum()))
    c[3].metric("Minor flags", int(f_int["Minor"].sum()))
    c[4].metric("Avg integrity score", f"{f_int['integrity_score'].mean():.1f}" if len(f_int) else "-")

# ---------------- audit log ----------------
with tab_audit:
    st.subheader("Data quality audit")
    from src.audit import audit_tables
    A = audit_tables(f_flags, f_hh)
    
    st.markdown("**Table 1 - Summary of data quality**")
    show_df(A["t1"], hide_index=True)
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("Common error categories")
        if "t1_category" in A:
            show_df(A["t1_category"], hide_index=True)
    with c2:
        st.markdown("Most common error types")
        if "t1_rules" in A:
            show_df(A["t1_rules"], hide_index=True)

    st.markdown("**Table 2 - Detailed Flagged Submissions Log**")
    
    if f_flags.empty:
        st.info("No flagged submissions match the current filter selection.")
    else:
        t2_rich = f_flags.copy()
        
        # Normalize UUIDs for clean joining across dataframes
        if "uuid" in t2_rich.columns and "uuid" in f_hh.columns:
            t2_rich["_join_uuid"] = t2_rich["uuid"].astype(str).str.strip()
            f_hh_temp = f_hh.copy()
            f_hh_temp["_join_uuid"] = f_hh_temp["uuid"].astype(str).str.strip()
            
            possible_meta = [
                "_join_uuid", "interview_date", "submission_date", 
                "municipality_label", "municipality", 
                "barangay_label", "barangay", 
                "enumerator_label", "enumerator", "enumerator_name", 
                "hh_id", "household_id"
            ]
            meta_cols = [c for c in possible_meta if c in f_hh_temp.columns]
            t2_rich = t2_rich.merge(f_hh_temp[meta_cols].drop_duplicates(subset=["_join_uuid"]), on="_join_uuid", how="left")

        # Parse submission date safely
        date_col = next((c for c in ["interview_date", "submission_date", "date"] if c in t2_rich.columns), None)
        if date_col:
            t2_rich["Submission Date"] = pd.to_datetime(t2_rich[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        else:
            t2_rich["Submission Date"] = "N/A"
            
        # Flexible column mapping
        rename_map = {}
        for src, target in [
            ("municipality_label", "Municipality"), ("municipality", "Municipality"),
            ("barangay_label", "Barangay"), ("barangay", "Barangay"),
            ("enumerator_label", "Enumerator Name"), ("enumerator", "Enumerator Name"), ("enumerator_name", "Enumerator Name"),
            ("hh_id", "Actual HH ID"), ("household_id", "Actual HH ID"),
            ("severity", "Severity"),
            ("category", "Error Category"),
            ("rule", "Rule Violated"),
            ("detail", "Specific Details"),
            ("details", "Specific Details"),
            ("description", "Description")
        ]:
            if src in t2_rich.columns and target not in rename_map.values():
                rename_map[src] = target
                
        t2_rich = t2_rich.rename(columns=rename_map)
        
        display_cols = [
            "Submission Date", "Municipality", "Barangay", "Enumerator Name", 
            "Actual HH ID", "Severity", "Error Category", "Rule Violated", "Specific Details", "Description"
        ]
        display_cols = [c for c in display_cols if c in t2_rich.columns]
        
        for col in t2_rich.columns:
            if col not in display_cols and col not in ["_join_uuid", "uuid", "interview_date", "submission_date"]:
                display_cols.append(col)
                
        t2_display = t2_rich[display_cols]
        sort_keys = [k for k in ["Submission Date", "Municipality"] if k in t2_display.columns]
        if sort_keys:
            asc_bools = [False if k == "Submission Date" else True for k in sort_keys]
            t2_display = t2_display.sort_values(sort_keys, ascending=asc_bools, na_position="last")
        
        sev_opts = t2_display["Severity"].dropna().unique().tolist() if "Severity" in t2_display.columns else ["Critical", "Major", "Minor"]
        sevs = st.multiselect("Filter by Severity", sev_opts, default=[s for s in ["Critical", "Major"] if s in sev_opts], key="aud_sev_rich_v4")
        
        if sevs and "Severity" in t2_display.columns:
            t2_display = t2_display[t2_display["Severity"].isin(sevs)]
            
        show_df(t2_display, hide_index=True)
        download(t2_display, "audit_flagged_submissions_log")

# ---------------- confidence ----------------
with tab_conf:
    st.subheader("Enumerator / CF confidence level")
    w = cfg["confidence"]
    cols = ["enumerator_label", "title", "home_area", "surveys", "monitored", "monitoring_score", "integrity_score", "clean_rate",
            "critical_flags", "major_flags", "confidence_score", "confidence_level", "basis", "note"]
    ct = f_enum[cols].copy()
    show_df(style_cells(ct.round(1), "confidence_level", LEVEL_COLORS), hide_index=True)
    download(ct, "enumerator_confidence")

# ---------------- status ----------------
with tab_status:
    s = D["status"]
    st.write(f"**Source:** {s['source']}")
    st.write(f"**Last refreshed:** {s['refreshed_at']}")
    st.write(f"**FDAF submissions:** {s['fdaf_records']:,}  |  **Monitoring submissions:** {s['monitoring_records']:,}")
