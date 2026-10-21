import streamlit as st
import pandas as pd
import requests

# Page Configuration
st.set_page_config(
    page_title="BASELINE M&E DASHBOARD",
    page_icon="📊",
    layout="wide"
)

st.title("📊 BASELINE M&E DASHBOARD (FDAF Project)")
st.markdown("---")

# Retrieve secrets
KOBO_TOKEN = st.secrets.get("KOBO_TOKEN", "")
KOBO_SERVER = st.secrets.get("KOBO_SERVER", "kf.kobotoolbox.org")

if not KOBO_TOKEN:
    st.error("🔑 KOBO_TOKEN is missing in Streamlit Secrets. Please check Settings -> Secrets.")
    st.stop()

# Define your 4 specific FDAF Asset UIDs
FDAF_ASSETS = {
    "Form 1 (a5X3VN...)": "a5X3VNtbTEARd7d9L6nvpt",
    "Form 2 (abG2xw...)": "abG2xw4Bv6Die7MZ6zZeM2",
    "Form 3 (a9a2wr...)": "a9a2wrGWJ565rgTkA8FxTN",
    "Form 4 (aoK7iX...)": "aoK7iXDNLmwbxPT2aiV9qq"
}

headers = {"Authorization": f"Token {KOBO_TOKEN}"}

# Function to fetch ALL submission records with Pagination Handling (pulls 500+ records)
@st.cache_data(ttl=300)
def fetch_all_fdaf_data():
    all_data = []
    form_summaries = {}
    
    for form_name, uid in FDAF_ASSETS.items():
        start = 0
        limit = 1000
        form_records = []
        
        while True:
            url = f"https://{KOBO_SERVER}/api/v2/assets/{uid}/data.json?start={start}&limit={limit}"
            try:
                res = requests.get(url, headers=headers)
                if res.status_code == 200:
                    payload = res.json()
                    results = payload.get("results", [])
                    if not results:
                        break
                    for rec in results:
                        rec["_source_form"] = form_name
                        form_records.append(rec)
                    if len(results) < limit:
                        break
                    start += limit
                else:
                    break
            except Exception:
                break
                
        form_summaries[form_name] = len(form_records)
        all_data.extend(form_records)
            
    return all_data, form_summaries

raw_data, form_counts = fetch_all_fdaf_data()

if raw_data:
    df = pd.DataFrame(raw_data)

    # Clean column names (strip Kobo group slash prefixes)
    df.columns = [col.split('/')[-1] if '/' in col else col for col in df.columns]

    # High-level KPI Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Submissions (All 4 Forms)", len(df))
    c2.metric("Active Forms Tracked", len(FDAF_ASSETS))
    c3.metric("Server Status", "Connected 🟢")
    c4.metric("Active Server", KOBO_SERVER)

    st.markdown("### 📋 Submission Volume per Form")
    counts_df = pd.DataFrame(list(form_counts.items()), columns=["Form Name", "Total Submissions"])
    st.dataframe(counts_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # -------------------------------------------------------------
    # DAILY SURVEY PRODUCTIVITY TABLE
    # -------------------------------------------------------------
    st.markdown("### 📅 Daily Survey Productivity")
    time_col = "_submission_time" if "_submission_time" in df.columns else None
    if time_col:
        df["Survey Date"] = pd.to_datetime(df[time_col]).dt.date
        
        # Look for enumerator and location columns if available
        group_cols = ["Survey Date"]
        for col_candidate in ['Enumerator', 'enumerator', '_submitted_by', 'Barangay', 'brgy', 'Municipality']:
            if col_candidate in df.columns:
                group_cols.append(col_candidate)
                
        prod_table = df.groupby(group_cols).size().reset_index(name="Surveys Completed")
        st.dataframe(prod_table.sort_values(by="Survey Date", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("Submission timestamps unavailable.")

    st.markdown("---")

    # -------------------------------------------------------------
    # MASTER DATA & AUDIT LOG TABLE
    # -------------------------------------------------------------
    st.markdown("### 📂 Master Audit Log & Survey Records")
    st.dataframe(df, use_container_width=True)

else:
    st.warning("⚠️ No submission records found across the 4 FDAF forms yet.")
