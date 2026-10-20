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
                    results = res.json().get("results", [])
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

    # Dynamic Column Locator for M&E Metadata
    def find_col(keywords):
        for col in df.columns:
            if any(kw in col.lower() for kw in keywords):
                return col
        return None

    col_enum = find_col(['enumerator', 'enum', 'staff', 'user', 'interview_name'])
    col_brgy = find_col(['brgy', 'barangay', 'village'])
    col_muni = find_col(['muni', 'municipality', 'town', 'city'])
    col_family = find_col(['family', 'household', 'hh_name', 'respondent', 'head_name'])

    # Standardize Metadata Columns safely
    df['Enumerator'] = df[col_enum] if col_enum else df.get('_submitted_by', 'Unknown Enumerator')
    df['Barangay'] = df[col_brgy] if col_brgy else 'Unassigned Brgy'
    df['Municipality'] = df[col_muni] if col_muni else 'Unassigned Municipality'
    df['Family'] = df[col_family] if col_family else df.get('_id', 'Unknown Family')

    # -------------------------------------------------------------
    # SIDEBAR: FILTERS
    # -------------------------------------------------------------
    st.sidebar.header("🔍 M&E Filters")

    selected_form = st.sidebar.selectbox("Select Form:", ["All Forms Combined"] + list(FDAF_ASSETS.keys()))
    
    municipalities = ["All Municipalities"] + sorted(df['Municipality'].dropna().unique().tolist())
    selected_muni = st.sidebar.selectbox("Municipality:", municipalities)

    barangays = ["All Barangays"] + sorted(df['Barangay'].dropna().unique().tolist())
    selected_brgy = st.sidebar.selectbox("Barangay:", barangays)

    enumerators = ["All Enumerators"] + sorted(df['Enumerator'].dropna().unique().tolist())
    selected_enum = st.sidebar.selectbox("Enumerator:", enumerators)

    search_query = st.sidebar.text_input("Search Records:", "")

    # Apply Filters
    df_filtered = df.copy()
    if selected_form != "All Forms Combined":
        df_filtered = df_filtered[df_filtered["_source_form"] == selected_form]
    if selected_muni != "All Municipalities":
        df_filtered = df_filtered[df_filtered["Municipality"] == selected_muni]
    if selected_brgy != "All Barangays":
        df_filtered = df_filtered[df_filtered["Barangay"] == selected_brgy]
    if selected_enum != "All Enumerators":
        df_filtered = df_filtered[df_filtered["Enumerator"] == selected_enum]
    if search_query:
        mask = df_filtered.astype(str).apply(lambda x: x.str.contains(search_query, case=False, na=False)).any(axis=1)
        df_filtered = df_filtered[mask]

    # -------------------------------------------------------------
    # KPI METRICS
    # -------------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Submissions (Loaded)", len(df))
    c2.metric("Filtered Records", len(df_filtered))
    c3.metric("Active Enumerators", df_filtered['Enumerator'].nunique())
    c4.metric("Barangays Covered", df_filtered['Barangay'].nunique())

    st.markdown("---")

    # Form Breakdown Summary Table
    st.markdown("### 📋 Submission Volume per Form")
    counts_df = pd.DataFrame(list(form_counts.items()), columns=["Form Name", "Total Submissions"])
    st.dataframe(counts_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # -------------------------------------------------------------
    # DAILY PRODUCTIVITY PER ENUMERATOR, BRGY, MUNICIPALITY
    # -------------------------------------------------------------
    st.markdown("### 📅 Daily Survey Productivity per Enumerator & Location")
    time_col = "_submission_time" if "_submission_time" in df_filtered.columns else None
    if time_col:
        df_filtered["Survey Date"] = pd.to_datetime(df_filtered[time_col]).dt.date
        prod_table = df_filtered.groupby(["Municipality", "Barangay", "Enumerator", "Survey Date"]).size().reset_index(name="Surveys Completed")
        st.dataframe(prod_table.sort_values(by="Survey Date", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("Submission timestamp metadata unavailable.")

    st.markdown("---")

    # -------------------------------------------------------------
    # MASTER SUBMISSION DATA TABLE
    # -------------------------------------------------------------
    st.markdown("### 📂 Master Survey Records")
    st.dataframe(df_filtered, use_container_width=True)

else:
    st.warning("⚠️ No records loaded. Please verify your Kobo token connection.")
