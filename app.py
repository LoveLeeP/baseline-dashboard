import streamlit as st
import pandas as pd
import requests

# Page Configuration
st.set_page_config(
    page_title="BASELINE M&E AUDIT & COMPLIANCE DASHBOARD",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ BASELINE M&E AUDIT & COMPLIANCE HUB")
st.markdown("**Executive M&E Inspector:** Data Integrity, Enumerator Productivity & Question-Level Error Disaggregation")
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

# Function to fetch submissions for all forms
@st.cache_data(ttl=300)
def fetch_all_fdaf_data():
    all_data = []
    form_summaries = {}
    
    for form_name, uid in FDAF_ASSETS.items():
        url = f"https://{KOBO_SERVER}/api/v2/assets/{uid}/data.json"
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                records = res.json().get("results", [])
                form_summaries[form_name] = len(records)
                for rec in records:
                    rec["_source_form"] = form_name
                    all_data.append(rec)
            else:
                form_summaries[form_name] = "Error (401/404)"
        except Exception as e:
            form_summaries[form_name] = f"Failed: {e}"
            
    return all_data, form_summaries

raw_data, form_counts = fetch_all_fdaf_data()

if raw_data:
    df = pd.DataFrame(raw_data)

    # Clean column names (strip group slashes)
    df.columns = [col.split('/')[-1] if '/' in col else col for col in df.columns]

    # Standardize or locate key auditing columns
    # We look for common naming patterns for Enumerator, Role, Barangay, Municipality, and Family
    def find_col(keywords):
        for col in df.columns:
            if any(kw in col.lower() for kw in keywords):
                return col
        return None

    col_enum = find_col(['enumerator', 'enum', 'staff', 'user', 'interview_name'])
    col_role = find_col(['role', 'position', 'team_role'])
    col_brgy = find_col(['brgy', 'barangay', 'village'])
    col_muni = find_col(['muni', 'municipality', 'town', 'city'])
    col_family = find_col(['family', 'household', 'hh_name', 'respondent', 'head'])
    col_error = find_col(['error', 'flag', 'issue', 'discrepancy', 'remark', 'comment'])

    # Fallback placeholders if specific columns aren't named standardly yet
    if not col_enum: df['Enumerator'] = df.get('_submitted_by', 'Unknown Enumerator')
    else: df['Enumerator'] = df[col_enum]

    if not col_role: df['Role'] = 'Field Enumerator'
    else: df['Role'] = df[col_role]

    if not col_brgy: df['Barangay'] = 'Unassigned Brgy'
    else: df['Barangay'] = df[col_brgy]

    if not col_muni: df['Municipality'] = 'Unassigned Municipality'
    else: df['Municipality'] = df[col_muni]

    if not col_family: df['Family'] = df.get('_id', 'Unknown Family')
    else: df['Family'] = df[col_family]

    # -------------------------------------------------------------
    # SIDEBAR: M&E MULTI-LAYER FILTERS
    # -------------------------------------------------------------
    st.sidebar.header("🔍 M&E Geographic & Personnel Filters")

    # Filter 1: Project / Form
    selected_form = st.sidebar.selectbox("Select Form Scope:", ["All Forms Combined"] + list(FDAF_ASSETS.keys()))

    # Filter 2: Municipality
    municipalities = ["All Municipalities"] + sorted(df['Municipality'].dropna().unique().tolist())
    selected_muni = st.sidebar.selectbox("Filter by Municipality:", municipalities)

    # Filter 3: Barangay
    barangays = ["All Barangays"] + sorted(df['Barangay'].dropna().unique().tolist())
    selected_brgy = st.sidebar.selectbox("Filter by Barangay:", barangays)

    # Filter 4: Role
    roles = ["All Roles"] + sorted(df['Role'].dropna().unique().tolist())
    selected_role = st.sidebar.selectbox("Filter by Role:", roles)

    # Filter 5: Enumerator Name
    enumerators = ["All Enumerators"] + sorted(df['Enumerator'].dropna().unique().tolist())
    selected_enum = st.sidebar.selectbox("Filter by Enumerator:", enumerators)

    # Apply Filters
    df_filtered = df.copy()
    if selected_form != "All Forms Combined":
        df_filtered = df_filtered[df_filtered["_source_form"] == selected_form]
    if selected_muni != "All Municipalities":
        df_filtered = df_filtered[df_filtered["Municipality"] == selected_muni]
    if selected_brgy != "All Barangays":
        df_filtered = df_filtered[df_filtered["Barangay"] == selected_brgy]
    if selected_role != "All Roles":
        df_filtered = df_filtered[df_filtered["Role"] == selected_role]
    if selected_enum != "All Enumerators":
        df_filtered = df_filtered[df_filtered["Enumerator"] == selected_enum]

    # -------------------------------------------------------------
    # M&E EXECUTIVE METRIC SUMMARY
    # -------------------------------------------------------------
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Surveys Logged", len(df_filtered))
    c2.metric("Active Enumerators", df_filtered['Enumerator'].nunique())
    c3.metric("Municipalities Covered", df_filtered['Municipality'].nunique())
    c4.metric("Barangays Covered", df_filtered['Barangay'].nunique())
    c5.metric("Data Audit Status", "Active 🟢")

    st.markdown("---")

    # -------------------------------------------------------------
    # 1. ENUMERATOR PRODUCTIVITY: DAILY SURVEYS PER ENUMERATOR, BRGY, MUNI
    # -------------------------------------------------------------
    st.markdown("### 📊 1. Enumerator Daily Productivity & Volume Tracking")
    
    time_col = "_submission_time" if "_submission_time" in df_filtered.columns else None
    if time_col:
        df_filtered["Survey Date"] = pd.to_datetime(df_filtered[time_col]).dt.date
        
        # Aggregate productivity table
        prod_table = df_filtered.groupby(["Municipality", "Barangay", "Enumerator", "Survey Date"]).size().reset_index(name="Surveys Completed")
        st.dataframe(prod_table.sort_values(by="Survey Date", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("Submission timestamp metadata is missing for daily trend graphing.")

    st.markdown("---")

    # -------------------------------------------------------------
    # 2. DATA INTEGRITY & QUESTION-LEVEL ERROR DISAGGREGATION
    # -------------------------------------------------------------
    st.markdown("### 🚨 2. Question-Level Error & Discrepancy Disaggregation")
    st.caption("Detailed breakdown mapping errors, anomalies, or flagged entries per family, enumerator, barangay, and municipality.")

    # Build structured compliance audit view
    audit_display_cols = [
        "_source_form", "Municipality", "Barangay", "Enumerator", "Role", "Family", 
        col_error if col_error else "_id", 
        "_submission_time", "_validation_status"
    ]
    # Keep only columns that actually exist in df_filtered
    audit_display_cols = [c for c in audit_display_cols if c in df_filtered.columns]

    st.dataframe(df_filtered[audit_display_cols], use_container_width=True, hide_index=True)

    # Summary pivot: Errors/Flags per Enumerator & Barangay
    st.markdown("### 📋 Audit Summary: Submissions by Enumerator & Location")
    summary_pivot = df_filtered.groupby(["Municipality", "Barangay", "Enumerator"]).size().reset_index(name="Total Submissions")
    st.dataframe(summary_pivot, use_container_width=True, hide_index=True)

else:
    st.warning("⚠️ No records loaded. Please verify Kobo token connection.")
