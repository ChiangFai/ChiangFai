"""
Chiang Mai Fire Watch — Streamlit Cloud app
Live: chiangfai.streamlit.app
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import folium
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

FIRE_BY_YEAR_CSV = "data/fire_by_year.csv"
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
def load_fire_by_year():
    if os.path.exists(FIRE_BY_YEAR_CSV):
        return pd.read_csv(FIRE_BY_YEAR_CSV)
    return pd.DataFrame()


def filter_by_range(df, start_year, end_year):
    """Sum fire detections across selected year range. Returns lat/lon/burn_count."""
    year_cols = [f"y{y}" for y in range(start_year, end_year + 1) if f"y{y}" in df.columns]
    if not year_cols:
        return pd.DataFrame()
    result = df[["latitude", "longitude"]].copy()
    result["burn_count"] = df[year_cols].sum(axis=1)
    return result[result["burn_count"] > 0]


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

        components.html(make_firms_map(df)._repr_html_(), height=500)

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
    df_yr = load_fire_by_year()

    if df_yr.empty:
        st.info("Per-year fire data not yet available. Run the new GEE export and process_retrospective.py, then push fire_by_year.csv.")
        if os.path.exists(RECURRENCE_PNG):
            st.image(RECURRENCE_PNG, caption="Total burn recurrence 2000–2025 (26-year sum)")
    else:
        avail_years = sorted([int(c[1:]) for c in df_yr.columns if c.startswith("y")])
        min_yr, max_yr = avail_years[0], avail_years[-1]

        year_range = st.slider(
            "เลือกช่วงปี / Select year range",
            min_value=min_yr, max_value=max_yr,
            value=(min_yr, max_yr), step=1, key="year_range"
        )
        start_yr, end_yr = year_range

        filtered = filter_by_range(df_yr, start_yr, end_yr)
        st.caption(f"**{len(filtered):,} pixels** with at least one fire between {start_yr}–{end_yr} · NASA FIRMS MODIS 1km")
        components.html(make_recurrence_map(filtered)._repr_html_(), height=520)

        st.download_button(
            "⬇ Download filtered CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            f"fires_{start_yr}_{end_yr}.csv", "text/csv"
        )


# ── Tab 3: Side-by-Side ───────────────────────────────────────────────────────
with tab_compare:
    df_yr = load_fire_by_year()

    if "firms_df" not in st.session_state:
        with st.spinner("Loading live fire data..."):
            df_live_result, note = get_data(1, "VIIRS_NOAA20_NRT", MAP_KEY)
            st.session_state["firms_df"] = df_live_result
            st.session_state["firms_note"] = note
    df_live = st.session_state.get("firms_df", pd.DataFrame())

    if df_yr.empty:
        st.warning("Per-year fire data not yet available (see tab 2).")
    else:
        avail_years = sorted([int(c[1:]) for c in df_yr.columns if c.startswith("y")])
        min_yr, max_yr = avail_years[0], avail_years[-1]

        st.markdown(
            "**พื้นที่เดิมที่ถูกเผาซ้ำตลอด 26 ปี กำลังลุกไหม้อีกครั้งในวันนี้**  \n"
            "The same locations that burned repeatedly for 26 years are on fire again today."
        )

        compare_range = st.slider(
            "Historical range to compare",
            min_value=min_yr, max_value=max_yr,
            value=(2000, 2025), step=1, key="compare_range"
        )
        hotspots = filter_by_range(df_yr, compare_range[0], compare_range[1])

        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("🔴 วันนี้ / Today (Live)")
            st.caption(f"{len(df_live):,} detections · VIIRS")
            components.html(make_firms_map(df_live, zoom=7)._repr_html_(), height=500)
        with col_right:
            st.subheader(f"📊 {compare_range[0]}–{compare_range[1]}")
            st.caption(f"{len(hotspots):,} pixels burned · FIRMS MODIS")
            components.html(make_recurrence_map(hotspots, zoom=7)._repr_html_(), height=500)
