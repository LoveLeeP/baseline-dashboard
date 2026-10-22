"""FDAF Monitoring Dashboard  -  run with:  streamlit run app.py"""
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
    # Allows auto-login if the password is in the URL (e.g., from a QR code)
    query_params = st.query_params
    if "password" in query_params and hmac.compare_digest(query_params["password"], st.secrets["password"]):
        st.session_state["password_correct"] = True
        return True

    def password_entered():
        if hmac.compare_digest(st.session_state["password"], st.secrets["password"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Clear password from session state
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.text_input("🔒 Enter Password to Access Dashboard", type="password", on_change=password_entered, key="password")
    if "password_correct" in st.session_state:
        st.error("😕 Password incorrect. Please try again.")
    return False

if not check_password():
    st.stop()
# ---------------------------------

LEVEL_COLORS = {"High": "#c6efce", "Medium": "#ffeb9c", "Low": "#ffc7ce"}
SEV_COLORS = {"Critical": "#ffc7ce", "Major": "#ffeb9c", "Minor": "#ddebf7"}


def show_df(df, **kw):
    """st.dataframe that works on old and new Streamlit (use_container_width was replaced by width="stretch")."""
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
    st.download_button(f"Download {name}.csv", df.to_csv(index=False).encode("utf-8-sig"), f"{name}.csv", "text/csv")


# ---------------- sidebar ----------------
live_ready = _live_ready(cfg)
st.sidebar.title("FDAF Dashboard")
mode = st.sidebar.radio("Data source", ["Live (KoboToolbox)", "Demo data"], index=0 if live_ready else 1)
if mode.startswith("Live") and not live_ready:
    st.sidebar.warning("KOBO_TOKEN and/or the project UIDs are not set (see README, step 1). Showing demo data.")
    mode = "Demo data"
if st.sidebar.button("Refresh now"):
    st.cache_data.clear()
try:
    D = get_data(mode == "Demo data")
except Exception as exc:  # show a readable message instead of a stack trace
    import traceback
    st.error(f"Could not load data: {exc}")
    st.info("Run `python check_kobo.py` in the dashboard folder - it tests the token, the server and each project "
            "one by one and tells you exactly which one is failing.")
    with st.expander("Technical details (send this if you need help)"):
        st.code(traceback.format_exc())
    st.stop()

# ---- automatic refresh: re-run the app when the cache expires, so new Kobo submissions appear without clicking ----
if hasattr(st, "fragment") and mode.startswith("Live"):
    @st.fragment(run_every=f"{max(1, int(cfg.get('cache_minutes', 10)))}m")
    def _auto_refresh():
        if st.session_state.get("_auto_refresh_armed"):
            st.rerun()          # full re-run; get_data() re-pulls from Kobo because its cache has expired
        st.session_state["_auto_refresh_armed"] = True
    _auto_refresh()

hh, integ, flags, mon, items, enum, daily = (D[k] for k in ("hh", "integrity", "flags", "monitoring", "items", "enumerators", "daily"))
if hh.empty:
    st.info("No FDAF submissions yet.")
    st.stop()

dmin, dmax = hh["interview_date"].min().date(), hh["interview_date"].max().date()
dates = st.sidebar.date_input("Interview dates", (dmin, dmax), min_value=dmin, max_value=dmax)
d0, d1 = (dates if isinstance(dates, tuple) and len(dates) == 2 else (dmin, dmax))
titles = st.sidebar.multiselect("Role / title", sorted(hh["title"].dropna().unique()))
areas = st.
