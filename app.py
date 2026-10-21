import streamlit as st
import pandas as pd
import requests
import re
from datetime import datetime

# Page Configuration
st.set_page_config(
    page_title="M&E Executive Coaching & Quality Console",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ M&E EXECUTIVE COACHING & QUALITY CONSOLE")
st.markdown("**Real-Time Field Command Center:** Daily Productivity, Enumerator Error Rates & Complete Family Error Dossiers")
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

# Function to fetch ALL submission records with Pagination Handling
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
    col_loc = find_col(['location', 'gps', 'geo', 'coordinates', 'lat', 'long'])
    col_start = find_col(['start', 'start_time', 'interview_start', 'submission_start'])
    col_end = find_col(['end', 'end_time', 'interview_end', 'submission_end'])
    
    # Specific fields for logical checking
    col_age = find_col(['age', 'years_old'])
    col_edu = find_col(['education', 'grade', 'schooling', 'attainment'])
    col_status = find_col(['status', 'enrollment', 'currently_studying', 'school'])
    col_gender = find_col(['gender', 'sex'])
    col_pregnant = find_col(['pregnant', 'pregnancy', 'lactating'])
    col_son_age = find_col(['son_age', 'child_age', 'dependents_age'])
    col_hh_size = find_col(['hh_size', 'household_size', 'total_members'])
    col_housing = find_col(['housing', 'house_type', 'dwelling'])
    col_school_kids = find_col(['school_aged_children', 'has_children_school'])

    # Standardize Metadata Columns safely
    df['Enumerator'] = df[col_enum] if col_enum else df.get('_submitted_by', 'Unknown Enumerator')
    df['Barangay'] = df[col_brgy] if col_brgy else 'Unassigned Brgy'
    df['Municipality'] = df[col_muni] if col_muni else 'Unassigned Municipality'
    df['Family'] = df[col_family] if col_family else df.get('_id', 'Unknown Family')
    df['Location_Key'] = df[col_loc] if col_loc else df['Barangay']

    loc_counts = df['Location_Key'].value_counts().to_dict()
    df['Shared_Location_Count'] = df['Location_Key'].map(loc_counts)

    family_counts = df['Family'].value_counts().to_dict()
    df['Duplicate_Family_Count'] = df['Family'].map(family_counts)
    
    time_col = "_submission_time" if "_submission_time" in df.columns else None
    if time_col:
        df['Parsed_Timestamp'] = pd.to_datetime(df[time_col], errors='coerce')
        df["Survey Date"] = df['Parsed_Timestamp'].dt.date
        df["Submission Hour"] = df['Parsed_Timestamp'].dt.hour
    else:
        df["Survey Date"] = "Unknown Date"
        df["Submission Hour"] = 12

    # -------------------------------------------------------------
    # M&E AUDIT ENGINE
    # -------------------------------------------------------------
    def audit_row_data(row):
        errors = []
        
        # 1. Duration Check
        if col_start and col_end and pd.notna(row.get(col_start)) and pd.notna(row.get(col_end)):
            try:
                start_dt = pd.to_datetime(row[col_start])
                end_dt = pd.to_datetime(row[col_end])
                duration_mins = (end_dt - start_dt).total_seconds() / 60.0
                if duration_mins < 3.0:
                    errors.append({
                        "Question/Field": "Interview Duration",
                        "Error Description": f"Rushed Survey ({round(duration_mins, 1)} mins)",
                        "Severity": "MAJOR"
                    })
            except Exception:
                pass

        # 2. Odd-Hour Submission
        sub_hour = row.get("Submission Hour", 12)
        if pd.notna(sub_hour) and (sub_hour >= 22 or sub_hour <= 4):
            errors.append({
                "Question/Field": "Submission Timestamp",
                "Error Description": f"Odd-Hour Submission ({sub_hour}:00 hrs)",
                "Severity": "CRITICAL"
            })

        # 3. GPS Overlap
        if row.get('Shared_Location_Count', 1) > 1:
            errors.append({
                "Question/Field": "GPS Location",
                "Error Description": "GPS Overlap / Shared Coordinates with another submission",
                "Severity": "MAJOR"
            })

        # 4. Duplicate Family ID
        if row.get('Duplicate_Family_Count', 1) > 1:
            errors.append({
                "Question/Field": "Household ID",
                "Error Description": "Duplicate Household ID detected",
                "Severity": "CRITICAL"
            })

        # 5. Skip Logic Failure
        if col_school_kids and col_edu and pd.notna(row.get(col_school_kids)):
            try:
                has_kids = str(row[col_school_kids]).lower()
                edu_val = row.get(col_edu)
                if any(no in has_kids for no in ['no', 'none', '0']) and pd.notna(edu_val) and str(edu_val).strip() != "":
                    errors.append({
                        "Question/Field": "Skip Logic: Education Module",
                        "Error Description": "Education module filled out despite reporting zero school-aged children",
                        "Severity": "CRITICAL"
                    })
            except Exception:
                pass

        # 6. Cross-Question Logic (Age vs Education)
        if col_age and col_edu and col_status and pd.notna(row.get(col_age)) and pd.notna(row.get(col_edu)):
            try:
                age_val = float(row[col_age])
                edu_str = str(row[col_edu]).lower()
                if age_val >= 25 and any(g in edu_str for g in ['grade 1', 'grade 2', 'elementary']):
                    errors.append({
                        "Question/Field": "Age vs Education",
                        "Error Description": f"Adult Age ({int(age_val)}) conflicts with elementary schooling",
                        "Severity": "CRITICAL"
                    })
            except ValueError:
                pass

        if not errors:
            return [{"Question/Field": "N/A", "Error Description": "Clean record", "Severity": "CLEAN"}]
        return errors

    audit_results = []
    for idx, row in df.iterrows():
        row_errors = audit_row_data(row)
        for err in row_errors:
            audit_results.append({
                "Survey Date": row.get("Survey Date", ""),
                "Municipality": row.get("Municipality", ""),
                "Barangay": row.get("Barangay", ""),
                "Enumerator": row.get("Enumerator", ""),
                "Family / HH ID": row.get("Family", ""),
                "Level of Error": err["Severity"],
                "Error Description (Brief)": err["Error Description"],
                "Question/Field": err["Question/Field"],
                "_source_form": row.get("_source_form", "")
            })

    audit_df = pd.DataFrame(audit_results)

    # -------------------------------------------------------------
    # SIDEBAR: GLOBAL FILTERS
    # -------------------------------------------------------------
    st.sidebar.header("🔍 Filter Field Data")
    selected_muni = st.sidebar.selectbox("Filter Municipality:", ["All Municipalities"] + sorted(df['Municipality'].dropna().unique().tolist()))
    selected_brgy = st.sidebar.selectbox("Filter Barangay:", ["All Barangays"] + sorted(df['Barangay'].dropna().unique().tolist()))
    selected_enum = st.sidebar.selectbox("Filter Enumerator:", ["All Enumerators"] + sorted(df['Enumerator'].dropna().unique().tolist()))

    filtered_audit_df = audit_df.copy()
    filtered_raw_df = df.copy()

    if selected_muni != "All Municipalities":
        filtered_audit_df = filtered_audit_df[filtered_audit_df["Municipality"] == selected_muni]
        filtered_raw_df = filtered_raw_df[filtered_raw_df["Municipality"] == selected_muni]
    if selected_brgy != "All Barangays":
        filtered_audit_df = filtered_audit_df[filtered_audit_df["Barangay"] == selected_brgy]
        filtered_raw_df = filtered_raw_df[filtered_raw_df["Barangay"] == selected_brgy]
    if selected_enum != "All Enumerators":
        filtered_audit_df = filtered_audit_df[filtered_audit_df["Enumerator"] == selected_enum]
        filtered_raw_df = filtered_raw_df[filtered_raw_df["Enumerator"] == selected_enum]

    # -------------------------------------------------------------
    # TOP EXECUTIVE METRICS BAR
    # -------------------------------------------------------------
    total_submits = len(filtered_raw_df)
    flagged_count = len(filtered_audit_df[filtered_audit_df["Level of Error"] != "CLEAN"]["Family / HH ID"].unique())
    overall_error_rate = round((flagged_count / total_submits * 100), 1) if total_submits > 0 else 0.0

    m
