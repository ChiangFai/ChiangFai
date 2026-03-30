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
tab_live, tab_retro, tab_compare, tab_anim = st.tabs([
    "🔴 Live Fires (24h)",
    "📊 26-Year Recurrence (2000–2025)",
    "⚡ Side-by-Side Comparison",
    "🎬 Fire Season Animation",
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


def make_recurrence_map(df_rec, zoom=8, min_count=1):
    from folium.plugins import HeatMap
    m = folium.Map(location=[18.8, 98.9], zoom_start=zoom, tiles="CartoDB dark_matter")
    if df_rec.empty:
        return m
    df_plot = df_rec[df_rec["burn_count"] >= min_count]
    if df_plot.empty:
        return m
    max_count = df_plot["burn_count"].max()
    heat_data = [
        [row["latitude"], row["longitude"], row["burn_count"] / max_count]
        for _, row in df_plot.iterrows()
    ]
    HeatMap(
        heat_data,
        min_opacity=0.35,
        radius=5,
        blur=3,
        gradient={0.2: "yellow", 0.5: "orange", 0.8: "red", 1.0: "darkred"},
    ).add_to(m)
    return m


def make_animated_year_map(df_yr, zoom=7, max_pts_per_year=1500):
    """
    TimestampedGeoJson animation: one frame per year, play/pause/scrub in browser.
    Points are colored by total recurrence across all years so chronic hotspots
    stay visually prominent in every frame.
    """
    from folium.plugins import TimestampedGeoJson

    avail_years = sorted([int(c[1:]) for c in df_yr.columns if c.startswith("y")])
    year_cols = [f"y{y}" for y in avail_years if f"y{y}" in df_yr.columns]

    df_work = df_yr[["latitude", "longitude"] + year_cols].copy()
    df_work["total_burns"] = df_work[year_cols].fillna(0).sum(axis=1)
    max_burns = max(df_work["total_burns"].max(), 1)

    def recurrence_color(n):
        frac = n / max_burns
        if frac >= 0.75:
            return "#8b0000"   # deep red — burned 75 %+ of all years
        elif frac >= 0.5:
            return "#cc2200"   # red
        elif frac >= 0.25:
            return "#ff6600"   # orange
        else:
            return "#ffaa00"   # amber — infrequent

    features = []
    for year in avail_years:
        col = f"y{year}"
        if col not in df_work.columns:
            continue
        year_fires = df_work[df_work[col].fillna(0) > 0]

        # Always keep chronic hotspots; sample the rest down to budget
        chronic = year_fires[year_fires["total_burns"] >= 5]
        occasional = year_fires[year_fires["total_burns"] < 5]
        remaining = max(0, max_pts_per_year - len(chronic))
        if len(occasional) > remaining:
            occasional = occasional.sample(remaining, random_state=42)
        sample = pd.concat([chronic, occasional])

        for _, row in sample.iterrows():
            color = recurrence_color(row["total_burns"])
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["longitude"]), float(row["latitude"])],
                },
                "properties": {
                    "time": f"{year}-03-15",
                    "style": {"color": color, "weight": 0},
                    "icon": "circle",
                    "iconstyle": {
                        "fillColor": color,
                        "fillOpacity": 0.8,
                        "stroke": False,
                        "radius": 4,
                    },
                    "popup": f"Burned {int(row['total_burns'])} of {len(avail_years)} years",
                },
            })

    m = folium.Map(location=[18.8, 98.9], zoom_start=zoom, tiles="CartoDB dark_matter")

    TimestampedGeoJson(
        {"type": "FeatureCollection", "features": features},
        period="P1Y",
        add_last_point=False,
        auto_play=False,
        loop=True,
        max_speed=5,
        loop_button=True,
        date_options="YYYY",
        time_slider_drag_update=True,
        duration="P1Y",
    ).add_to(m)

    legend_html = """
    <div style='position:fixed;bottom:36px;left:30px;z-index:1000;
                background:rgba(20,20,20,0.88);padding:10px 14px;
                border-radius:7px;color:#eee;font-size:12px;line-height:1.7'>
      <b>🔥 Burn recurrence (2000–2025)</b><br>
      <span style='color:#8b0000;font-size:16px'>■</span> Chronic hotspot (≥75 % of years)<br>
      <span style='color:#cc2200;font-size:16px'>■</span> Frequent (50–74 %)<br>
      <span style='color:#ff6600;font-size:16px'>■</span> Occasional (25–49 %)<br>
      <span style='color:#ffaa00;font-size:16px'>■</span> Rare (&lt;25 %)
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


FIRE_BY_WEEK_CSV = "data/fire_by_week.csv"


@st.cache_data(ttl=3600)
def load_fire_by_week():
    if os.path.exists(FIRE_BY_WEEK_CSV):
        return pd.read_csv(FIRE_BY_WEEK_CSV)
    return pd.DataFrame()


def make_weekly_animated_map(df_week, year, zoom=7):
    """
    Weekly animation within a single fire season.
    df_week columns: latitude, longitude, year, week
    """
    from folium.plugins import TimestampedGeoJson
    import datetime

    season = df_week[df_week["year"] == year].copy()
    if season.empty:
        return folium.Map(location=[18.8, 98.9], zoom_start=zoom, tiles="CartoDB dark_matter")

    features = []
    for week, grp in season.groupby("week"):
        try:
            dt = datetime.date.fromisocalendar(int(year), int(week), 1).strftime("%Y-%m-%d")
        except Exception:
            continue
        for _, row in grp.iterrows():
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["longitude"]), float(row["latitude"])],
                },
                "properties": {
                    "time": dt,
                    "style": {"color": "#ff4422", "weight": 0},
                    "icon": "circle",
                    "iconstyle": {
                        "fillColor": "#ff4422",
                        "fillOpacity": 0.8,
                        "stroke": False,
                        "radius": 4,
                    },
                    "popup": f"Week {int(week)} · {dt}",
                },
            })

    m = folium.Map(location=[18.8, 98.9], zoom_start=zoom, tiles="CartoDB dark_matter")
    TimestampedGeoJson(
        {"type": "FeatureCollection", "features": features},
        period="P7D",
        add_last_point=False,
        auto_play=False,
        loop=True,
        max_speed=3,
        loop_button=True,
        date_options="YYYY [W]WW",
        time_slider_drag_update=True,
        duration="P7D",
    ).add_to(m)
    return m


def get_single_year_fires(df, year):
    """Return lat/lon rows where the given year has a fire detection."""
    col = f"y{year}"
    if col not in df.columns:
        return pd.DataFrame(columns=["latitude", "longitude"])
    return df[df[col].fillna(0) > 0][["latitude", "longitude"]].copy()


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

        col_yr, col_min = st.columns([3, 1])
        with col_yr:
            year_range = st.slider(
                "เลือกช่วงปี / Select year range",
                min_value=min_yr, max_value=max_yr,
                value=(min_yr, max_yr), step=1, key="year_range"
            )
        with col_min:
            min_recur = st.slider("Min recurrences", 1, 10, 2, key="min_recur",
                                  help="Only show pixels that burned at least this many times")
        start_yr, end_yr = year_range

        filtered = filter_by_range(df_yr, start_yr, end_yr)
        n_shown = len(filtered[filtered["burn_count"] >= min_recur])
        st.caption(
            f"**{n_shown:,} pixels** burned ≥{min_recur}× between {start_yr}–{end_yr} "
            f"(of {len(filtered):,} total burned pixels) · NASA FIRMS MODIS 1km"
        )
        components.html(make_recurrence_map(filtered, min_count=min_recur)._repr_html_(), height=520)

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
            "**พื้นที่เดิมที่ถูกเผาซ้ำ กำลังลุกไหม้อีกครั้งในวันนี้**  \n"
            "The same locations that burned in past seasons are on fire again today."
        )

        col_pick, col_mode = st.columns([2, 2])
        with col_pick:
            compare_year = st.selectbox(
                "Historical year to compare",
                options=sorted(avail_years, reverse=True),
                index=0,
                key="compare_year",
            )
        with col_mode:
            st.markdown("<br>", unsafe_allow_html=True)
            show_recur = st.checkbox(
                "Show multi-year recurrence instead",
                value=False,
                key="show_recur",
                help="Switch from single-year to cumulative 2000–2025 recurrence (≥3 fires)",
            )

        if show_recur:
            hotspots = filter_by_range(df_yr, min_yr, max_yr)
            right_label = f"📊 Recurrence 2000–{max_yr} (≥3 fires)"
            right_caption = f"{len(hotspots[hotspots['burn_count'] >= 3]):,} pixels burned 3+ times · FIRMS MODIS"
            right_map = make_recurrence_map(hotspots, zoom=7, min_count=3)
        else:
            hotspots = get_single_year_fires(df_yr, compare_year)
            right_label = f"📊 {compare_year} fire season"
            right_caption = f"{len(hotspots):,} pixels burned · FIRMS MODIS"
            hotspots["burn_count"] = 1
            right_map = make_recurrence_map(hotspots, zoom=7, min_count=1)

        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("🔴 วันนี้ / Today (Live)")
            st.caption(f"{len(df_live):,} detections · VIIRS")
            components.html(make_firms_map(df_live, zoom=7)._repr_html_(), height=500)
        with col_right:
            st.subheader(right_label)
            st.caption(right_caption)
            components.html(right_map._repr_html_(), height=500)


# ── Tab 4: Animation ──────────────────────────────────────────────────────────
with tab_anim:
    df_yr = load_fire_by_year()
    df_wk = load_fire_by_week()

    if df_yr.empty:
        st.warning("Per-year fire data not yet available (see Tab 2).")
    else:
        avail_years = sorted([int(c[1:]) for c in df_yr.columns if c.startswith("y")])

        mode = st.radio(
            "Animation mode",
            ["📅 Year-by-year (2000–2025)", "🗓 Weekly drill-down (single season)"],
            horizontal=True,
            key="anim_mode",
            disabled=df_wk.empty,
            help="Weekly mode requires fire_by_week.csv — run the GEE weekly export first.",
        )

        if mode == "📅 Year-by-year (2000–2025)" or df_wk.empty:
            st.markdown(
                "Hit **▶ Play** on the map timeline to watch 26 fire seasons unfold.  \n"
                "Point colour shows how many of the 26 years that pixel has burned — "
                "**deep red = chronic hotspot**, amber = occasional."
            )
            with st.spinner("Building animation (first load may take ~10 s)…"):
                anim_map = make_animated_year_map(df_yr)
            components.html(anim_map._repr_html_(), height=580)
            st.caption(
                f"{len(avail_years)} years · up to 1,500 fire pixels sampled per year · "
                "chronic hotspots always included · NASA FIRMS MODIS 1km"
            )

        else:
            wk_years = sorted(df_wk["year"].unique(), reverse=True)
            sel_year = st.selectbox("Fire season", wk_years, key="wk_year")
            n_weeks = df_wk[df_wk["year"] == sel_year]["week"].nunique()
            st.markdown(
                f"Watch **{sel_year}** week by week across the fire season.  \n"
                f"{n_weeks} weeks of data · hit **▶ Play** to animate."
            )
            with st.spinner("Building weekly animation…"):
                wk_map = make_weekly_animated_map(df_wk, sel_year)
            components.html(wk_map._repr_html_(), height=580)
            st.caption(f"{sel_year} · weekly FIRMS data · NASA FIRMS MODIS 1km")

        if df_wk.empty:
            with st.expander("ℹ️ How to unlock weekly drill-down"):
                st.markdown("""
**Weekly data requires a GEE re-export.** Once you have it, the weekly animation
activates automatically.

```bash
# 1. Run the weekly GEE export (picks up the current year by default)
python retrospective_analysis.py --weekly 2024

# 2. After the Drive export lands, convert TIF → CSV
python process_retrospective.py --weekly "path/to/ChiangMai_fire_weekly_2024_FIRMS.tif"

# 3. Commit the result
git add data/fire_by_week.csv && git commit -m "Add weekly fire data 2024" && git push
```
""")
