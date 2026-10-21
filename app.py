import streamlit as st
import pandas as pd
import requests
import re
from datetime import datetime

# Page Configuration
st.set_page_config(
    page_title="COMPREHENSIVE M&E COACHING & INSPECTOR HUB",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ M&E FIELD INSPECTION & ENUMERATOR COACHING HUB")
st.markdown("**Specialist & Staff Console:** Duration & Timestamp Overlaps, GPS Overlaps, Question Scrutiny & Coaching Proofs")
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
    col_age = find_col(['age', 'years_old'])
    col_edu = find_col(['education', 'grade', 'schooling', 'attainment'])

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

    # Helper function for text/language anomaly checks
    def check_text_anomaly(text):
        if not isinstance(text, str):
            return False, ""
        txt = text.strip()
        if len(txt) < 3:
            return False, ""
        if re.search(r'(.)\1{3,}', txt.lower()):
            return True, f"Keyboard Mashing / Repeated Characters ('{txt}')"
        if any(p in txt.lower() for p in ['asdf', 'qwer', 'zxcv', 'testtest', '123456', 'asdfgh', 'sample']):
            return True, f"Placeholder / Test String Detected ('{txt}')"
        if len(txt) > 5 and not re.search(r'[aeiouäöüéàèùñ]', txt.lower()):
            return True, f"Consonant Mashing / Unpronounceable Text ('{txt}')"
        if re.search(r'[\u0400-\u04FF\u4E00-\u9FFF\u0600-\u06FF\u3040-\u309F]', txt):
            return True, f"Unexpected Foreign Script / Character Set ('{txt}')"
        return False, ""

    # -------------------------------------------------------------
    # RIGOROUS M&E AUDIT & TIME-MOTION ENGINE (CRASH-PROOF)
    # -------------------------------------------------------------
    def audit_row_data(row):
        errors = []
        
        # 1. Start Time vs End Time & Duration Audit
        if col_start and col_end and pd.notna(row.get(col_start)) and pd.notna(row.get(col_end)):
            try:
                start_dt = pd.to_datetime(row[col_start])
                end_dt = pd.to_datetime(row[col_end])
                duration_mins = (end_dt - start_dt).total_seconds() / 60.0
                
                if duration_mins < 0:
                    errors.append({
                        "Question/Field": f"{col_start} vs {col_end}",
                        "Error Description": "Timestamp Contradiction: End time precedes start time (Negative duration).",
                        "Severity": "CRITICAL"
                    })
                elif duration_mins < 3.0:
                    errors.append({
                        "Question/Field": f"Interview Duration ({col_start} to {col_end})",
                        "Error Description": f"Rushed Survey Warning: Interview completed in an impossibly short duration ({round(duration_mins, 1)} minutes).",
                        "Severity": "MAJOR"
                    })
            except Exception:
                pass

        # 2. GPS / Location Overlap Check
        loc_val = row.get('Location_Key')
        overlap_num = row.get('Shared_Location_Count', 1)
        if overlap_num > 1 and pd.notna(loc_val):
            errors.append({
                "Question/Field": col_loc if col_loc else "GPS / Location Coordinates",
                "Error Description": f"Location Overlap Warning: Shares identical location/GPS coordinates with {overlap_num - 1} other family submission(s).",
                "Severity": "MAJOR"
            })

        # 3. Logical Inconsistency Check (Age vs Education)
        if col_age and col_edu and pd.notna(row.get(col_age)) and pd.notna(row.get(col_edu)):
            try:
                age_val = float(row[col_age])
                edu_str = str(row[col_edu]).lower()
                if age_val > 25 and any(g in edu_str for g in ['grade 1', 'grade 2', 'grade 3', 'grade 4', 'grade 5', 'grade 6', 'elem']):
                    errors.append({
                        "Question/Field": f"{col_age} vs {col_edu}",
                        "Error Description": f"Logical Contradiction: Age ({int(age_val)} yrs) conflicts with Education Level ({row[col_edu]})",
                        "Severity": "CRITICAL"
                    })
            except ValueError:
                pass

        # 4. Exhaustive Question Scrutiny (Safely Handling Lists/Dicts)
        for col in row.index:
            if col in ['_id', '_uuid', '_submission_time', '_submitted_by', '_source_form', 'Enumerator', 'Role', 'Barangay', 'Municipality', 'Family', 'Location_Key', 'Shared_Location_Count', 'Survey Date']:
                continue
            
            val = row.get(col)
            # Skip if value is a list, dict, or missing
            if val is None or isinstance(val, (list, dict)):
                continue
                
            col_lower = str(col).lower()
            
            try:
                if pd.notna(val) and str(val).strip() != "":
                    val_str = str(val).strip()
                    is_anomaly, anomaly_msg = check_text_anomaly(val_str)
                    if is_anomaly:
                        errors.append({
                            "Question/Field": str(col),
                            "Error Description": anomaly_msg,
                            "Severity": "CRITICAL"
                        })
                    elif any(k in col_lower for k in ['error', 'flag', 'discrepancy', 'remark', 'note', 'comment', 'issue']):
                        if val_str.lower() not in ['none', 'no error', 'ok', 'clean', 'n/a', '0', 'false', 'none.']:
                            errors.append({
                                "Question/Field": str(col),
                                "Error Description": f"Field Flag / Remark Recorded: {val_str}",
                                "Severity": "MAJOR" if "error" in col_lower or "flag" in col_lower else "MINOR"
                            })
            except Exception:
                continue

        if not errors:
            return [{
                "Question/Field": "All Fields",
                "Error Description": "Comprehensive Audit Passed: Clean of duration anomalies, GPS overlaps, and text errors.",
                "Severity": "CLEAN"
            }]
        return errors

    # Run audit across all records safely
    audit_results = []
    for idx, row in df.iterrows():
        row_errors = audit_row_data(row)
        for err in row_errors:
            audit_results.append({
                "_source_form": row.get("_source_form", ""),
                "_id": row.get("_id", ""),
                "Municipality": row.get("Municipality", ""),
                "Barangay": row.get("Barangay", ""),
                "Role": row.get("Role", ""),
                "Enumerator": row.get("Enumerator", ""),
                "Family": row.get("Family", ""),
                "_submission_time": row.get("_submission_time", ""),
                "Question/Field": err["Question/Field"],
                "Error Description": err["Error Description"],
                "Severity": err["Severity"]
            })

    audit_df = pd.DataFrame(audit_results)

    # -------------------------------------------------------------
    # SIDEBAR: M&E FIELD SCOPE FILTERS FOR STAFF COACHING
    # -------------------------------------------------------------
    st.sidebar.header("🔍 Staff Coaching & Inspection Filters")
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
    # DASHBOARD TABS
    # -------------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Daily Productivity & Volume", 
        "🏛️ Geographic Summaries (Brgy & Muni)", 
        "🏆 Enumerator Confidence Scorecards", 
        "🔍 Question Scrutiny & Coaching Proofs",
        "🚨 Master Audit Trail"
    ])

    with tab1:
        st.markdown("### 📊 Daily Survey Productivity per Enumerator")
        st.caption("Day-by-day throughput tracking across field staff and locations.")
        
        time_col = "_submission_time" if "_submission_time" in df.columns else None
        if time_col:
            df["Survey Date"] = pd.to_datetime(df[time_col]).dt.date
            prod_df = df.copy()
            if selected_muni != "All Municipalities": prod_df = prod_df[prod_df["Municipality"] == selected_muni]
            if selected_brgy != "All Barangays": prod_df = prod_df[prod_df["Barangay"] == selected_brgy]
            if selected_enum != "All Enumerators": prod_df = prod_df[prod_df["Enumerator"] == selected_enum]

            daily_prod = prod_df.groupby(["Municipality", "Barangay", "Enumerator", "Survey Date"]).size().reset_index(name="Surveys Completed")
            st.dataframe(daily_prod.sort_values(by="Survey Date", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("Submission timestamps unavailable.")

    with tab2:
        st.markdown("### 🏛️ Geographic Submissions Summary")
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.markdown("#### Submissions per Municipality")
            muni_summary = df.groupby("Municipality").size().reset_index(name="Total Surveys")
            st.dataframe(muni_summary, use_container_width=True, hide_index=True)

        with col_b:
            st.markdown("#### Submissions per Barangay")
            brgy_summary = df.groupby(["Municipality", "Barangay"]).size().reset_index(name="Total Surveys")
            st.dataframe(brgy_summary, use_container_width=True, hide_index=True)

    with tab3:
        st.markdown("### 🏆 Enumerator Confidence Level & Quality Scorecards")
        st.caption("Comprehensive rating per enumerator based on timestamp/duration flaws, GPS overlaps, logic contradictions, and text anomalies.")

        enum_summary = filtered_audit_df.groupby(["Municipality", "Barangay", "Role", "Enumerator"]).agg(
            Total_Surveys=('_id', 'nunique'),
            Critical_Errors=('Severity', lambda x: (x == 'CRITICAL').sum()),
            Major_Errors=('Severity', lambda x: (x == 'MAJOR').sum()),
            Minor_Errors=('Severity', lambda x: (x == 'MINOR').sum())
        ).reset_index()

        enum_summary['Confidence (%)'] = ((1 - ((enum_summary['Critical_Errors']*2 + enum_summary['Major_Errors']) / (enum_summary['Total_Surveys']*2).replace(0, 1))) * 100).clip(0, 100).round(1)
        enum_summary['Confidence Status'] = enum_summary['Confidence (%)'].apply(lambda s: 'High 🟢' if s >= 85 else ('Moderate 🟡' if s >= 70 else 'Low / Needs Review 🔴'))

        st.dataframe(
            enum_summary[[
                "Municipality", "Barangay", "Role", "Enumerator", "Total_Surveys", 
                "Critical_Errors", "Major_Errors", "Confidence (%)", "Confidence Status"
            ]].sort_values(by="Confidence (%)", ascending=True),
            use_container_width=True,
            hide_index=True
        )

    with tab4:
        st.markdown("### 🔍 Question Scrutiny & Staff Coaching Proofs")
        st.caption("Use these exact error proofs during staff coaching sessions to review timestamp overlaps, GPS clustering, and question discrepancies with enumerators.")

        flagged_rows = filtered_audit_df[filtered_audit_df["Severity"] != "CLEAN"]
        if not flagged_rows.empty:
            for idx, row in flagged_rows.iterrows():
                with st.expander(f"[{row['Severity']}] Family: {row['Family']} | Enumerator: {row['Enumerator']} ({row['Barangay']}, {row['Municipality']})"):
                    col_x, col_y = st.columns(2)
                    col_x.write(f"**Form Source:** {row['_source_form']}")
                    col_x.write(f"**Question / Field Scrutinized:** `{row['Question/Field']}`")
                    col_y.write(f"**Severity Level:** {row['Severity']}")
                    col_y.write(f"**Submission Time:** {row['_submission_time']}")
                    st.error(f"**Coaching Audit Proof / Description:** {row['Error Description']}")
        else:
            st.success("✅ All scrutinized submissions pass time-motion, GPS, and question quality standards within the selected filters!")

    with tab5:
        st.markdown("### 🚨 Master Granular Error Audit Trail")
        st.dataframe(
            filtered_audit_df[["Severity", "Question/Field", "Error Description", "Family", "Enumerator", "Barangay", "Municipality", "_submission_time"]],
            use_container_width=True,
            hide_index=True
        )

else:
    st.warning("⚠️ No records loaded. Please verify your Kobo token connection.")
