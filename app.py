import streamlit as st
import pandas as pd
import requests
import re
from datetime import datetime

# Page Configuration
st.set_page_config(
    page_title="M&E Executive Field Console",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ M&E EXECUTIVE FIELD COMMAND CONSOLE")
st.markdown("**Complete Audit Hub:** Quality & Compliance Scorecards, Daily Productivity, Robust Logic Checks & Family Error Audits.")
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
    col_start = find_col(['start', 'start_time'])
    col_end = find_col(['end', 'end_time'])
    
    # Specific fields for robust logical checking
    col_age = find_col(['age', 'years_old'])
    col_edu = find_col(['education', 'grade', 'schooling', 'attainment'])
    col_status = find_col(['status', 'enrollment', 'currently_studying', 'school'])
    col_hh_size = find_col(['hh_size', 'household_size', 'total_members'])
    col_housing = find_col(['housing', 'house_type', 'dwelling'])
    col_school_kids = find_col(['school_aged_children', 'has_children_school'])

    # Standardize Metadata Safely
    df['Enumerator'] = df[col_enum] if col_enum else df.get('_submitted_by', 'Unknown Enumerator')
    df['Barangay'] = df[col_brgy] if col_brgy else 'Unassigned Brgy'
    df['Municipality'] = df[col_muni] if col_muni else 'Unassigned Municipality'
    df['HH ID'] = df[col_family] if col_family else df.get('_id', 'Unknown ID')
    df['Location_Key'] = df[col_loc] if col_loc else df['Barangay']

    df['Shared_Location_Count'] = df['Location_Key'].map(df['Location_Key'].value_counts().to_dict())
    df['Duplicate_HH_Count'] = df['HH ID'].map(df['HH ID'].value_counts().to_dict())

    # Timestamp handling
    if "_submission_time" in df.columns:
        df['Parsed_Timestamp'] = pd.to_datetime(df["_submission_time"], errors='coerce')
        df["Survey Date"] = df['Parsed_Timestamp'].dt.date
        df["Submission Hour"] = df['Parsed_Timestamp'].dt.hour
    else:
        df["Survey Date"] = "Unknown Date"
        df["Submission Hour"] = 12

    # -------------------------------------------------------------
    # ROBUST M&E AUDIT ENGINE WITH SEVERITY ASSIGNMENT
    # -------------------------------------------------------------
    audit_results = []

    for idx, row in df.iterrows():
        errors = []
        actual_data_summary = {}

        for c in df.columns:
            if not c.startswith('_') and pd.api.types.is_scalar(row.get(c)):
                val = row.get(c)
                if pd.notna(val) and str(val).strip() != "":
                    actual_data_summary[c] = val

        # 1. Interview Duration (Major)
        if col_start and col_end and pd.notna(row.get(col_start)) and pd.notna(row.get(col_end)):
            try:
                s_dt = pd.to_datetime(row[col_start])
                e_dt = pd.to_datetime(row[col_end])
                mins = (e_dt - s_dt).total_seconds() / 60.0
                if mins < 3.0:
                    errors.append({"Desc": f"Rushed Interview ({round(mins, 1)} mins)", "Severity": "MAJOR"})
            except Exception:
                pass

        # 2. Odd-Hour Submission (Critical)
        hour = row.get("Submission Hour", 12)
        if pd.notna(hour) and (hour >= 22 or hour <= 4):
            errors.append({"Desc": f"Odd-Hour Submission ({hour}:00 hrs - Late night)", "Severity": "CRITICAL"})

        # 3. GPS Overlap (Major)
        if row.get('Shared_Location_Count', 1) > 1:
            errors.append({"Desc": "GPS Overlap / Shared Coordinates", "Severity": "MAJOR"})

        # 4. Duplicate Household ID (Critical)
        if row.get('Duplicate_HH_Count', 1) > 1:
            errors.append({"Desc": "Duplicate Household ID submitted", "Severity": "CRITICAL"})

        # 5. Skip Logic Failure (Critical)
        if col_school_kids and col_edu and pd.notna(row.get(col_school_kids)):
            try:
                has_kids = str(row[col_school_kids]).lower()
                edu_val = row.get(col_edu)
                if any(no in has_kids for no in ['no', 'none', '0']) and pd.notna(edu_val) and str(edu_val).strip() != "":
                    errors.append({"Desc": "Skip Logic Failure: Education filled out with zero school-aged children", "Severity": "CRITICAL"})
            except Exception:
                pass

        # 6. Age vs Education Consistency Check (Critical)
        if col_age and col_edu and col_status and pd.notna(row.get(col_age)) and pd.notna(row.get(col_edu)):
            try:
                age_val = float(row[col_age])
                edu_str = str(row[col_edu]).lower()
                if age_val >= 25 and any(g in edu_str for g in ['grade 1', 'grade 2', 'elementary']):
                    errors.append({"Desc": f"Logical Conflict: Adult Age ({int(age_val)}) vs Elementary Schooling", "Severity": "CRITICAL"})
            except ValueError:
                pass

        # 7. Housing Outlier Check (Major)
        if col_hh_size and col_housing and pd.notna(row.get(col_hh_size)) and pd.notna(row.get(col_housing)):
            try:
                hh_size = float(row[col_hh_size])
                housing_str = str(row[col_housing]).lower()
                if hh_size >= 12 and any(h in housing_str for h in ['makeshift', 'tent', 'shanty']):
                    errors.append({"Desc": f"Economic Outlier: Large household ({int(hh_size)}) in makeshift structure", "Severity": "MAJOR"})
            except ValueError:
                pass

        # Log results
        if errors:
            for err in errors:
                audit_results.append({
                    "Survey Date": str(row.get("Survey Date", "")),
                    "Municipality": str(row.get("Municipality", "")),
                    "Barangay": str(row.get("Barangay", "")),
                    "Enumerator": str(row.get("Enumerator", "")),
                    "HH ID": str(row.get("HH ID", "")),
                    "Error Description": err["Desc"],
                    "Severity": err["Severity"],
                    "Actual Data Entered": str(actual_data_summary)
                })
        else:
            audit_results.append({
                "Survey Date": str(row.get("Survey Date", "")),
                "Municipality": str(row.get("Municipality", "")),
                "Barangay": str(row.get("Barangay", "")),
                "Enumerator": str(row.get("Enumerator", "")),
                "HH ID": str(row.get("HH ID", "")),
                "Error Description": "Clean Record",
                "Severity": "CLEAN",
                "Actual Data Entered": str(actual_data_summary)
            })

    audit_df = pd.DataFrame(audit_results)

    # -------------------------------------------------------------
    # SIDEBAR GLOBAL FILTERS
    # -------------------------------------------------------------
    st.sidebar.header("🔍 Global Field Filters")
    sel_muni = st.sidebar.selectbox("Filter Municipality:", ["All"] + sorted(df['Municipality'].dropna().unique().tolist()))
    sel_brgy = st.sidebar.selectbox("Filter Barangay:", ["All"] + sorted(df['Barangay'].dropna().unique().tolist()))
    sel_enum = st.sidebar.selectbox("Filter Enumerator:", ["All"] + sorted(df['Enumerator'].dropna().unique().tolist()))

    # Apply Filters
    filtered_raw = df.copy()
    filtered_audit = audit_df.copy()

    if sel_muni != "All":
        filtered_raw = filtered_raw[filtered_raw["Municipality"] == sel_muni]
        filtered_audit = filtered_audit[filtered_audit["Municipality"] == sel_muni]
    if sel_brgy != "All":
        filtered_raw = filtered_raw[filtered_raw["Barangay"] == sel_brgy]
        filtered_audit = filtered_audit[filtered_audit["Barangay"] == sel_brgy]
    if sel_enum != "All":
        filtered_raw = filtered_raw[filtered_raw["Enumerator"] == sel_enum]
        filtered_audit = filtered_audit[filtered_audit["Enumerator"] == sel_enum]

    flagged_errors = filtered_audit[filtered_audit["Severity"] != "CLEAN"]

    # Top Metrics Bar
    total_submits = len(filtered_raw)
    total_flagged = len(flagged_errors)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Surveys Submitted", total_submits)
    m2.metric("Total Flagged Errors", total_flagged)
    m3.metric("Active Enumerators", filtered_raw['Enumerator'].nunique())
    m4.metric("Active Locations", f"{filtered_raw['Barangay'].nunique()} Brgys")

    st.markdown("---")

    # -------------------------------------------------------------
    # STREAMLIT TABS LAYOUT
    # -------------------------------------------------------------
    tab_prod, tab_audit = st.tabs([
        "🛡️ 1. Quality & Compliance Scorecards & Productivity", 
        "📋 2. Master Family Error Audit & Coaching Desk"
    ])

    with tab_prod:
        st.subheader("🛡️ Enumerator Quality & Compliance Scorecards")
        st.markdown("Calculated using severity weighting: **Critical Errors** (skip-logic, odd hours, duplicates) dock 15 pts; **Major Errors** (rushed surveys, GPS overlaps) dock 5 pts.")

        if not filtered_raw.empty:
            # Aggregate counts per enumerator
            tot_surveys = filtered_raw.groupby("Enumerator").size().reset_index(name="Total Surveys")
            
            crit_counts = flagged_errors[flagged_errors["Severity"] == "CRITICAL"].groupby("Enumerator").size().reset_index(name="Critical Errors")
            maj_counts = flagged_errors[flagged_errors["Severity"] == "MAJOR"].groupby("Enumerator").size().reset_index(name="Major Errors")

            scorecard = pd.merge(tot_surveys, crit_counts, on="Enumerator", how="left").fillna(0)
            scorecard = pd.merge(scorecard, maj_counts, on="Enumerator", how="left").fillna(0)

            # Compliance Score Formula
            scorecard['Compliance Score (%)'] = (100 - (((scorecard['Critical Errors'] * 15) + (scorecard['Major Errors'] * 5)) / scorecard['Total Surveys'].replace(0, 1))).clip(0, 100).round(1)
            scorecard['Status Rating'] = scorecard['Compliance Score (%)'].apply(lambda s: 'High 🟢' if s >= 85 else ('Moderate 🟡' if s >= 70 else 'Low / Needs Coaching 🔴'))

            st.dataframe(
                scorecard[["Enumerator", "Total Surveys", "Critical Errors", "Major Errors", "Compliance Score (%)", "Status Rating"]].sort_values(by="Compliance Score (%)", ascending=True),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No records match the current filter selection.")

        st.markdown("---")
        st.markdown("#### 📅 Daily Survey Productivity per Enumerator & Location")
        prod_summary = filtered_raw.groupby(["Municipality", "Barangay", "Enumerator", "Survey Date"]).size().reset_index(name="Surveys Completed")
        st.dataframe(prod_summary.sort_values(by="Survey Date", ascending=False), use_container_width=True, hide_index=True)

    with tab_audit:
        st.subheader("Master Family Error Table & Actual Data Entered")
        st.markdown("Review the exact HH ID, Enumerator, Date, Severity, Error Description, and Actual Data Entered for rapid coaching.")

        if not flagged_errors.empty:
            st.dataframe(
                flagged_errors[["Survey Date", "Municipality", "Barangay", "Enumerator", "HH ID", "Severity", "Error Description", "Actual Data Entered"]],
                use_container_width=True,
                hide_index=True
            )

            # CSV Download Button
            csv_data = flagged_errors.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Master Error & Actual Data Table (CSV)",
                data=csv_data,
                file_name=f"master_quality_compliance_audit_{datetime.now().strftime('%Y-%m-%d')}.csv",
                mime='text/csv'
            )
        else:
            st.success("✅ Clean! No family errors or compliance issues found under current filters.")

else:
    st.warning("⚠️ No records loaded. Please verify your Kobo token connection.")
