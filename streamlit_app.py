"""
Root-level Streamlit entry point — required for Streamlit Cloud deployment.
Live at: https://chiangfai.streamlit.app (after connecting repo in Streamlit Cloud)
"""

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
from io import StringIO
from datetime import datetime
import os

st.set_page_config(
    page_title="เชียงใหม่ไฟป่า | Chiang Mai Fire Watch",
    page_icon="🔥",
    layout="wide",
)

# --- MAP KEY: set in Streamlit Cloud → Settings → Secrets as FIRMS_MAP_KEY ---
MAP_KEY = st.secrets.get("FIRMS_MAP_KEY", "4f412b8b6d507d17c0682871f13c3618")
BBOX = "97.5,17.5,99.5,20.5"

# --- Header ---
st.markdown("""
<div style='text-align:center; padding: 10px 0 20px 0'>
<h1 style='color:#ff4422; margin-bottom:4px'>🔥 เชียงใหม่ไฟป่า</h1>
<h3 style='color:#aaa; font-weight:300; margin-top:0'>Chiang Mai Fire Watch · Open Satellite Data</h3>
<p style='color:#555; font-size:0.85em'>
Data: NASA FIRMS VIIRS 375m &nbsp;·&nbsp;
<a href='https://github.com/ChiangFai/ChiangFai' style='color:#666'>github.com/ChiangFai/ChiangFai</a>
</p>
</div>
""", unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.header("ตั้งค่า / Settings")
    days = st.slider("ช่วงเวลา / Lookback (days)", 1, 10, 1)
    source = st.selectbox("เซ็นเซอร์ / Sensor", ["VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"])
    fetch = st.button("🔄 โหลดข้อมูล / Fetch Data", use_container_width=True)
    st.markdown("---")
    st.markdown("**เกี่ยวกับ / About**")
    st.markdown("โครงการ open source วิเคราะห์รูปแบบการเผาไหม้ในภาคเหนือ ปี 2561–2569")
    st.markdown("Open source project mapping burn patterns across northern Thailand, 2018–2026.")

# --- Fetch data ---
@st.cache_data(ttl=3600)
def fetch_firms(days, source, map_key):
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{source}/{BBOX}/{days}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    if not df.empty and "acq_date" in df.columns:
        df["acq_datetime"] = pd.to_datetime(
            df["acq_date"] + " " + df["acq_time"].astype(str).str.zfill(4),
            format="%Y-%m-%d %H%M"
        )
    return df

if fetch or "firms_df" not in st.session_state:
    with st.spinner("กำลังโหลดข้อมูลดาวเทียม..."):
        try:
            st.session_state["firms_df"] = fetch_firms(days, source, MAP_KEY)
        except Exception as e:
            st.error(f"Error fetching data: {e}")
            st.stop()

df = st.session_state.get("firms_df", pd.DataFrame())

if df.empty:
    st.warning("ไม่พบข้อมูล / No data returned. Try a longer lookback period.")
    st.stop()

# --- Metrics ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("จุดความร้อน / Detections", f"{len(df):,}")
col2.metric("FRP สูงสุด / Max FRP (MW)", f"{df['frp'].max():.1f}" if 'frp' in df.columns else "–")
col3.metric("FRP เฉลี่ย / Avg FRP (MW)", f"{df['frp'].mean():.1f}" if 'frp' in df.columns else "–")
high = len(df[df['confidence'].isin(['h','high'])]) if 'confidence' in df.columns else 0
col4.metric("High confidence", f"{high:,}")

if len(df) > 20:
    st.error(f"⚠ ตรวจพบ {len(df):,} จุดความร้อน — เกินเกณฑ์เตือนภัย | {len(df):,} detections exceed alert threshold")

# --- Map ---
st.subheader("แผนที่จุดความร้อน | Fire Detection Map")
m = folium.Map(location=[18.8, 98.9], zoom_start=8, tiles="CartoDB dark_matter")

for _, row in df.iterrows():
    frp_val = row.get("frp", 5)
    radius = min(max(frp_val / 3, 3), 12)
    folium.CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=radius,
        color="#ff4422",
        fill=True,
        fill_color="#ff6644",
        fill_opacity=0.6,
        popup=f"FRP: {frp_val:.1f} MW | {str(row.get('acq_datetime',''))[:16]}",
        tooltip=f"{frp_val:.1f} MW",
    ).add_to(m)

st_folium(m, width="100%", height=520)

# --- Table ---
with st.expander("🔢 ข้อมูลดิบ / Raw data"):
    cols = [c for c in ["acq_datetime", "latitude", "longitude", "frp", "confidence"] if c in df.columns]
    st.dataframe(df[cols].sort_values("frp", ascending=False) if "frp" in df.columns else df[cols],
                 use_container_width=True)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇ ดาวน์โหลด CSV / Download CSV", csv, "chiang_mai_fires.csv", "text/csv")
