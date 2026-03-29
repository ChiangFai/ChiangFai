import requests
import pandas as pd
from datetime import datetime, timedelta

# Get your free MAP_KEY from https://firms.modaps.eosdis.nasa.gov/api/map_key
MAP_KEY = "4f412b8b6d507d17c0682871f13c3618"

# Chiang Mai bounding box: west, south, east, north
BBOX = "97.5,17.5,99.5,20.5"

# Coordinated-burn detection threshold: fires in 24h before flagging
ALERT_THRESHOLD = 20


def get_recent_fires(days: int = 1, source: str = "VIIRS_NOAA20_NRT") -> pd.DataFrame:
    """
    Fetch active fire detections from NASA FIRMS API.
    Automatically retries with fewer days if the API rejects the request.
    days: 1–10
    source: VIIRS_NOAA20_NRT | VIIRS_SNPP_NRT | MODIS_NRT
    """
    from io import StringIO
    import time

    for attempt_days in range(days, 0, -1):
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{source}/{BBOX}/{attempt_days}"
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text))
            if attempt_days < days:
                print(f"Note: API accepted {attempt_days} days (requested {days})")
            if df.empty:
                print("No fire detections returned.")
                return df
            df["acq_datetime"] = pd.to_datetime(
                df["acq_date"] + " " + df["acq_time"].astype(str).str.zfill(4),
                format="%Y-%m-%d %H%M",
            )
            return df
        except requests.HTTPError as e:
            if e.response.status_code == 400 and attempt_days > 1:
                print(f"API rejected {attempt_days} days, retrying with {attempt_days - 1}...")
                time.sleep(1)
                continue
            raise

    return pd.DataFrame()


def check_coordinated_burns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag events where fire count exceeds threshold — potential coordinated ignition.
    Expand with spatial clustering (see clustering.py) for ring-pattern detection.
    """
    count = len(df)
    if count > ALERT_THRESHOLD:
        print(f"ALERT: {count} fire detections in window — possible coordinated event.")
    else:
        print(f"{count} detections — within normal range.")
    return df


def save_snapshot(df: pd.DataFrame):
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M")
    path = f"data/firms_snapshot_{ts}.csv"
    df.to_csv(path, index=False)
    print(f"Saved: {path}")


if __name__ == "__main__":
    fires = get_recent_fires(days=1)
    if not fires.empty:
        fires = check_coordinated_burns(fires)
        save_snapshot(fires)
        print(fires[["acq_datetime", "latitude", "longitude", "frp", "confidence"]].head(20))
