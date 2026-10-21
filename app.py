import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# Page Configuration
st.set_page_config(
    page_title="M&E Field Coaching & Error Console",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ M&E FIELD COACHING & ERROR CONSOLE")
st.markdown("**Direct Action Hub:** Productivity, Enumerator Error Rates, and Family Error Audits.")
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

    # Safe Column Finder
    def find_col(keywords):
        for col in df.columns:
            if any(kw in col.lower() for kw in keywords):
                return col
        return None

    col_enum = find_col(['enumerator', 'enum', 'staff', 'user', 'interview_name'])
    col_brgy = find_col(['brgy', 'barangay', 'village'])
    col_muni = find_col(['muni', 'municipality', 'town', 'city'])
    col_family = find_col(['family', 'household', 'hh_name', 'respondent', 'head_name', 'name'])
    col_start = find_col(['start', 'start_time'])
    col_end = find_col(['end', 'end_time'])

    # Standardize Metadata Safely
    df['Enumerator'] = df[col_enum] if col_enum else df.get('_submitted_by', 'Unknown Enumerator')
    df['Barangay'] = df[col_brgy] if col_brgy else 'Unassigned Brgy'
    df['Municipality'] = df[col_muni] if col_muni else 'Unassigned Municipality'
    df['HH ID'] = df[col_family] if col_family else df.get('_id', 'Unknown ID')

    # Timestamp handling
    if "_submission_time" in df.columns:
        df['Parsed_Timestamp'] = pd.to_datetime(df["_submission_time"], errors='coerce')
        df["Survey Date"] = df['Parsed_Timestamp'].dt.date
    else:
        df["Survey Date"] = "Unknown Date"

    # -------------------------------------------------------------
    # SIMPLE & DIRECT QUALITY CHECK LOGIC
    # -------------------------------------------------------------
    audit_results = []

    for idx, row in df.iterrows():
        errors = []
        actual_data_summary = {}

        # Capture key entered data fields to display for coaching
        for c in df.columns:
            if not c.startswith('_') and pd.api.types.is_scalar(row.get(c)):
                val = row.get(c)
                if pd.notna(val) and str(val).strip() != "":
                    actual_data_summary[c] = val

        # 1. Check Duration (Speeding)
        if col_start and col_end and pd.notna(row.get(col_start)) and pd.notna(row.get(col_end)):
            try:
                s_dt = pd.to_datetime(row[col_start])
                e_dt = pd.to_datetime(row[col_end])
                mins = (e_dt - s_dt).total_seconds() / 60.0
                if mins < 3.0:
                    errors.append(f"Rushed Interview ({round(mins, 1)} mins)")
            except Exception:
                pass

        # 2. Check for missing critical identifiers
        if str(row.get('HH ID')) in ['Unknown ID', 'nan', '']:
            errors.append("Missing Household / Family ID")

        # If errors found, log them along with the actual data
        if errors:
            for err in errors:
                audit_results.append({
                    "Survey Date": str(row.get("Survey Date", "")),
                    "Municipality": str(row.get("Municipality", "")),
                    "Barangay": str(row.get("Barangay", "")),
                    "Enumerator": str(row.get("Enumerator", "")),
                    "HH ID": str(row.get("HH ID", "")),
                    "Error Description": err,
                    "Actual Data Entered": str(actual_data_summary)
                })

    audit_df = pd.DataFrame(audit_results)

    # -------------------------------------------------------------
    # DASHBOARD LAYOUT (2 TABS: PRODUCTIVITY & ERROR AUDIT)
    # -------------------------------------------------------------
    
    tab_prod, tab_audit = st.tabs(["📊 1. Productivity & Error Rates", "👨‍👩‍👧‍👦 2. Family Error & Coaching Audit Table"])

    with tab_prod:
        st.subheader("Daily Productivity & Enumerator Error Rates")
        
        col_p1, col_p2 = st.columns(2)
        
        with col_p1:
            st.markdown("#### 📅 Productivity per Enumerator, Brgy & Municipality")
            prod_summary = df.groupby(["Municipality", "Barangay", "Enumerator", "Survey Date"]).size().reset_index(name="Total Submissions")
            st.dataframe(prod_summary, use_container_width=True, hide_index=True)
            
        with col_p2:
            st.markdown("#### 📉 Enumerator Error Rates")
            if not audit_df.empty:
                enum_errors = audit_df.groupby("Enumerator").size().reset_index(name="Flagged Errors")
                total_sub = df.groupby("Enumerator").size().reset_index(name="Total Submissions")
                enum_merged = pd.merge(total_sub, enum_errors, on="Enumerator", how="left").fillna(0)
                enum_merged["Error Rate (%)"] = (enum_merged["Flagged Errors"] / enum_merged["Total Submissions"] * 100).round(1)
                st.dataframe(enum_merged, use_container_width=True, hide_index=True)
            else:
                st.success("No errors found to calculate rates!")

    with tab_audit:
        st.subheader("Master Family Error & Actual Data Table")
        st.markdown("Review the exact HH ID, Enumerator, Error Description, and Actual Data Entered for coaching.")

        if not audit_df.empty:
            # Simple filters
            sel_enum = st.selectbox("Filter by Enumerator:", ["All"] + sorted(audit_df["Enumerator"].unique().tolist()))
            display_df = audit_df if sel_enum == "All" else audit_df[audit_df["Enumerator"] == sel_enum]

            st.dataframe(
                display_df[["Survey Date", "Municipality", "Barangay", "Enumerator", "HH ID", "Error Description", "Actual Data Entered"]],
                use_container_width=True,
                hide_index=True
            )

            # CSV Download
            csv_data = display_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Family Error Audit Table (CSV)",
                data=csv_data,
                file_name=f"family_error_audit_{datetime.now().strftime('%Y-%m-%d')}.csv",
                mime='text/csv'
            )
        else:
            st.success("✅ Clean! No errors detected across your submissions.")

else:
    st.warning("⚠️ No records loaded. Please check your KoBo token connection.")
