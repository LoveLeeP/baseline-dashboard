import streamlit as st
import pandas as pd
import requests
import re

# Page Configuration
st.set_page_config(
    page_title="BASELINE M&E SPECIALIST HUB",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ BASELINE M&E AUDIT & COMPLIANCE HUB")
st.markdown("**Specialist Inspector Console:** Quality Scoring, Daily Productivity & Granular Error Audit Log")
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
    col_brgy = find_col(['brgy', 'barangay', 'village'])
    col_muni = find_col(['muni', 'municipality', 'town', 'city'])
    col_family = find_col(['family', 'household', 'hh_name', 'respondent', 'head_name'])
    col_age = find_col(['age', 'years_old'])
    col_edu = find_col(['education', 'grade', 'schooling', 'attainment'])

    # Standardize Metadata Columns safely
    df['Enumerator'] = df[col_enum] if col_enum else df.get('_submitted_by', 'Unknown Enumerator')
    df['Barangay'] = df[col_brgy] if col_brgy else 'Unassigned Brgy'
    df['Municipality'] = df[col_muni] if col_muni else 'Unassigned Municipality'
    df['Family'] = df[col_family] if col_family else df.get('_id', 'Unknown Family')

    # -------------------------------------------------------------
    # RULE-BASED ANOMALY & ERROR DETECTION ENGINE
    # -------------------------------------------------------------
    def audit_row_data(row):
        errors = []
        
        # 1. Logical Inconsistency Check (CRITICAL) - e.g., Age vs Grade
        if col_age and col_edu and pd.notna(row.get(col_age)) and pd.notna(row.get(col_edu)):
            try:
                age_val = float(row[col_age])
                edu_str = str(row[col_edu]).lower()
                if age_val > 25 and any(g in edu_str for g in ['grade 1', 'grade 2', 'grade 3', 'grade 4', 'grade 5', 'grade 6', 'elem']):
                    errors.append({
                        "Question/Field": f"{col_age} vs {col_edu}",
                        "Error Description": f"Logical Contradiction: Age ({int(age_val)} yrs) vs Education ({row[col_edu]})",
                        "Severity": "CRITICAL"
                    })
            except ValueError:
                pass

        # 2. Name Format Check (MAJOR)
        if col_family and pd.notna(row.get(col_family)):
            fam_name = str(row[col_family]).strip()
            if len(fam_name) < 3 or fam_name.isdigit() or re.search(r'[^a-zA-Z\s\.\-]', fam_name):
                errors.append({
                    "Question/Field": col_family,
                    "Error Description": f"Name Format Error / Suspicious Entry: '{fam_name}'",
                    "Severity": "MAJOR"
                })

        # 3. Scan for Flagged Remarks / Discrepancies in Form Fields
        for col in row.index:
            if any(k in col.lower() for k in ['error', 'flag', 'discrepancy', 'remark', 'note', 'comment']):
                val = row.get(col)
                if pd.notna(val) and str(val).strip() != "" and str(val).lower() not in ['none', 'no error', 'ok', 'clean', 'n/a']:
                    errors.append({
                        "Question/Field": col,
                        "Error Description": str(val),
                        "Severity": "MAJOR" if "error" in col.lower() or "flag" in col.lower() else "MINOR"
                    })

        if not errors:
            return [{
                "Question/Field": "N/A",
                "Error Description": "No error detected (Clean)",
                "Severity": "CLEAN"
            }]
        return errors

    # Run audit engine
    audit_results = []
    for idx, row in df.iterrows():
        row_errors = audit_row_data(row)
        for err in row_errors:
            audit_results.append({
                "_source_form": row.get("_source_form", ""),
                "_id": row.get("_id", ""),
                "Municipality": row.get("Municipality", ""),
                "Barangay": row.get("Barangay", ""),
                "Enumerator": row.get("Enumerator", ""),
                "Family": row.get("Family", ""),
                "_submission_time": row.get("_submission_time", ""),
                "Question/Field": err["Question/Field"],
                "Error Description": err["Error Description"],
                "Severity": err["Severity"]
            })

    audit_df = pd.DataFrame(audit_results)

    # -------------------------------------------------------------
    # CLEAN TABBED LAYOUT (No Sidebar Filters)
    # -------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Executive Summary", 
        "🏆 Enumerator Scorecards", 
        "📅 Daily Productivity", 
        "🚨 Granular Error Audit Log"
    ])

    with tab1:
        st.markdown("### 📊 Executive Overview & Form Submission Volumes")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Records Extracted", len(df))
        c2.metric("Critical Errors 🚨", len(audit_df[audit_df["Severity"] == "CRITICAL"]))
        c3.metric("Major Errors ⚠️", len(audit_df[audit_df["Severity"] == "MAJOR"]))
        c4.metric("Minor Errors ℹ️", len(audit_df[audit_df["Severity"] == "MINOR"]))
        c5.metric("Clean Submissions ✅", len(audit_df[audit_df["Severity"] == "CLEAN"]))

        st.markdown("---")
        st.markdown("#### Submission Count per FDAF Form")
        counts_df = pd.DataFrame(list(form_counts.items()), columns=["Form Name", "Total Submissions"])
        st.dataframe(counts_df, use_container_width=True, hide_index=True)

    with tab2:
        st.markdown("### 🏆 Enumerator Quality, Compliance, Integrity & Confidence Scorecard")
        st.caption("Performance metrics per enumerator calculated from error severity ratios across all submitted surveys.")

        enum_summary = audit_df.groupby(["Municipality", "Barangay", "Enumerator"]).agg(
            Total_Surveys=('_id', 'nunique'),
            Critical_Count=('Severity', lambda x: (x == 'CRITICAL').sum()),
            Major_Count=('Severity', lambda x: (x == 'MAJOR').sum()),
            Minor_Count=('Severity', lambda x: (x == 'MINOR').sum())
        ).reset_index()

        enum_summary['Quality Score (%)'] = ((1 - ((enum_summary['Critical_Count']*2 + enum_summary['Major_Count']) / (enum_summary['Total_Surveys']*2).replace(0, 1))) * 100).clip(0, 100).round(1)
        enum_summary['Compliance (%)'] = enum_summary['Quality Score (%)']
        enum_summary['Data Integrity (%)'] = enum_summary['Quality Score (%)']
        enum_summary['Confidence Rating'] = enum_summary['Quality Score (%)'].apply(lambda s: 'High 🟢' if s >= 85 else ('Moderate 🟡' if s >= 70 else 'Low / Needs Review 🔴'))

        st.dataframe(
            enum_summary[[
                "Municipality", "Barangay", "Enumerator", "Total_Surveys", 
                "Critical_Count", "Major_Count", "Quality Score (%)", 
                "Compliance (%)", "Data Integrity (%)", "Confidence Rating"
            ]].sort_values(by="Quality Score (%)", ascending=True),
            use_container_width=True,
            hide_index=True
        )

    with tab3:
        st.markdown("### 📅 Daily Survey Productivity per Enumerator & Location")
        st.caption("Day-to-day breakdown of survey volume conducted across Barangays and Municipalities.")
        
        time_col = "_submission_time" if "_submission_time" in df.columns else None
        if time_col:
            df["Survey Date"] = pd.to_datetime(df[time_col]).dt.date
            prod_table = df.groupby(["Municipality", "Barangay", "Enumerator", "Survey Date"]).size().reset_index(name="Surveys Completed")
            st.dataframe(prod_table.sort_values(by="Survey Date", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("Submission timestamp metadata unavailable.")

    with tab4:
        st.markdown("### 🚨 Granular Error Audit Log & Question-Level Discrepancies")
        st.caption("Line-item audit trail detailing exact errors, severity levels, questions, families, and responsible enumerators.")

        display_columns = [
            "Severity", "Question/Field", "Error Description", 
            "Family", "Enumerator", "Barangay", "Municipality", "_source_form", "_submission_time"
        ]
        st.dataframe(audit_df[display_columns], use_container_width=True, hide_index=True)

else:
    st.warning("⚠️ No records loaded. Please verify your Kobo token connection.")
