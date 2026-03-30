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

# ── Animation fragment (must be module-level for st.fragment to work) ─────────
@st.fragment
def _render_animation():
    import time as _t
    df_wk = load_fire_by_week()

    if df_wk.empty:
        st.warning("Weekly fire data not available. Run the GEE weekly export first.")
        return

    wk_years = sorted(df_wk["year"].unique())

    mode = st.radio(
        "Show", ["📅 Year range", "🔍 Single season"],
        horizontal=True, key="anim_mode",
    )

    if mode == "🔍 Single season":
        sel_year = st.selectbox(
            "Fire season", sorted(wk_years, reverse=True), key="wk_year"
        )
        wk_src = df_wk[df_wk["year"] == sel_year]
    else:
        yr_min, yr_max = int(wk_years[0]), int(wk_years[-1])
        year_range = st.slider(
            "Year range", yr_min, yr_max, (yr_min, yr_max), step=1, key="anim_yr_range"
        )
        wk_src = df_wk[(df_wk["year"] >= year_range[0]) & (df_wk["year"] <= year_range[1])]

    # Build ordered (year, week) frame list
    frames = sorted(wk_src[["year", "week"]].drop_duplicates().itertuples(index=False))

    if "anim_idx" not in st.session_state:
        st.session_state["anim_idx"] = 0
    if "anim_playing" not in st.session_state:
        st.session_state["anim_playing"] = False

    # Clamp index any time the frame count shrinks (e.g. range narrowed)
    if st.session_state["anim_idx"] >= len(frames):
        st.session_state["anim_idx"] = 0

    idx = min(st.session_state["anim_idx"], len(frames) - 1)

    # Row 1: jump + speed
    j1, j2 = st.columns([1, 2])
    with j1:
        frame_years = sorted(set(f.year for f in frames))
        jump_year = st.selectbox("Jump to year", frame_years,
                                 index=len(frame_years) - 1, key="anim_jump_year")
        if st.session_state.get("anim_last_jump") != jump_year:
            st.session_state["anim_last_jump"] = jump_year
            st.session_state["anim_idx"] = next(
                (i for i, f in enumerate(frames) if f.year == jump_year), 0
            )
            st.session_state["anim_playing"] = False
    with j2:
        speed = st.slider("Seconds per frame", 0.3, 3.0, 0.8, step=0.1, key="anim_speed")

    # Row 2: play / restart
    c1, c2 = st.columns([1, 1])
    with c1:
        btn_label = "⏸ Pause" if st.session_state["anim_playing"] else "▶ Play"
        if st.button(btn_label, key="anim_btn_play"):
            st.session_state["anim_playing"] = not st.session_state["anim_playing"]
            st.rerun(scope="fragment")
    with c2:
        if st.button("↩ Restart", key="anim_btn_restart"):
            st.session_state["anim_idx"] = 0
            st.session_state["anim_playing"] = False
            st.rerun(scope="fragment")

    import datetime as _dt
    year, week = frames[idx].year, frames[idx].week
    try:
        week_start = _dt.date.fromisocalendar(int(year), int(week), 1)
        week_end   = _dt.date.fromisocalendar(int(year), int(week), 7)
        date_label = f"{week_start.strftime('%d %b')} – {week_end.strftime('%d %b %Y')}"
    except Exception:
        date_label = f"Week {week}"

    st.markdown(
        f"<div style='background:#1a0000;border-left:4px solid #ff4422;padding:8px 14px;margin-bottom:8px'>"
        f"<b style='color:#ff4422;font-size:1.2em'>ONE WEEK OF DATA</b><br>"
        f"<span style='color:#eee;font-size:1.1em'>{date_label}</span>"
        f"<span style='color:#666;font-size:0.85em'> · frame {idx+1} of {len(frames)}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    fires = wk_src[
        (wk_src["year"] == year) & (wk_src["week"] == week)
    ][["latitude", "longitude"]].copy()
    fires["burn_count"] = 1

    if fires.empty:
        st.info("No fire detections this week.")
    else:
        components.html(make_weekly_fire_map(fires)._repr_html_(), height=520)
    st.caption(f"{len(fires):,} individual fire pixels detected this single week · NASA FIRMS MODIS 1km")

    if st.session_state["anim_playing"]:
        _t.sleep(speed)
        st.session_state["anim_idx"] = (idx + 1) % len(frames)
        st.rerun(scope="fragment")


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_live, tab_retro, tab_compare, tab_anim, tab_predict = st.tabs([
    "🔴 Live Fires (24h)",
    "📊 26-Year Recurrence (2000–2025)",
    "⚡ Side-by-Side Comparison",
    "🎬 Fire Season Animation",
    "🚨 Prediction & Alerts",
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


def make_weekly_fire_map(df_fires):
    """Precise dot map — one dot per fire pixel, no clustering, no heatmap spreading."""
    m = folium.Map(location=[18.8, 98.9], zoom_start=9, tiles="CartoDB dark_matter")
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(lon), float(lat)],
                },
                "properties": {},
            }
            for lat, lon in zip(df_fires["latitude"], df_fires["longitude"])
        ],
    }
    folium.GeoJson(
        geojson,
        marker=folium.CircleMarker(
            radius=4, fill_color="#ff4422", fill_opacity=0.85, color="", weight=0
        ),
    ).add_to(m)
    return m


def make_recurrence_map(df_rec, zoom=8, min_count=1):
    from folium.plugins import HeatMap
    if df_rec.empty:
        return folium.Map(location=[18.8, 98.9], zoom_start=zoom, tiles="CartoDB dark_matter")
    df_plot = df_rec[df_rec["burn_count"] >= min_count]
    if df_plot.empty:
        return folium.Map(location=[18.8, 98.9], zoom_start=zoom, tiles="CartoDB dark_matter")

    m = folium.Map(location=[18.8, 98.9], zoom_start=8, tiles="CartoDB dark_matter")

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


@st.cache_data(ttl=300)
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
    _render_animation()


# ── Tab 5: Prediction & Alerts ────────────────────────────────────────────────
with tab_predict:
    import datetime as _dt

    df_yr = load_fire_by_year()
    df_wk = load_fire_by_week()

    if "firms_df" not in st.session_state:
        with st.spinner("Loading live fire data..."):
            _live, _note = get_data(1, "VIIRS_NOAA20_NRT", MAP_KEY)
            st.session_state["firms_df"] = _live
            st.session_state["firms_note"] = _note
    df_live = st.session_state.get("firms_df", pd.DataFrame())

    current_week = _dt.date.today().isocalendar()[1]
    current_year = _dt.date.today().year

    st.markdown(
        f"**Today is week {current_week} of {current_year}** — "
        "the fire season in Chiang Mai runs weeks 6–20 (Feb–May)."
    )

    if df_yr.empty:
        st.warning("Requires fire_by_year.csv — see Tab 2.")
    else:
        avail_years = sorted([int(c[1:]) for c in df_yr.columns if c.startswith("y")])

        # ── Chronic hotspot alert ─────────────────────────────────────────────
        st.subheader("🔴 Live fires hitting chronic hotspots")
        st.caption(
            "Chronic hotspot = pixel that burned in 10+ of 26 years. "
            "A live fire here is not random — it is the pattern repeating."
        )

        year_cols = [f"y{y}" for y in avail_years if f"y{y}" in df_yr.columns]
        df_yr_work = df_yr[["latitude", "longitude"] + year_cols].copy()
        df_yr_work["total_burns"] = df_yr_work[year_cols].fillna(0).sum(axis=1)
        chronic = df_yr_work[df_yr_work["total_burns"] >= 10][["latitude", "longitude", "total_burns"]]

        min_recur_thresh = st.slider(
            "Chronic threshold (years burned)", 5, 20, 10, key="pred_thresh"
        )
        chronic = df_yr_work[df_yr_work["total_burns"] >= min_recur_thresh][
            ["latitude", "longitude", "total_burns"]
        ]

        if not df_live.empty and not chronic.empty:
            # Round live coords to same precision as historical data
            df_live_r = df_live.copy()
            df_live_r["lat_r"] = df_live_r["latitude"].round(2)
            df_live_r["lon_r"] = df_live_r["longitude"].round(2)
            chronic_r = chronic.copy()
            chronic_r["lat_r"] = chronic_r["latitude"].round(2)
            chronic_r["lon_r"] = chronic_r["longitude"].round(2)
            hits = df_live_r.merge(
                chronic_r[["lat_r", "lon_r", "total_burns"]], on=["lat_r", "lon_r"], how="inner"
            )
            hit_pct = len(hits) / max(len(df_live), 1) * 100

            if len(hits) > 0:
                st.error(
                    f"⚠ **{len(hits):,} live detections** are inside chronic hotspot zones "
                    f"({hit_pct:.0f}% of today's fires). These locations have burned an average "
                    f"of **{hits['total_burns'].mean():.1f} of {len(avail_years)} years**."
                )
            else:
                st.success("No live fires currently overlap chronic hotspot zones.")
        else:
            st.info("Fetch live fire data (Tab 1) to run the hotspot overlap check.")

        # ── Predicted ignition zones this week ───────────────────────────────
        st.subheader(f"📍 Predicted ignition zones — week {current_week}")

        if not df_wk.empty:
            # Weekly data: probability = fraction of years that burned this week
            hist_this_week = df_wk[df_wk["week"] == current_week]
            wk_avail_years = df_wk["year"].nunique()
            if not hist_this_week.empty:
                freq = (
                    hist_this_week.groupby(["latitude", "longitude"])
                    .size()
                    .reset_index(name="years_burned")
                )
                freq["probability"] = (freq["years_burned"] / wk_avail_years * 100).round(1)
                high_risk = freq[freq["probability"] >= 30].sort_values("probability", ascending=False)
                st.caption(
                    f"{len(high_risk):,} pixels have burned during week {current_week} "
                    f"in 30%+ of historical years — these are this week's predicted ignition zones."
                )

                # Map: predicted zones + live fires
                m_pred = folium.Map(location=[18.8, 98.9], zoom_start=8, tiles="CartoDB dark_matter")
                from folium.plugins import HeatMap
                if not high_risk.empty:
                    HeatMap(
                        [[r["latitude"], r["longitude"], r["probability"] / 100]
                         for _, r in high_risk.iterrows()],
                        min_opacity=0.3, radius=8, blur=6,
                        gradient={0.3: "#ffcc00", 0.6: "#ff6600", 1.0: "#cc0000"},
                        name="Predicted zones",
                    ).add_to(m_pred)
                    # Cyan dots: exact predicted pixel centres
                    geojson_pred = {"type": "FeatureCollection", "features": [
                        {"type": "Feature",
                         "geometry": {"type": "Point", "coordinates": [float(r["longitude"]), float(r["latitude"])]},
                         "properties": {"prob": r["probability"]}}
                        for _, r in high_risk.iterrows()
                    ]}
                    folium.GeoJson(
                        geojson_pred,
                        marker=folium.CircleMarker(radius=3, fill_color="#00ffff",
                                                   fill_opacity=0.7, color="", weight=0),
                        tooltip=folium.GeoJsonTooltip(fields=["prob"], aliases=["Burn probability (%)"]),
                        name="Predicted pixels",
                    ).add_to(m_pred)
                if not df_live.empty:
                    for _, row in df_live.iterrows():
                        folium.CircleMarker(
                            location=[row["latitude"], row["longitude"]],
                            radius=5, color="#ffffff", fill=True,
                            fill_color="#ffffff", fill_opacity=0.95, weight=0,
                            tooltip="Live fire today",
                        ).add_to(m_pred)
                folium.LayerControl().add_to(m_pred)
                components.html(m_pred._repr_html_(), height=520)
                st.caption(
                    "Yellow–red glow = predicted ignition zones (historical week frequency). "
                    "Cyan dots = exact predicted pixels. White dots = live fires today. "
                    "Cyan + white overlap = pattern confirmed in real time."
                )

                if len(hits) > 0 if not df_live.empty else False:
                    overlap = high_risk.merge(
                        df_live_r[["lat_r", "lon_r"]].assign(
                            latitude=df_live_r["latitude"], longitude=df_live_r["longitude"]
                        ),
                        left_on=[high_risk["latitude"].round(2), high_risk["longitude"].round(2)],
                        right_on=["lat_r", "lon_r"], how="inner"
                    )
                    if not overlap.empty:
                        st.error(
                            f"🔴 **Pattern confirmed:** {len(overlap):,} live fires are burning "
                            f"inside this week's predicted zones — exactly where history says they would be."
                        )
            else:
                st.info(f"No historical fires recorded during week {current_week} in the dataset.")
        else:
            # Fallback: use annual chronic hotspots as proxy for "at risk now"
            st.caption(
                "Weekly granularity not yet available — showing chronic hotspots (10+ years) "
                "as at-risk zones. Run `python retrospective_analysis.py --weekly-all` to unlock "
                "week-level predictions."
            )
            chronic_display = chronic.rename(columns={"total_burns": "burn_count"})
            m_pred = folium.Map(location=[18.8, 98.9], zoom_start=8, tiles="CartoDB dark_matter")
            from folium.plugins import HeatMap
            if not chronic_display.empty:
                max_b = chronic_display["burn_count"].max()
                HeatMap(
                    [[r["latitude"], r["longitude"], r["burn_count"] / max_b]
                     for _, r in chronic_display.iterrows()],
                    min_opacity=0.3, radius=8, blur=6,
                    gradient={0.3: "#ffcc00", 0.6: "#ff6600", 1.0: "#cc0000"},
                ).add_to(m_pred)
                geojson_chronic = {"type": "FeatureCollection", "features": [
                    {"type": "Feature",
                     "geometry": {"type": "Point", "coordinates": [float(r["longitude"]), float(r["latitude"])]},
                     "properties": {"years": int(r["burn_count"])}}
                    for _, r in chronic_display.iterrows()
                ]}
                folium.GeoJson(
                    geojson_chronic,
                    marker=folium.CircleMarker(radius=3, fill_color="#00ffff",
                                               fill_opacity=0.7, color="", weight=0),
                    tooltip=folium.GeoJsonTooltip(fields=["years"], aliases=["Years burned"]),
                ).add_to(m_pred)
            if not df_live.empty:
                for _, row in df_live.iterrows():
                    folium.CircleMarker(
                        location=[row["latitude"], row["longitude"]],
                        radius=5, color="#ffffff", fill=True,
                        fill_color="#ffffff", fill_opacity=0.95, weight=0,
                        tooltip="Live fire today",
                    ).add_to(m_pred)
            components.html(m_pred._repr_html_(), height=520)
            st.caption(
                "Yellow–red glow = chronic hotspot zones. "
                "Cyan dots = exact hotspot pixels. White dots = live fires today."
            )

        # ── Seasonal calendar ─────────────────────────────────────────────────
        if not df_wk.empty:
            st.subheader("📅 Expected ignition calendar (by week)")
            import altair as alt
            wk_summary = (
                df_wk[df_wk["week"].between(6, 20)]
                .groupby("week")
                .agg(pixels=("latitude", "count"), years=("year", "nunique"))
                .reset_index()
            )
            wk_summary["avg_pixels"] = (wk_summary["pixels"] / wk_summary["years"]).round(0)
            wk_summary["is_current"] = wk_summary["week"] == current_week
            chart = (
                alt.Chart(wk_summary)
                .mark_bar()
                .encode(
                    x=alt.X("week:O", title="ISO Week"),
                    y=alt.Y("avg_pixels:Q", title="Avg fire pixels"),
                    color=alt.condition(
                        alt.datum.is_current,
                        alt.value("#00ffff"),
                        alt.value("#ff4422"),
                    ),
                    tooltip=["week", "avg_pixels", "years"],
                )
                .properties(
                    title="Average weekly fire activity across all years (cyan = current week)",
                    height=250,
                )
            )
            st.altair_chart(chart, use_container_width=True)
