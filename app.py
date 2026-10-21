import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# Page Configuration
st.set_page_config(
    page_title="M&E Master Quality Audit Hub",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ M&E MASTER QUALITY AUDIT HUB")
st.markdown("**Direct Action Console:** Single-view error tracking for rapid field coaching.")
st.markdown("---")

# Retrieve secrets
KOBO_TOKEN = st.secrets.get("KOBO_TOKEN", "")
KOBO_SERVER = st.secrets.get("KOBO_SERVER", "kf.kobotoolbox.org")

if not KOBO_TOKEN:
    st.error("🔑 KOBO_TOKEN is missing in Streamlit Secrets. Please check Settings -> Secrets.")
    st.stop()

# Define your 4 specific FDAF Asset UIDs
FDAF_ASSETS = {
    "Form 1": "a5X3VNtbTEARd7d9L6nvpt",
    "Form 2": "abG2xw4Bv6Die7MZ6zZeM2",
    "Form 3": "a9a2wrGWJ565rgTkA8FxTN",
    "Form 4": "aoK7iXDNLmwbxPT2aiV9qq"
}

headers = {"Authorization": f"Token {KOBO_TOKEN}"}

# Function to fetch ALL submission records with Pagination Handling
@st.cache_data(ttl=300)
def fetch_all_fdaf_data():
    all_data = []
    for form_name, uid in FDAF_ASSETS.items():
        start = 0
        limit = 1000
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
                        all_data.append(rec)
                    if len(results) < limit:
                        break
                    start += limit
                else:
                    break
            except Exception:
                break
    return all_data

raw_data = fetch_all_fdaf_data()

if raw_data:
    df = pd.DataFrame(raw_data)

    # Clean column names (strip Kobo group slash prefixes)
    df.columns = [col.split('/')[-1] if '/' in col else col for col in df.columns]

    # Flexible Column Finder
    def find_col(keywords):
        for col in df.columns:
            if any(kw in col.lower() for kw in keywords):
                return col
        return None

    col_enum = find_col(['enumerator', 'enum', 'staff', 'user', 'interview_name'])
    col_brgy = find_col(['brgy', 'barangay', 'village'])
    col_muni = find_col(['muni', 'municipality', 'town', 'city'])
    col_family = find_col(['family', 'household', 'hh_name', 'respondent', 'head_name', 'name'])
    col_loc = find_col(['location', 'gps', 'geo', 'coordinates', 'lat', 'long'])
    col_start = find_col(['start', 'start_time', 'submission_start'])
    col_end = find_col(['end', 'end_time', 'submission_end'])

    # Standardize Metadata Columns Safely
    df['Enumerator'] = df[col_enum] if col_enum else df.get('_submitted_by', 'Unknown Enumerator')
    df['Barangay'] = df[col_brgy] if col_brgy else 'Unassigned Brgy'
    df['Municipality'] = df[col_muni] if col_muni else 'Unassigned Municipality'
    df['Family / HH ID'] = df[col_family] if col_family else df.get('_id', 'Unknown ID')
    df['Location_Key'] = df[col_loc] if col_loc else df['Barangay']

    # Duplicate and Overlap metrics
    df['Shared_Location_Count'] = df['Location_Key'].map(df['Location_Key'].value_counts().to_dict())
    df['Duplicate_HH_Count'] = df['Family / HH ID'].map(df['Family / HH ID'].value_counts().to_dict())

    # Timestamp handling
    if "_submission_time" in df.columns:
        df['Parsed_Timestamp'] = pd.to_datetime(df["_submission_time"], errors='coerce')
        df["Survey Date"] = df['Parsed_Timestamp'].dt.date
        df["Submission Hour"] = df['Parsed_Timestamp'].dt.hour
    else:
        df["Survey Date"] = "Unknown Date"
        df["Submission Hour"] = 12

    # -------------------------------------------------------------
    # COMPREHENSIVE QUALITY AUDIT ENGINE
    # -------------------------------------------------------------
    audit_results = []

    for idx, row in df.iterrows():
        errors = []
        
        # 1. Check Duration / Speeding
        if col_start and col_end and pd.notna(row.get(col_start)) and pd.notna(row.get(col_end)):
            try:
                s_dt = pd.to_datetime(row[col_start])
                e_dt = pd.to_datetime(row[col_end])
                mins = (e_dt - s_dt).total_seconds() / 60.0
                if mins < 3.0:
                    errors.append(f"Rushed Survey (Completed in {round(mins, 1)} mins)")
                elif mins < 0:
                    errors.append("Timestamp Error (End time precedes start time)")
            except Exception:
                pass

        # 2. Odd-Hour Submission Check
        hour = row.get("Submission Hour", 12)
        if pd.notna(hour) and (hour >= 22 or hour <= 4):
            errors.append(f"Odd-Hour Submission ({hour}:00 hrs - Late night)")

        # 3. GPS Overlap Check
        if row.get('Shared_Location_Count', 1) > 1:
            errors.append(f"GPS Overlap (Shared coordinates with {row.get('Shared_Location_Count') - 1} other forms)")

        # 4. Duplicate Household ID Check
        if row.get('Duplicate_HH_Count', 1) > 1:
            errors.append("Duplicate Household ID (Same ID submitted multiple times)")

        # 5. General Missing Data Check (Scans all columns for blanks)
        blank_cols = [c for c in df.columns if pd.isna(row.get(c)) and not c.startswith('_')]
        if len(blank_cols) > 5:
            errors.append(f"High Incompleteness ({len(blank_cols)} blank fields detected)")

        # If errors found, log them
        if errors:
            for err in errors:
                audit_results.append({
                    "Survey Date": row.get("Survey Date", ""),
                    "Form": row.get("_source_form", ""),
                    "Municipality": row.get("Municipality", ""),
                    "Barangay": row.get("Barangay", ""),
                    "Enumerator": row.get("Enumerator", ""),
                    "HH ID": row.get("Family / HH ID", ""),
                    "Error Description": err
                })

    audit_df = pd.DataFrame(audit_results)

    # -------------------------------------------------------------
    # STREAMLIT UI: CLEAN MASTER TABLE
    # -------------------------------------------------------------
    
    # Sidebar Filters
    st.sidebar.header("🔍 Filter Master Audit")
    sel_muni = st.sidebar.selectbox("Filter Municipality:", ["All"] + sorted(df['Municipality'].dropna().unique().tolist()))
    sel_brgy = st.sidebar.selectbox("Filter Barangay:", ["All"] + sorted(df['Barangay'].dropna().unique().tolist()))
    sel_enum = st.sidebar.selectbox("Filter Enumerator:", ["All"] + sorted(df['Enumerator'].dropna().unique().tolist()))

    filtered_df = audit_df.copy()
    if sel_muni != "All":
        filtered_df = filtered_df[filtered_df["Municipality"] == sel_muni]
    if sel_brgy != "All":
        filtered_df = filtered_df[filtered_df["Barangay"] == sel_brgy]
    if sel_enum != "All":
        filtered_df = filtered_df[filtered_df["Enumerator"] == sel_enum]

    # Metrics Row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Raw Submissions", len(df))
    c2.metric("Total Flagged Errors", len(audit_df))
    c3.metric("Filtered Errors Shown", len(filtered_df))
    c4.metric("Active Enumerators", df['Enumerator'].nunique())

    st.markdown("---")
    st.markdown("### 📋 Master Quality Audit Table")
    st.markdown("Here is every flagged household, enumerator, date, and exact error description in one easy table.")

    if not filtered_df.empty:
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        
        # Download button for Excel/CSV
        csv_export = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Master Error Table as CSV",
            data=csv_export,
            file_name=f"master_quality_audit_{datetime.now().strftime('%Y-%m-%d')}.csv",
            mime='text/csv'
        )
    else:
        st.success("✅ Clean! No errors detected under the current filter selection.")

    with st.expander("🛠️ Debug: View Detected KoBo Column Mappings"):
        st.write(f"**Enumerator Column Detected:** `{col_enum}`")
        st.write(f"**Barangay Column Detected:** `{col_brgy}`")
        st.write(f"**Municipality Column Detected:** `{col_muni}`")
        st.write(f"**Family / HH ID Column Detected:** `{col_family}`")
        st.write(f"**GPS / Location Column Detected:** `{col_loc}`")

else:
    st.warning("⚠️ No records loaded. Please verify your Kobo token and Asset UIDs.")
