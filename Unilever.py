import streamlit as st
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import folium_static
import plotly.graph_objs as go
import plotly.express as px
import io

# Define the page configuration
st.set_page_config(page_title="UNILEVER", page_icon="🌍", layout="wide")
st.header(":bar_chart: Unilever Dashboard")
st.markdown('<style>div.block-container{padding-top:2rem;}</style>', unsafe_allow_html=True)

# Setup retries with backoff
session = requests.Session()
retry = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry)
session.mount('https://', adapter)

# Caching data to avoid multiple API calls
@st.cache_data
def download_kobo_data(api_url, headers):
    try:
        response = session.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error retrieving the data: {e}")
        return None

# API URL and key
api_url = "https://kf.kobotoolbox.org/api/v2/assets/amfgmGRANPdTQgh85J7YqK/data/?format=json"
headers = {
    "Authorization": "Token fd0239896ad338de0651fe082978bec82cc7dad4"
}

# Download the data from KoboCollect
data = download_kobo_data(api_url, headers)
if data:
    st.success("KoboCollect data retrieved successfully!")

    # Convert JSON data to DataFrame
    df_kobo = pd.json_normalize(data['results'])

    # Display the data in Streamlit
    with st.expander("Gross data"):
        st.dataframe(df_kobo)  # Display data as a table

    # Convert the DataFrame to an Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_kobo.to_excel(writer, index=False)
    processed_data = output.getvalue()

    # Button to download the Excel file
    st.download_button(
        label="📥 Download raw data in Excel format",
        data=processed_data,
        file_name="collected_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Process GPI column if present
    if 'GPI' in df_kobo.columns:
        gpi_data = df_kobo['GPI'].apply(lambda x: ', '.join([str(obj) for obj in x]) if isinstance(x, list) else x)
        df_kobo['GPI_Transformed'] = gpi_data
        df_kobo = df_kobo.drop(columns=['GPI'])

    # Process Sondage column if present
    if 'Sondage' in df_kobo.columns:
        sondage_data = df_kobo['Sondage'].apply(lambda x: ', '.join([str(obj) for obj in x]) if isinstance(x, list) else x)
        df_kobo['Sondage_Transformed'] = sondage_data
        df_kobo = df_kobo.drop(columns=['Sondage'])

    # Checking and processing GPS data
    if 'GPS' in df_kobo.columns:
        gps_split = df_kobo['GPS'].str.split(' ', expand=True)
        df_kobo[['Latitude', 'Longitude', 'Altitude', 'Other']] = gps_split.astype(float)

    # Convert the date column
    df_kobo["_submission_time"] = pd.to_datetime(df_kobo["_submission_time"])

    # Input for date selection
    date1 = st.sidebar.date_input("Choose start date")
    date2 = st.sidebar.date_input("Choose end date")

    # Convert date1 and date2 to datetime and ensure date2 covers the entire day
    date1 = pd.to_datetime(date1)
    date2 = pd.to_datetime(date2) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    # Filter by date
    df_filtered = df_kobo[
        (df_kobo["_submission_time"] >= date1) & 
        (df_kobo["_submission_time"] <= date2)
    ]

    # Sidebar for additional filters
    st.sidebar.header("Choose your filters:")
    filters = {
        "Identification/Province": st.sidebar.multiselect("Choose your Province", df_filtered["Identification/Province"].unique()),
        "Identification/Commune": st.sidebar.multiselect("Choose the commune", df_filtered["Identification/Commune"].unique()),
        "Identification/Adresse_PDV": st.sidebar.multiselect("Choose the avenue", df_filtered["Identification/Adresse_PDV"].unique()),
        "Name_Agent": st.sidebar.multiselect("Choose Name and Surname", df_filtered["Name_Agent"].unique())
    }

    for col, selection in filters.items():
        if selection:
            df_filtered = df_filtered[df_filtered[col].isin(selection)]

# Bloc analytique pour afficher le nombre de PDVs et le Total Price
with st.expander("ANALYTICS"):
    a1, a2 = st.columns(2)

    # Vérifier si 'Sondage_Transformed' existe dans le DataFrame
    if 'Sondage_Transformed' in df_filtered.columns:
        # Convertir la colonne 'Sondage_Transformed' en numérique pour Sondage/PVT
        df_filtered['Sondage/PVT'] = pd.to_numeric(df_filtered['Sondage_Transformed'], errors='coerce')

        # Calcul du prix total (somme de 'Sondage/PVT')
        total_price = df_filtered['Sondage/PVT'].sum()  # Somme des valeurs de Sondage/PVT
        num_rows = len(df_filtered)

        # Affichage des métriques pour le nombre de points de vente (PDVs) et le prix total
        a1.metric(label="Number of PDVs", value=num_rows, help=f"Total Price: {total_price}", delta=total_price)
        a2.metric(label="Total Price", value=total_price, help=f"Total Price: {total_price}", delta=total_price)

    else:
        st.error("La colonne 'Sondage_Transformed' n'existe pas dans le DataFrame filtré.")

    # Sélectionner des colonnes à afficher et à télécharger
    columns = st.multiselect("Select the columns you wish to include in the downloaded file:", 
                             options=df_kobo.columns.tolist(), 
                             default=df_kobo.columns.tolist())

    # Filtrer les données en fonction des colonnes sélectionnées
    df_final = df_filtered[columns]

    # Afficher les données filtrées
    st.subheader("Filtered data")
    st.dataframe(df_final, use_container_width=True)

    # Convert the filtered DataFrame to an Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, index=False)
    processed_data = output.getvalue()

    # Button to download the filtered data in Excel format
    st.download_button(
        label="📥 Download filtered data in Excel format",
        data=processed_data,
        file_name="filtered_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Checking before displaying the map
    if not df_filtered[['Latitude', 'Longitude']].isna().all().any():
        df_filtered = df_filtered.dropna(subset=['Latitude', 'Longitude'])
        map_center = [df_filtered['Latitude'].mean(), df_filtered['Longitude'].mean()]
        map_folium = folium.Map(location=map_center, zoom_start=12)
        marker_cluster = MarkerCluster().add_to(map_folium)

        for _, row in df_filtered.iterrows():
            folium.Marker(
                location=[row['Latitude'], row['Longitude']],
                popup=f"Agent: {row['Name_Agent']}"
            ).add_to(marker_cluster)

        folium_static(map_folium)
    else:
        st.warning("No valid data to display the map.")

    # Graphs
    col1, col2 = st.columns(2)
    with col1:
        # Create a bar chart for selected columns
        if len(columns) > 0:
            st.subheader("Bar chart of selected columns")
            selected_column = st.selectbox("Select a column to display", columns)
            bar_chart_data = df_filtered[selected_column].value_counts()
            fig = px.bar(bar_chart_data, x=bar_chart_data.index, y=bar_chart_data.values, labels={'x': selected_column, 'y': 'Counts'})
            st.plotly_chart(fig)

    with col2:
        # Create a pie chart for the same selected column
        if len(columns) > 0:
            st.subheader("Pie chart of selected column")
            selected_column = st.selectbox("Select a column for the pie chart", columns)
            pie_chart_data = df_filtered[selected_column].value_counts()
            fig = px.pie(pie_chart_data, values=pie_chart_data.values, names=pie_chart_data.index, title=f"Distribution of {selected_column}")
            st.plotly_chart(fig)
