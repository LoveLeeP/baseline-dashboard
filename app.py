import streamlit as st
import pandas as pd
import requests

# Page Configuration
st.set_page_config(
    page_title="BASELINE M&E DASHBOARD - FDAF",
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

# Define your specific FDAF Asset UIDs
FDAF_ASSETS = {
    "Form 1 (a5X3VN...)": "a5X3VNtbTEARd7d9L6nvpt",
    "Form 2 (abG2xw...)": "abG2xw4Bv6Die7MZ6zZeM2",
    "Form 3 (a9a2wr...)": "a9a2wrGWJ565rgTkA8FxTN",
    "Form 4 (aoK7iX...)": "aoK7iXDNLmwbxPT2aiV9qq"
}

# Function to fetch submission data for specific assets
@st.cache_data(ttl=300)
def fetch_fdaf_submissions(asset_uid):
    headers = {"Authorization": f"Token {KOBO_TOKEN}"}
    url = f"https://{KOBO_SERVER}/api/v2/assets/{asset_uid}/data.json"
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("results", [])
    return []

# -------------------------------------------------------------
# SIDEBAR: SELECTOR FOR FDAF FORMS
# -------------------------------------------------------------
st.sidebar.header("🔍 FDAF Form Selector")
selected_form_name = st.sidebar.selectbox("Choose FDAF Form:", list(FDAF_ASSETS.keys()))
selected_uid = FDAF_ASSETS[selected_form_name]

# Fetch data for selected form
submissions = fetch_fdaf_submissions(selected_uid)

if submissions:
    df = pd.DataFrame(submissions)

    # High-level Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Selected Form", selected_form_name)
    col2.metric("Total Submissions", len(df))
    col3.metric("Active Server", KOBO_SERVER)

    st.markdown(f"### 📋 Survey Submissions: {selected_form_name}")

    # Optional Sidebar Search / Filter if data exists
    search_term = st.sidebar.text_input("Search in Submissions:", "")
    if search_term and not df.empty:
        mask = df.astype(str).apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)
        df_filtered = df[mask]
    else:
        df_filtered = df

    st.sidebar.info(f"Showing **{len(df_filtered)}** of **{len(df)}** records.")

    # Display data table
    st.dataframe(df_filtered, use_container_width=True)

else:
    st.info(f"No submission records found yet for **{selected_form_name}**, or the form is currently empty.")
