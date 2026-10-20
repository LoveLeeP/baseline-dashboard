import streamlit as st
import pandas as pd
import requests

# Page Configuration
st.set_page_config(
    page_title="BASELINE M&E DASHBOARD",
    page_icon="📊",
    layout="wide"
)

st.title("📊 BASELINE M&E DASHBOARD")
st.markdown("---")

# Retrieve secrets
KOBO_TOKEN = st.secrets.get("KOBO_TOKEN", "")
KOBO_SERVER = st.secrets.get("KOBO_SERVER", "kf.kobotoolbox.org")

if not KOBO_TOKEN:
    st.error("🔑 KOBO_TOKEN is missing in Streamlit Secrets. Please check Settings -> Secrets.")
    st.stop()

headers = {"Authorization": f"Token {KOBO_TOKEN}"}

# Cache 1: Get list of active forms/assets
@st.cache_data(ttl=180)
def fetch_kobo_assets():
    url = f"https://{KOBO_SERVER}/api/v2/assets/?asset_type=survey"
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return res.json().get("results", [])
        else:
            st.error(f"Error fetching forms list (Status Code: {res.status_code})")
            return []
    except Exception as e:
        st.error(f"Request failed: {e}")
        return []

# Cache 2: Fetch submission data for a given asset UID
@st.cache_data(ttl=180)
def fetch_asset_submissions(asset_uid):
    url = f"https://{KOBO_SERVER}/api/v2/assets/{asset_uid}/data/?format=json"
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return res.json().get("results", [])
        else:
            st.warning(f"Could not fetch submissions for form {asset_uid} (Status Code: {res.status_code})")
            return []
    except Exception as e:
        st.error(f"Failed to load data for {asset_uid}: {e}")
        return []

# Load all available forms
forms = fetch_kobo_assets()

if forms:
    # Build dictionary mapping Form Name -> UID
    form_map = {f.get("name", "Unnamed Form"): f.get("uid") for f in forms if f.get("uid")}

    # -------------------------------------------------------------
    # SIDEBAR: SELECTOR FOR ACTIVE FORM
    # -------------------------------------------------------------
    st.sidebar.header("🔍 Form Selection & Filters")
    selected_form_name = st.sidebar.selectbox("Select Survey Form:", list(form_map.keys()))
    selected_uid = form_map[selected_form_name]

    # Fetch submission data for selected form
    raw_submissions = fetch_asset_submissions(selected_uid)

    if raw_submissions:
        # Convert list of submission records to DataFrame
        df = pd.DataFrame(raw_submissions)

        # Clean column names (strip Kobo slash prefixes like 'group/question')
        df.columns = [col.split('/')[-1] if '/' in col else col for col in df.columns]

        # Top Metric Cards
        st.markdown(f"### 📋 Form: {selected_form_name}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Submissions", len(df))
        c2.metric("Total Fields", len(df.columns))
        c3.metric("Server", KOBO_SERVER)

        st.markdown("---")

        # Sidebar Search Bar
        search_query = st.sidebar.text_input("Search Submissions:")
        if search_query:
            mask = df.astype(str).apply(lambda row: row.str.contains(search_query, case=False, na=False)).any(axis=1)
            df_display = df[mask]
        else:
            df_display = df

        st.sidebar.info(f"Showing **{len(df_display)}** of **{len(df)}** records.")

        # Display Data Table
        st.dataframe(df_display, use_container_width=True)

    else:
        st.info(f"No submission records found for **{selected_form_name}**.")

else:
    st.warning("No survey forms found under this Kobo account token.")
