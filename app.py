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

# Function to fetch assets / data from Kobo API
@st.cache_data(ttl=300)
def fetch_kobo_data():
    headers = {"Authorization": f"Token {KOBO_TOKEN}"}
    assets_url = f"https://{KOBO_SERVER}/api/v2/assets.json"
    
    response = requests.get(assets_url, headers=headers)
    if response.status_code != 200:
        st.error(f"Error fetching data from Kobo (Status Code: {response.status_code})")
        return None
    
    data = response.json()
    return data.get("results", [])

raw_data = fetch_kobo_data()

if raw_data:
    df = pd.DataFrame(raw_data)

    # -------------------------------------------------------------
    # SIDEBAR: FILTERS AND SELECTORS
    # -------------------------------------------------------------
    st.sidebar.header("🔍 Data Filters")

    # Filter 1: Project / Asset Name Selector
    project_names = df["name"].dropna().unique().tolist() if "name" in df.columns else []
    selected_projects = st.sidebar.multiselect(
        "Select Project(s):",
        options=project_names,
        default=project_names
    )

    # Filter 2: Asset Type Filter
    if "asset_type" in df.columns:
        asset_types = df["asset_type"].dropna().unique().tolist()
        selected_types = st.sidebar.multiselect(
            "Select Asset Type:",
            options=asset_types,
            default=asset_types
        )
    else:
        selected_types = None

    # Filter 3: Search Query
    search_query = st.sidebar.text_input("Search Projects/Forms:", "")

    # Apply Filters to DataFrame
    filtered_df = df.copy()

    if selected_projects:
        filtered_df = filtered_df[filtered_df["name"].isin(selected_projects)]

    if selected_types and "asset_type" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["asset_type"].isin(selected_types)]

    if search_query:
        filtered_df = filtered_df[
            filtered_df["name"].astype(str).str.contains(search_query, case=False, na=False)
        ]

    # -------------------------------------------------------------
    # DASHBOARD BODY
    # -------------------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.info(f"Showing **{len(filtered_df)}** of **{len(df)}** total items.")

    # High-level Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Projects", len(df))
    col2.metric("Filtered View", len(filtered_df))
    col3.metric("Active Server", KOBO_SERVER)

    st.markdown("### 📋 Survey & Project Overview")

    # Display columns safely
    display_cols = [col for col in ["name", "asset_type", "date_created", "date_modified", "submissions_count"] if col in filtered_df.columns]
    if display_cols:
        st.dataframe(filtered_df[display_cols], use_container_width=True)
    else:
        st.dataframe(filtered_df, use_container_width=True)

else:
    st.warning("No data retrieved from KoboToolbox.")
