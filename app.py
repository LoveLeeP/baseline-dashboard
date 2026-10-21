import streamlit as st
import pandas as pd
import requests

# Page Configuration
st.set_page_config(
    page_title="BASELINE M&E DASHBOARD - FDAF",
    page_icon="📊",
    layout="wide"
)

st.title("📊 BASELINE M&E DASHBOARD (FDAF Project - Quality & Error Tracking)")
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

# Load data
raw_data, form_counts = fetch_all_fdaf_data()

# -------------------------------------------------------------
# SIDEBAR: CONTROLS & FILTERS
# -------------------------------------------------------------
st.sidebar.header("🔍 M&E Filter Controls")
selected_form_filter = st.sidebar.selectbox(
    "Filter by Form:",
    ["All Forms Combined"] + list(FDAF_ASSETS.keys())
)

search_query = st.sidebar.text_input("Search Records:", "")

# -------------------------------------------------------------
# MAIN DASHBOARD
# -------------------------------------------------------------
if raw_data:
    df = pd.DataFrame(raw_data)

    # Clean column names (strip group slashes)
    df.columns = [col.split('/')[-1] if '/' in col else col for col in df.columns]

    # Filter by form if selected
    if selected_form_filter != "All Forms Combined":
        df_filtered = df[df["_source_form"] == selected_form_filter].copy()
    else:
        df_filtered = df.copy()

    # Apply search filter if entered
    if search_query:
        mask = df_filtered.astype(str).apply(lambda x: x.str.contains(search_query, case=False, na=False)).any(axis=1)
        df_filtered = df_filtered[mask]

    # Top KPI Row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Submissions", len(df))
    col2.metric("Filtered View Count", len(df_filtered))
    col3.metric("Active Forms", len(FDAF_ASSETS))
    col4.metric("Server Status", "Connected 🟢")

    st.markdown("### 📋 Form Breakdown & Submission Volume")
    counts_df = pd.DataFrame(list(form_counts.items()), columns=["Form Name", "Total Submissions"])
    st.dataframe(counts_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # -------------------------------------------------------------
    # CONFIDENCE & QUALITY INDICATORS
    # -------------------------------------------------------------
    st.markdown("### 🎯 Confidence, Quality & Integrity Metrics")
    indicator_keywords = ['confid', 'qual', 'integ', 'score', 'rate', 'valid', 'compliance']
    indicator_cols = [c for c in df_filtered.columns if any(kw in c.lower() for kw in indicator_keywords)]
    
    if indicator_cols:
        ind_col1, ind_col2 = st.columns(2)
        with ind_col1:
            st.info(f"Detected Indicators: **{', '.join(indicator_cols)}**")
        primary_ind = indicator_cols[0]
        with ind_col2:
            st.write(f"**Breakdown for: `{primary_ind}`**")
            value_counts = df_filtered[primary_ind].value_counts().reset_index()
            value_counts.columns = [primary_ind, "Count"]
            st.dataframe(value_counts, hide_index=True, use_container_width=True)
    else:
        st.info("💡 Ensure survey forms include questions with keywords like 'confidence', 'quality', or 'score' to populate metrics here.")

    st.markdown("---")

    # -------------------------------------------------------------
    # SPECIFIC ERRORS PER FAMILY DISAGGREGATED PER ENUMERATOR
    # -------------------------------------------------------------
    st.markdown("### 🚨 Error Disaggregation: Errors per Family by Enumerator")
    
    # Identify potential enumerator columns and family/respondent identification columns
    enum_cols = [c for c in df_filtered.columns if any(k in c.lower() for k in ['enumerator', 'enum', 'user', 'staff', 'submitted_by'])]
    family_cols = [c for c in df_filtered.columns if any(k in c.lower() for k in ['family', 'household', 'name', 'respondent', 'hh_id'])]
    error_cols = [c for c in df_filtered.columns if any(k in c.lower() for k in ['error', 'discrepancy', 'issue', 'flag', 'comment', 'note', 'remark'])]

    if enum_cols and family_cols:
        primary_enum = enum_cols[0]
        primary_family = family_cols[0]
        primary_error = error_cols[0] if error_cols else df_filtered.columns[0] # Fallback
        
        st.caption(using tracking fields: Enumerator=`{primary_enum}`, Family=`{primary_family}`, Error/Note=`{primary_error}`)
        
        # Group and pivot data
        error_summary = df_filtered[[primary_enum, primary_family, primary_error, "_source_form"]].dropna(subset=[primary_enum])
        st.dataframe(error_summary, use_container_width=True, hide_index=True)
    else:
        st.info("💡 To view granular error breakdowns by family and enumerator, ensure your Kobo forms contain identifier fields for enumerators (e.g., `enumerator_name`), families (e.g., `family_name`), and errors/remarks (e.g., `error_notes`).")

    st.markdown("---")

    # Daily Submission Trend
    st.markdown("### 📅 Daily Submission Activity")
    time_col = "_submission_time" if "_submission_time" in df_filtered.columns else None
    if time_col:
        try:
            df_filtered["date"] = pd.to_datetime(df_filtered[time_col]).dt.date
            daily_counts = df_filtered.groupby("date").size().reset_index(name="count")
            st.bar_chart(daily_counts.set_index("date"))
        except Exception:
            st.info("Submission timestamps could not be parsed into a daily chart.")
    else:
        st.info("No submission timestamp field found for daily aggregation.")

    # -------------------------------------------------------------
    # AUDIT LOG & COMPLIANCE TABLE
    # -------------------------------------------------------------
    st.markdown("### 🛡️ Audit Log & Metadata Compliance")
    audit_cols = [c for c in ["_source_form", "_id", "_submission_time", "_submitted_by", "_validation_status"] if c in df_filtered.columns]
    st.dataframe(df_filtered[audit_cols] if audit_cols else df_filtered, use_container_width=True)

else:
    st.warning("⚠️ No submission records found across the 4 FDAF forms yet.")
