"""
Chiang Mai Fire Watch — Streamlit Cloud app
Live: chiangfai.streamlit.app
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

MAP_KEY = st.secrets.get("FIRMS_MAP_KEY", "4f412b8b6d507d17c0682871f13c3618")
BBOX = "97.5,17.5,99.5,20.5"

RECURRENCE_CSV = "data/burn_recurrence.csv"
RECURRENCE_PNG = "reports/recurrence_map.png"

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='text-align:center;padding:10px 0 4px 0'>
<h1 style='color:#ff4422;margin-bottom:2px'>🔥 เชียงใหม่ไฟป่า</h1>
<h3 style='color:#aaa;font-weight:300;margin-top:0'>Chiang Mai Fire Watch · Open Satellite Data</h3>
<p style='color:#555;font-size:0.82em'>
NASA FIRMS VIIRS 375m &nbsp;·&nbsp; Sentinel-2 dNBR 10m &nbsp;·&nbsp;
<a href='https://github.com/ChiangFai/ChiangFai' style='color:#666'>
github.com/ChiangFai/ChiangFai</a>
</p></div>
""", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_live, tab_retro, tab_compare = st.tabs([
    "🔴 Live Fires (24h)",
    "📊 8-Year Recurrence (2018–2025)",
    "⚡ Side-by-Side Comparison",
])

# ── Shared: fetch FIRMS ───────────────────────────────────────────────────────
SNAPSHOT_DIR = "data"

def load_local_snapshot() -> pd.DataFrame:
    """Fallback: load most recent saved CSV snapshot."""
    import glob
    snaps = sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "firms_snapshot_*.csv")))
    if snaps:
        df = pd.read_csv(snaps[-1])
        if "acq_datetime" in df.columns:
            df["acq_datetime"] = pd.to_datetime(df["acq_datetime"])
        return df, os.path.basename(snaps[-1])
    return pd.DataFrame(), None


@st.cache_data(ttl=3600)
def fetch_firms(days, source, map_key):
    import time
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{source}/{BBOX}/{days}"
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text))
            if not df.empty and "acq_date" in df.columns:
                df["acq_datetime"] = pd.to_datetime(
                    df["acq_date"] + " " + df["acq_time"].astype(str).str.zfill(4),
                    format="%Y-%m-%d %H%M"
                )
            return df, None
        except Exception as e:
            last_err = str(e)
            if attempt < 2:
                time.sleep(2 ** attempt)
    return pd.DataFrame(), last_err


@st.cache_data
def load_recurrence():
    if os.path.exists(RECURRENCE_CSV):
        return pd.read_csv(RECURRENCE_CSV)
    return pd.DataFrame()


def make_firms_map(df, zoom=8):
    m = folium.Map(location=[18.8, 98.9], zoom_start=zoom, tiles="CartoDB dark_matter")
    for _, row in df.iterrows():
        frp = row.get("frp", 5)
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=min(max(frp / 3, 3), 12),
            color="#ff4422", fill=True, fill_color="#ff6644", fill_opacity=0.65,
            popup=f"FRP: {frp:.1f} MW | {str(row.get('acq_datetime',''))[:16]}",
            tooltip=f"{frp:.1f} MW",
        ).add_to(m)
    return m


def make_recurrence_map(df_rec, zoom=8):
    m = folium.Map(location=[18.8, 98.9], zoom_start=zoom, tiles="CartoDB dark_matter")
    if df_rec.empty:
        return m
    max_count = df_rec["burn_count"].max()
    palette = ["#ffcc00", "#ff9900", "#ff4400", "#cc0000", "#880000",
               "#550000", "#330000", "#1a0000"]
    for _, row in df_rec.iterrows():
        idx = min(int(row["burn_count"]) - 1, len(palette) - 1)
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=3,
            color=palette[idx], fill=True, fill_color=palette[idx], fill_opacity=0.7,
            popup=f"Burned {int(row['burn_count'])} of 8 years",
            tooltip=f"{int(row['burn_count'])}yr",
        ).add_to(m)
    return m


# ── Tab 1: Live ───────────────────────────────────────────────────────────────
with tab_live:
    col_s, col_b = st.columns([3, 1])
    with col_s:
        days = st.slider("Lookback (days)", 1, 10, 1, key="days_live")
        source = st.selectbox("Sensor", ["VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"])
    with col_b:
        st.markdown("<br>", unsafe_allow_html=True)
        fetch = st.button("🔄 Fetch", use_container_width=True)

    if fetch or "firms_df" not in st.session_state:
        with st.spinner("Loading satellite data..."):
            df_result, err = fetch_firms(days, source, MAP_KEY)
            if err:
                st.warning(f"FIRMS API unavailable ({err}) — showing last saved snapshot.")
                df_result, snap_name = load_local_snapshot()
                if df_result.empty:
                    st.error("No local snapshot available either. Try again in a few minutes.")
                    st.stop()
                else:
                    st.info(f"Loaded from cache: `{snap_name}`")
            st.session_state["firms_df"] = df_result

    df = st.session_state.get("firms_df", pd.DataFrame())

    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("จุดความร้อน / Detections", f"{len(df):,}")
        c2.metric("Max FRP (MW)", f"{df['frp'].max():.1f}" if "frp" in df.columns else "–")
        c3.metric("Avg FRP (MW)", f"{df['frp'].mean():.1f}" if "frp" in df.columns else "–")
        high = len(df[df["confidence"].isin(["h", "high"])]) if "confidence" in df.columns else 0
        c4.metric("High confidence", f"{high:,}")

        if len(df) > 20:
            st.error(f"⚠ {len(df):,} detections — exceeds alert threshold of 20")

        st_folium(make_firms_map(df), width="100%", height=500, key="map_live")

        with st.expander("Raw data / ดาวน์โหลด"):
            cols = [c for c in ["acq_datetime", "latitude", "longitude", "frp", "confidence"] if c in df.columns]
            st.dataframe(df[cols].sort_values("frp", ascending=False) if "frp" in df.columns else df[cols],
                         use_container_width=True)
            st.download_button("⬇ CSV", df.to_csv(index=False).encode("utf-8"),
                               "chiang_mai_fires.csv", "text/csv")
    else:
        st.info("No data. Click Fetch.")


# ── Tab 2: Retrospective ──────────────────────────────────────────────────────
with tab_retro:
    df_rec = load_recurrence()

    if df_rec.empty and not os.path.exists(RECURRENCE_PNG):
        st.info("""
**Retrospective data not yet available.**

The 8-year Sentinel-2 burn recurrence map is currently being processed via Google Earth Engine.

Once the GEE export lands in Google Drive:
1. Download the `.tif` file
2. Run: `python process_retrospective.py <path_to_file.tif>`
3. Commit `data/burn_recurrence.csv` and `reports/recurrence_map.png` to GitHub
4. This tab will populate automatically on next app refresh.
        """)
    else:
        if os.path.exists(RECURRENCE_PNG):
            st.image(RECURRENCE_PNG,
                     caption="Burn recurrence 2018–2025 · Sentinel-2 dNBR · 10m · Google Earth Engine",
                     use_container_width=True)

        if not df_rec.empty:
            st.markdown("---")
            max_c = int(df_rec["burn_count"].max())

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Burned 1+ years", f"{(df_rec['burn_count'] >= 1).sum():,}")
            c2.metric("Burned 3+ years", f"{(df_rec['burn_count'] >= 3).sum():,}")
            c3.metric("Burned 5+ years", f"{(df_rec['burn_count'] >= 5).sum():,}")
            c4.metric(f"Burned all {max_c} years", f"{(df_rec['burn_count'] >= max_c).sum():,}")

            min_years = st.slider("Show pixels burned at least N years", 1, max_c, 3, key="rec_slider")
            filtered = df_rec[df_rec["burn_count"] >= min_years]
            st.caption(f"{len(filtered):,} pixels burned {min_years}+ years")
            st_folium(make_recurrence_map(filtered), width="100%", height=500, key="map_retro")

            st.download_button("⬇ Download recurrence CSV",
                               df_rec.to_csv(index=False).encode("utf-8"),
                               "burn_recurrence_2018_2025.csv", "text/csv")


# ── Tab 3: Side-by-Side ───────────────────────────────────────────────────────
with tab_compare:
    df_rec = load_recurrence()
    df_live = st.session_state.get("firms_df", pd.DataFrame())

    if df_live.empty:
        st.warning("Fetch live data first (tab 1).")
    elif df_rec.empty and not os.path.exists(RECURRENCE_PNG):
        st.warning("Retrospective data not yet processed (see tab 2).")
    else:
        st.markdown("""
**The core finding:** The same locations that burned repeatedly across 8 years of satellite records
are burning again today. This is not random. This is pattern.

**ข้อค้นพบหลัก:** พื้นที่เดิมที่ถูกเผาซ้ำตลอด 8 ปีของบันทึกดาวเทียม กำลังลุกไหม้อีกครั้งในวันนี้
        """)

        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("🔴 วันนี้ / Today (Live)")
            st.caption(f"{len(df_live):,} detections · NASA FIRMS VIIRS")
            if not df_live.empty:
                st_folium(make_firms_map(df_live, zoom=7),
                          width="100%", height=480, key="map_compare_live")

        with col_right:
            st.subheader("📊 2018–2025 (Retrospective)")
            if os.path.exists(RECURRENCE_PNG):
                st.image(RECURRENCE_PNG, use_container_width=True)
            elif not df_rec.empty:
                st.caption(f"Pixels burned 3+ years shown")
                filtered = df_rec[df_rec["burn_count"] >= 3]
                st_folium(make_recurrence_map(filtered, zoom=7),
                          width="100%", height=480, key="map_compare_retro")
            else:
                st.info("Retrospective data pending.")
