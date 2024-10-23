import streamlit as st
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import folium_static
import plotly.express as px
import io
import os

# Page configuration
st.set_page_config(page_title="UNILEVER", page_icon="🌍", layout="wide")
st.header(":bar_chart: Unilever Dashboard")
st.markdown('<style>div.block-container{padding-top:2rem;}</style>', unsafe_allow_html=True)

# HTTP retries setup
session = requests.Session()
retry = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry)
session.mount('https://', adapter)

# Cache data to avoid multiple API calls
@st.cache_data
def download_kobo_data(api_url, headers, page=1):
    try:
        # Add pagination to handle large datasets
        response = session.get(f"{api_url}&page={page}", headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error while fetching data: {e}")
        return None

# API URL and authentication token
api_url = "https://kf.kobotoolbox.org/api/v2/assets/amfgmGRANPdTQgh85J7YqK/data/?format=json"
token = os.getenv("KOBO_API_TOKEN", "fd0239896ad338de0651fe082978bec82cc7dad4")  # Replace with your method of handling tokens
headers = {"Authorization": f"Token {token}"}

# Download KoboCollect data (first page of paginated data)
data = download_kobo_data(api_url, headers)
if data:
    st.success("KoboCollect data successfully retrieved!")

    # Convert JSON data to DataFrame
    df_kobo = pd.json_normalize(data['results'])

    # Display raw data
    with st.expander("Raw data"):
        st.dataframe(df_kobo)

    # Transform GPI and Sondage columns
    for col in ['GPI', 'Sondage']:
        if col in df_kobo.columns:
            df_kobo[f'{col}_Transformed'] = df_kobo[col].apply(lambda x: ', '.join([str(obj) for obj in x]) if isinstance(x, list) else x)
            df_kobo.drop(columns=[col], inplace=True)

    # Process GPS data
    if 'GPS' in df_kobo.columns:
        gps_split = df_kobo['GPS'].str.split(' ', expand=True)
        df_kobo[['Latitude', 'Longitude', 'Altitude', 'Other']] = gps_split.apply(pd.to_numeric, errors='coerce')

    # Convert submission time column to datetime
    df_kobo["_submission_time"] = pd.to_datetime(df_kobo["_submission_time"])

    # Date selection with validation
    date1 = st.sidebar.date_input("Select start date")
    date2 = st.sidebar.date_input("Select end date")

    if date1 > date2:
        st.error("Start date cannot be after end date!")
    else:
        date1 = pd.to_datetime(date1)
        date2 = pd.to_datetime(date2) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

        df_filtered = df_kobo[(df_kobo["_submission_time"] >= date1) & (df_kobo["_submission_time"] <= date2)]

        # Additional filters
        st.sidebar.header("Additional filters:")
        filters = {
            "Identification/Province": st.sidebar.multiselect("Province", sorted(df_filtered["Identification/Province"].unique())),
            "Identification/Commune": st.sidebar.multiselect("Commune", sorted(df_filtered["Identification/Commune"].unique())),
            "Identification/Adresse_PDV": st.sidebar.multiselect("Avenue", sorted(df_filtered["Identification/Adresse_PDV"].unique())),
            "Name_Agent": st.sidebar.multiselect("Agent", sorted(df_filtered["Name_Agent"].unique()))
        }

        for col, selection in filters.items():
            if selection:
                df_filtered = df_filtered[df_filtered[col].isin(selection)]

        # Analytics block
        with st.expander("Analytics"):
            a1, a2 = st.columns(2)

            if 'Sondage_Transformed' in df_filtered.columns:
                df_filtered['Sondage/PVT'] = pd.to_numeric(df_filtered['Sondage_Transformed'], errors='coerce')
                total_price = df_filtered['Sondage/PVT'].sum()
                num_rows = len(df_filtered)
                a1.metric(label="Number of PDVs", value=num_rows)
                a2.metric(label="Total price", value=total_price)
            else:
                st.error("The 'Sondage_Transformed' column is missing.")

        # Column selection and data download
        columns = st.multiselect("Columns to include in the downloaded file", options=df_kobo.columns.tolist(), default=df_kobo.columns.tolist())
        df_final = df_filtered[columns]

        st.subheader("Filtered data")
        st.dataframe(df_final, use_container_width=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_final.to_excel(writer, index=False)
        processed_data = output.getvalue()

        st.download_button(
            label="Download filtered data",
            data=processed_data,
            file_name="filtered_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # Display map
        if not df_filtered[['Latitude', 'Longitude']].isna().all().any():
            df_filtered = df_filtered.dropna(subset=['Latitude', 'Longitude'])
            map_center = [df_filtered['Latitude'].mean(), df_filtered['Longitude'].mean()]
            map_folium = folium.Map(location=map_center, zoom_start=12)
            marker_cluster = MarkerCluster().add_to(map_folium)

            for _, row in df_filtered.iterrows():
                folium.Marker(
                    location=[row['Latitude'], row['Longitude']],
                    popup=f"Agent: {row['Identification/Name_PDV']}"
                ).add_to(marker_cluster)

            folium_static(map_folium)
        else:
            st.warning("No valid GPS data available to display the map.")

        # Charts
        col1, col2 = st.columns(2)

        with col1:
            if 'Identification/Type_PDV' in df_filtered.columns:
                st.subheader("Type_PDV Pie Chart")
                pie_chart_data = df_filtered['Identification/Type_PDV'].value_counts()
                fig = px.pie(pie_chart_data, values=pie_chart_data.values, names=pie_chart_data.index, title="Type_PDV Distribution", hole=0.3)
                fig.update_traces(textinfo='value', textposition='inside')
                st.plotly_chart(fig)

        with col2:
            if 'Name_Agent' in df_filtered.columns:
                st.subheader("Agent Histogram")
                
                if not df_filtered.empty:
                    bar_chart_data = df_filtered['Name_Agent'].value_counts()
                    if not bar_chart_data.empty:
                        fig = px.bar(
                            bar_chart_data, 
                            x=bar_chart_data.index, 
                            y=bar_chart_data.values, 
                            labels={"x": "Agent Name", "y": "Occurrences"}, 
                            title="Number of Agents"
                        )
                        st.plotly_chart(fig)
                    else:
                        st.warning("No data for the agent histogram.")
                else:
                    st.warning("The filtered DataFrame is empty.")
else:
    st.error("Failed to retrieve KoboCollect data.")
