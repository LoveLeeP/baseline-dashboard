import streamlit as st
import pandas as pd
import requests
import re
from datetime import datetime

# Page Configuration
st.set_page_config(
    page_title="BASELINE M&E INSPECTOR & COACHING HUB",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ BASELINE M&E INSPECTOR & DATA QUALITY HUB")
st.markdown("**Executive Console:** Roster Integrity, Odd-Hour & Duration Audits, GPS Overlaps, Duplicate IDs & Confidence %")
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

    # Dynamic Column Locator for M&E Metadata
    def find_col(keywords):
        for col in df.columns:
            if any(kw in col.lower() for kw in keywords):
                return col
        return None

    col_enum = find_col(['enumerator', 'enum', 'staff', 'user', 'interview_name'])
    col_role = find_col(['role', 'position', 'team_role'])
    col_brgy = find_col(['brgy', 'barangay', 'village'])
    col_muni = find_col(['muni', 'municipality', 'town', 'city'])
    col_family = find_col(['family', 'household', 'hh_name', 'respondent', 'head_name'])
    col_loc = find_col(['location', 'gps', 'geo', 'coordinates', 'lat', 'long'])
    col_start = find_col(['start', 'start_time', 'interview_start', 'submission_start'])
    col_end = find_col(['end', 'end_time', 'interview_end', 'submission_end'])
    
    # Specific fields for rigorous logical checking
    col_age = find_col(['age', 'years_old'])
    col_edu = find_col(['education', 'grade', 'schooling', 'attainment'])
    col_status = find_col(['status', 'enrollment', 'currently_studying', 'school'])
    col_gender = find_col(['gender', 'sex'])
    col_pregnant = find_col(['pregnant', 'pregnancy', 'lactating'])
    col_son_age = find_col(['son_age', 'child_age', 'dependents_age'])

    # Standardize Metadata Columns safely
    df['Enumerator'] = df[col_enum] if col_enum else df.get('_submitted_by', 'Unknown Enumerator')
    df['Role'] = df[col_role] if col_role else 'Field Enumerator'
    df['Barangay'] = df[col_brgy] if col_brgy else 'Unassigned Brgy'
    df['Municipality'] = df[col_muni] if col_muni else 'Unassigned Municipality'
    df['Family'] = df[col_family] if col_family else df.get('_id', 'Unknown Family')
    df['Location_Key'] = df[col_loc] if col_loc else df['Barangay']

    # Pre-calculate Location/GPS Overlaps
    loc_counts = df['Location_Key'].value_counts().to_dict()
    df['Shared_Location_Count'] = df['Location_Key'].map(loc_counts)

    # Pre-calculate Duplicate Household IDs
    family_counts = df['Family'].value_counts().to_dict()
    df['Duplicate_Family_Count'] = df['Family'].map(family_counts)
    
    # Format Survey Date & Extract Submission Hour for Odd-Hour Checks
    time_col = "_submission_time" if "_submission_time" in df.columns else None
    if time_col:
        df['Parsed_Timestamp'] = pd.to_datetime(df[time_col], errors='coerce')
        df["Survey Date"] = df['Parsed_Timestamp'].dt.date
        df["Submission Hour"] = df['Parsed_Timestamp'].dt.hour
    else:
        df["Survey Date"] = "Unknown Date"
        df["Submission Hour"] = 12

    # -------------------------------------------------------------
    # ADVANCED COMPREHENSIVE M&E AUDIT ENGINE
    # -------------------------------------------------------------
    def audit_row_data(row):
        errors = []
        
        # 1. Time-Motion / Duration Check
        if col_start and col_end and pd.notna(row.get(col_start)) and pd.notna(row.get(col_end)):
            try:
                start_dt = pd.to_datetime(row[col_start])
                end_dt = pd.to_datetime(row[col_end])
                duration_mins = (end_dt - start_dt).total_seconds() / 60.0
                if duration_mins < 0:
                    errors.append({
                        "Question/Field": "Timestamp",
                        "Error Description": "Timestamp Contradiction (End precedes start)",
                        "Severity": "CRITICAL"
                    })
                elif duration_mins < 3.0:
                    errors.append({
                        "Question/Field": "Interview Duration",
                        "Error Description": f"Rushed Survey ({round(duration_mins, 1)} mins)",
                        "Severity": "MAJOR"
                    })
            except Exception:
                pass

        # 2. Odd-Hour Submission Audit (Late Night Back-filling detection)
        sub_hour = row.get("Submission Hour", 12)
        if pd.notna(sub_hour) and (sub_hour >= 22 or sub_hour <= 4): # Between 10 PM and 4 AM
            errors.append({
                "Question/Field": "Submission Timestamp",
                "Error Description": f"Odd-Hour Submission ({sub_hour}:00 hrs - Potential late-night back-filling)",
                "Severity": "CRITICAL"
            })

        # 3. GPS / Location Overlap Check (Pencil-whipping detection)
        loc_val = row.get('Location_Key')
        overlap_num = row.get('Shared_Location_Count', 1)
        if overlap_num > 1 and pd.notna(loc_val):
            errors.append({
                "Question/Field": "GPS Location",
                "Error Description": f"GPS Overlap (Shared with {overlap_num - 1} other forms)",
                "Severity": "MAJOR"
            })

        # 4. Duplicate Household ID Check
        dup_count = row.get('Duplicate_Family_Count', 1)
        fam_id = row.get('Family', 'Unknown')
        if dup_count > 1 and fam_id != 'Unknown Family':
            errors.append({
                "Question/Field": "Household ID",
                "Error Description": f"Duplicate Household ID (Submitted {dup_count} times)",
                "Severity": "CRITICAL"
            })

        # 5. Name Format Validation Rule
        if col_family and pd.notna(row.get(col_family)):
            fam_str = str(row[col_family]).strip()
            if len(fam_str) < 2 or fam_str.isdigit() or re.search(r'[^a-zA-Z\s\.\-]', fam_str):
                errors.append({
                    "Question/Field": "Respondent Name",
                    "Error Description": f"Invalid Name Format ('{fam_str}')",
                    "Severity": "MAJOR"
                })

        # 6. HOUSEHOLD & CROSS-QUESTION LOGIC CONSISTENCY CHECKS
        
        # Check A: Head Age vs. Elementary Grade & Studying Status
        if col_age and col_edu and col_status and pd.notna(row.get(col_age)) and pd.notna(row.get(col_edu)) and pd.notna(row.get(col_status)):
            try:
                age_val = float(row[col_age])
                edu_str = str(row[col_edu]).lower()
                status_str = str(row[col_status]).lower()
                
                if age_val >= 25 and any(g in edu_str for g in ['grade 1', 'grade 2', 'grade 3', 'grade 4', 'grade 5', 'grade 6', 'elementary']) and any(s in status_str for s in ['yes', 'studying', 'current', 'enrolled']):
                    errors.append({
                        "Question/Field": "Age vs Education",
                        "Error Description": f"Adult Age ({int(age_val)}) conflicts with studying in elementary ({row[col_edu]})",
                        "Severity": "CRITICAL"
                    })
            except ValueError:
                pass

        # Check B: Impossible Parent-Child Age Gap
        if col_age and col_son_age and pd.notna(row.get(col_age)) and pd.notna(row.get(col_son_age)):
            try:
                parent_age = float(row[col_age])
                son_age = float(row[col_son_age])
                age_difference = parent_age - son_age
                
                if age_difference < 14:
                    errors.append({
                        "Question/Field": "Parent vs Child Age",
                        "Error Description": f"Impossible Age Gap ({int(age_difference)} yrs between parent & child)",
                        "Severity": "CRITICAL"
                    })
            except ValueError:
                pass

        # Check C: Biological Gender vs. Pregnancy Condition
        if col_gender and col_pregnant and pd.notna(row.get(col_gender)) and pd.notna(row.get(col_pregnant)):
            try:
                gender_str = str(row[col_gender]).lower()
                preg_str = str(row[col_pregnant]).lower()
                
                if any(m in gender_str for m in ['male', 'm', 'boy']) and any(p in preg_str for p in ['yes', 'pregnant', 'expecting', 'lactating', 'true']):
                    errors.append({
                        "Question/Field": "Gender vs Pregnancy",
                        "Error Description": "Biological Contradiction (Male marked as pregnant/lactating)",
                        "Severity": "CRITICAL"
                    })
            except Exception:
                pass

        if not errors:
            return [{
                "Question/Field": "N/A",
                "Error Description": "Clean record",
                "Severity": "CLEAN"
            }]
        return errors

    # Run audit across all records safely
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
    # SIDEBAR FILTERS
    # -------------------------------------------------------------
    st.sidebar.header("🔍 M&E Dashboard Filters")
    selected_muni = st.sidebar.selectbox("Filter Municipality:", ["All Municipalities"] + sorted(df['Municipality'].dropna().unique().tolist()))
    selected_brgy = st.sidebar.selectbox("Filter Barangay:", ["All Barangays"] + sorted(df['Barangay'].dropna().unique().tolist()))
    selected_enum = st.sidebar.selectbox("Filter Enumerator:", ["All Enumerators"] + sorted(df['Enumerator'].dropna().unique().tolist()))

    filtered_audit_df = audit_df.copy()
    if selected_muni != "All Municipalities":
        filtered_audit_df = filtered_audit_df[filtered_audit_df["Municipality"] == selected_muni]
    if selected_brgy != "All Barangays":
        filtered_audit_df = filtered_audit_df[filtered_audit_df["Barangay"] == selected_brgy]
    if selected_enum != "All Enumerators":
        filtered_audit_df = filtered_audit_df[filtered_audit_df["Enumerator"] == selected_enum]

    # -------------------------------------------------------------
    # TABS LAYOUT
    # -------------------------------------------------------------
    tab_daily, tab_quality, tab_integrity, tab_audit, tab_conf = st.tabs([
        "📅 Daily Survey", 
        "🛡️ Quality & Compliance", 
        "🔍 Data Integrity", 
        "📋 Audit Log",
        "🎯 Confidence %"
    ])

    with tab_daily:
        st.markdown("### 📅 Daily Survey Productivity per Enumerator")
        st.caption("Shows all enumerator names and their daily submission breakdown across all dates.")
        
        prod_df = df.copy()
        if selected_muni != "All Municipalities": prod_df = prod_df[prod_df["Municipality"] == selected_muni]
        if selected_brgy != "All Barangays": prod_df = prod_df[prod_df["Barangay"] == selected_brgy]
        if selected_enum != "All Enumerators": prod_df = prod_df[prod_df["Enumerator"] == selected_enum]

        daily_prod = prod_df.groupby(["Municipality", "Barangay", "Enumerator", "Survey Date"]).size().reset_index(name="Surveys Completed")
        st.dataframe(daily_prod.sort_values(by=["Survey Date", "Enumerator"], ascending=[False, True]), use_container_width=True, hide_index=True)

    with tab_quality:
        st.markdown("### 🛡️ Quality & Compliance Scorecards")
        st.caption("Overview of monitoring compliance, clean record ratios, and flag summaries per enumerator.")
        
        q_summary = filtered_audit_df.groupby(["Municipality", "Barangay", "Enumerator"]).agg(
            Total_Surveys=('Family / HH ID', 'nunique'),
            Critical_Errors=('Level of Error', lambda x: (x == 'CRITICAL').sum()),
            Major_Errors=('Level of Error', lambda x: (x == 'MAJOR').sum())
        ).reset_index()
        
        q_summary['Compliance Score (%)'] = ((1 - ((q_summary['Critical_Errors']*2 + q_summary['Major_Errors']) / (q_summary['Total_Surveys']*2).replace(0, 1))) * 100).clip(0, 100).round(1)
        st.dataframe(q_summary.sort_values(by="Compliance Score (%)", ascending=True), use_container_width=True, hide_index=True)

    with tab_integrity:
        st.markdown("### 🔍 Data Integrity (Household & Cross-Question Consistency)")
        st.caption("Expand any flagged survey to inspect exact household logic contradictions, odd-hour submissions, and GPS overlaps.")

        flagged_rows = filtered_audit_df[filtered_audit_df["Level of Error"] != "CLEAN"]
        if not flagged_rows.empty:
            for idx, row in flagged_rows.iterrows():
                with st.expander(f"[{row['Level of Error']}] HH ID: {row['Family / HH ID']} | Enumerator: {row['Enumerator']} ({row['Barangay']}, {row['Municipality']}) - {row['Survey Date']}"):
                    col_x, col_y = st.columns(2)
                    col_x.write(f"**Form Source:** {row['_source_form']}")
                    col_x.write(f"**Question / Field Flagged:** `{row['Question/Field']}`")
                    col_y.write(f"**Severity Level:** {row['Level of Error']}")
                    col_y.write(f"**Survey Date:** {row['Survey Date']}")
                    st.error(f"**Error Description:** {row['Error Description (Brief)']}")
        else:
            st.success("✅ No household or cross-section logic issues found within the selected filters!")

    with tab_audit:
        st.markdown("### 📋 Master Audit Log")
        st.caption("Clean, brief summary table of errors across all submissions for staff coaching.")
        
        st.dataframe(
            filtered_audit_df[["Survey Date", "Municipality", "Barangay", "Enumerator", "Family / HH ID", "Level of Error", "Error Description (Brief)"]],
            use_container_width=True,
            hide_index=True
        )

    with tab_conf:
        st.markdown("### 🎯 Enumerator Confidence Percentages")
        st.caption("Overall confidence ratings and percentage scores calculated per enumerator.")

        conf_summary = filtered_audit_df.groupby(["Municipality", "Barangay", "Enumerator"]).agg(
            Total_Surveys=('Family / HH ID', 'nunique'),
            Critical_Errors=('Level of Error', lambda x: (x == 'CRITICAL').sum()),
            Major_Errors=('Level of Error', lambda x: (x == 'MAJOR').sum())
        ).reset_index()

        conf_summary['Confidence (%)'] = ((1 - ((conf_summary['Critical_Errors']*2 + conf_summary['Major_Errors']) / (conf_summary['Total_Surveys']*2).replace(0, 1))) * 100).clip(0, 100).round(1)
        conf_summary['Rating'] = conf_summary['Confidence (%)'].apply(lambda s: 'High 🟢' if s >= 85 else ('Moderate 🟡' if s >= 70 else 'Low / Needs Review 🔴'))

        st.dataframe(
            conf_summary[[
                "Municipality", "Barangay", "Enumerator", "Total_Surveys", 
                "Critical_Errors", "Major_Errors", "Confidence (%)", "Rating"
            ]].sort_values(by="Confidence (%)", ascending=True),
            use_container_width=True,
            hide_index=True
        )

else:
    st.warning("⚠️ No records loaded. Please verify your Kobo token connection.")
