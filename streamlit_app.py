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
    "📊 26-Year Recurrence (2000–2025)",
    "⚡ Side-by-Side Comparison",
])

# ── Shared: fetch FIRMS ───────────────────────────────────────────────────────
SNAPSHOT_DIR = "data"


@st.cache_data
def load_all_snapshots() -> pd.DataFrame:
    """Load and merge every firms_snapshot_*.csv from data/."""
    import glob
    snaps = sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "firms_snapshot_*.csv")))
    if not snaps:
        return pd.DataFrame()
    frames = []
    for s in snaps:
        try:
            frames.append(pd.read_csv(s))
        except Exception:
            pass
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    if "acq_datetime" in df.columns:
        df["acq_datetime"] = pd.to_datetime(df["acq_datetime"], errors="coerce")
    return df


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


def get_data(days, source, map_key) -> tuple[pd.DataFrame, str]:
    """Merge live API result with all local snapshots, deduplicate, filter to days."""
    api_df, err = fetch_firms(days, source, map_key)
    local_df = load_all_snapshots()

    frames = [f for f in [api_df, local_df] if not f.empty]
    if not frames:
        return pd.DataFrame(), err or "No data available"

    combined = pd.concat(frames, ignore_index=True)
    if "acq_datetime" in combined.columns:
        combined["acq_datetime"] = pd.to_datetime(combined["acq_datetime"], errors="coerce")
        cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=days)
        combined = combined[combined["acq_datetime"] >= cutoff]

    # Deduplicate on lat/lon/time
    dedup_cols = [c for c in ["latitude", "longitude", "acq_datetime"] if c in combined.columns]
    combined = combined.drop_duplicates(subset=dedup_cols)

    note = "live + cached" if (not api_df.empty and not local_df.empty) else ("cached" if api_df.empty else "live")
    return combined.reset_index(drop=True), note


@st.cache_data(ttl=3600)
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
    from folium.plugins import HeatMap
    m = folium.Map(location=[18.8, 98.9], zoom_start=zoom, tiles="CartoDB dark_matter")
    if df_rec.empty:
        return m
    max_count = df_rec["burn_count"].max()
    # HeatMap takes [lat, lon, weight] — weight normalised 0-1
    heat_data = [
        [row["latitude"], row["longitude"], row["burn_count"] / max_count]
        for _, row in df_rec.iterrows()
    ]
    HeatMap(
        heat_data,
        min_opacity=0.4,
        radius=12,
        blur=8,
        gradient={0.2: "yellow", 0.5: "orange", 0.8: "red", 1.0: "darkred"},
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
        fetch = st.button("🔄 Fetch", width="stretch")

    if fetch or "firms_df" not in st.session_state:
        with st.spinner("Loading satellite data..."):
            df_result, note = get_data(days, source, MAP_KEY)
            if df_result.empty:
                st.error("No data available. Try again in a few minutes.")
                st.stop()
            st.session_state["firms_df"] = df_result
            st.session_state["firms_note"] = note

    df = st.session_state.get("firms_df", pd.DataFrame())

    if not df.empty:
        st.caption(f"Source: {st.session_state.get('firms_note', '')} · {len(df):,} total detections in window")
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
                         width="stretch")
            st.download_button("⬇ CSV", df.to_csv(index=False).encode("utf-8"),
                               "chiang_mai_fires.csv", "text/csv")
    else:
        st.info("No data. Click Fetch.")


# ── Tab 2: Retrospective ──────────────────────────────────────────────────────
with tab_retro:
    df_rec = load_recurrence()
    st.caption(f"CSV path: `{RECURRENCE_CSV}` · exists: `{os.path.exists(RECURRENCE_CSV)}` · rows: `{len(df_rec)}`")

    if df_rec.empty:
        st.info("Retrospective data not yet loaded. Commit `data/burn_recurrence.csv` to GitHub and reboot the app.")
    else:
        max_c = int(df_rec["burn_count"].max())

        # Clickable year threshold buttons
        if "rec_years" not in st.session_state:
            st.session_state["rec_years"] = 5

        st.markdown("**คลิกเพื่อดูพื้นที่ / Click to filter map by years burned:**")
        thresholds = [1, 3, 5, 10, 15, 20, max_c]
        thresholds = sorted(set(t for t in thresholds if t <= max_c))
        btn_cols = st.columns(len(thresholds))
        for i, t in enumerate(thresholds):
            count = (df_rec["burn_count"] >= t).sum()
            label = f"**{t}+ yrs**\n{count:,} px"
            if btn_cols[i].button(f"{t}+ yrs ({count:,})", key=f"btn_{t}"):
                st.session_state["rec_years"] = t

        min_years = st.slider(
            "หรือเลื่อนเพื่อเลือก / Or drag to select",
            min_value=1, max_value=max_c,
            value=st.session_state["rec_years"],
            step=1, key="rec_slider"
        )
        st.session_state["rec_years"] = min_years

        filtered = df_rec[df_rec["burn_count"] >= min_years]
        st.caption(f"**{len(filtered):,} pixels** burned {min_years}+ of {max_c} years (2000–2025)  ·  NASA FIRMS MODIS 1km")

        st_folium(make_recurrence_map(filtered), width="100%", height=520, key=f"map_retro_{min_years}")

        st.download_button(
            "⬇ Download full recurrence CSV",
            df_rec.to_csv(index=False).encode("utf-8"),
            "burn_recurrence_2000_2025.csv", "text/csv"
        )


# ── Tab 3: Side-by-Side ───────────────────────────────────────────────────────
with tab_compare:
    df_rec = load_recurrence()

    # Auto-fetch live data if not already in session state
    if "firms_df" not in st.session_state:
        with st.spinner("Loading live fire data..."):
            df_live_result, note = get_data(1, "VIIRS_NOAA20_NRT", MAP_KEY)
            st.session_state["firms_df"] = df_live_result
            st.session_state["firms_note"] = note
    df_live = st.session_state.get("firms_df", pd.DataFrame())

    if df_rec.empty:
        st.warning("Retrospective data not yet available — commit burn_recurrence.csv to GitHub.")
    else:
        max_c = int(df_rec["burn_count"].max())

        st.markdown(
            f"**The same locations that burned repeatedly across 26 years of satellite records "
            f"are burning again today. This is not random. This is pattern.**\n\n"
            f"พื้นที่เดิมที่ถูกเผาซ้ำตลอด 26 ปีของบันทึกดาวเทียม กำลังลุกไหม้อีกครั้งในวันนี้"
        )

        # Single year threshold for compare view
        compare_years = st.slider(
            "Show recurrence hotspots burned at least N years",
            min_value=1, max_value=max_c, value=10, step=1, key="compare_slider"
        )
        hotspots = df_rec[df_rec["burn_count"] >= compare_years]

        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("🔴 วันนี้ / Today")
            st.caption(f"{len(df_live):,} detections · NASA FIRMS VIIRS · last 24h")
            st_folium(make_firms_map(df_live, zoom=7), width="100%", height=500, key="map_compare_live")

        with col_right:
            st.subheader(f"📊 2000–2025 · {compare_years}+ years")
            st.caption(f"{len(hotspots):,} persistent burn pixels · NASA FIRMS MODIS")
            st_folium(make_recurrence_map(hotspots, zoom=7), width="100%", height=500, key="map_compare_retro")
