"""
Generates a bilingual Thai/English findings report as a printable HTML file.
Run: python findings_summary.py
Output: reports/findings_YYYYMMDD.html
"""

import pandas as pd
import glob
import os
from datetime import datetime

OUTPUT_DIR = "reports"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TEMPLATE = """<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>รายงานจุดความร้อนเชียงใหม่ | Chiang Mai Fire Report</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600;700&display=swap');
  body {{ font-family: 'Sarabun', sans-serif; background: #0f0f0f; color: #e0e0e0; margin: 0; padding: 0; }}
  .header {{ background: linear-gradient(135deg, #1a0000, #3d0000); padding: 40px; text-align: center; border-bottom: 2px solid #cc2200; }}
  .header h1 {{ font-size: 2.2em; color: #ff4422; margin: 0 0 8px 0; }}
  .header h2 {{ font-size: 1.1em; color: #aaaaaa; margin: 0; font-weight: 300; }}
  .date {{ color: #888; font-size: 0.9em; margin-top: 10px; }}
  .stats {{ display: flex; justify-content: center; gap: 30px; padding: 40px; flex-wrap: wrap; }}
  .stat-box {{ background: #1a1a1a; border: 1px solid #333; border-top: 3px solid #cc2200;
               padding: 24px 32px; text-align: center; min-width: 160px; }}
  .stat-box .number {{ font-size: 2.8em; font-weight: 700; color: #ff4422; }}
  .stat-box .label {{ font-size: 0.85em; color: #888; margin-top: 4px; }}
  .section {{ max-width: 900px; margin: 0 auto; padding: 20px 40px; }}
  .section h3 {{ color: #ff6644; border-bottom: 1px solid #333; padding-bottom: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
  th {{ background: #1a1a1a; color: #aaa; padding: 10px; text-align: left; border: 1px solid #333; }}
  td {{ padding: 8px 10px; border: 1px solid #222; }}
  tr:nth-child(even) {{ background: #111; }}
  .alert {{ background: #2a0000; border: 1px solid #cc2200; padding: 16px 20px;
            border-radius: 4px; margin: 20px 0; font-size: 1.05em; }}
  .footer {{ text-align: center; padding: 30px; color: #444; font-size: 0.8em; border-top: 1px solid #222; }}
  .footer a {{ color: #666; }}
  @media print {{ body {{ background: white; color: black; }}
    .header {{ background: #cc2200; }} .stat-box {{ border-color: #ccc; }}
    .alert {{ background: #fff0f0; border-color: #cc2200; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>⚠ รายงานสถานการณ์ไฟ จังหวัดเชียงใหม่</h1>
  <h2>Chiang Mai Active Fire Detection Report</h2>
  <div class="date">{date_th} &nbsp;|&nbsp; {date_en} &nbsp;|&nbsp; ข้อมูล: NASA FIRMS VIIRS 375m</div>
</div>

<div class="stats">
  <div class="stat-box">
    <div class="number">{total_fires:,}</div>
    <div class="label">จุดความร้อนใน 24 ชม.<br>Fire detections (24h)</div>
  </div>
  <div class="stat-box">
    <div class="number">{max_frp:.1f}</div>
    <div class="label">ค่า FRP สูงสุด (MW)<br>Peak fire radiative power</div>
  </div>
  <div class="stat-box">
    <div class="number">{avg_frp:.1f}</div>
    <div class="label">ค่า FRP เฉลี่ย (MW)<br>Average fire intensity</div>
  </div>
  <div class="stat-box">
    <div class="number">{high_confidence}</div>
    <div class="label">จุดความเชื่อมั่นสูง<br>High-confidence detections</div>
  </div>
</div>

<div class="section">
  <div class="alert">
    <strong>⚠ ข้อสังเกต / Observation:</strong><br>
    พบจุดความร้อนจำนวน {total_fires:,} จุด ในพื้นที่จังหวัดเชียงใหม่และจังหวัดใกล้เคียงภายใน 24 ชั่วโมงที่ผ่านมา
    ซึ่งสูงกว่าเกณฑ์เตือนภัยที่ตั้งไว้ (20 จุด) อย่างมีนัยสำคัญ
    ข้อมูลนี้มาจากดาวเทียม VIIRS ของ NASA ความละเอียด 375 เมตร<br><br>
    {total_fires:,} fire detections recorded across the Chiang Mai region in the last 24 hours —
    significantly exceeding the alert threshold of 20. Source: NASA FIRMS VIIRS 375m satellite.
  </div>

  <h3>📍 จุดความร้อนสูงสุด 20 อันดับ | Top 20 Hottest Detections</h3>
  {top_table}

  <h3>📊 ข้อมูลดิบ | Raw Statistics</h3>
  <table>
    <tr><th>ตัวชี้วัด / Metric</th><th>ค่า / Value</th></tr>
    <tr><td>จำนวนจุดทั้งหมด / Total detections</td><td>{total_fires:,}</td></tr>
    <tr><td>ค่า FRP สูงสุด / Max FRP (MW)</td><td>{max_frp:.2f}</td></tr>
    <tr><td>ค่า FRP เฉลี่ย / Mean FRP (MW)</td><td>{avg_frp:.2f}</td></tr>
    <tr><td>ค่า FRP มัธยฐาน / Median FRP (MW)</td><td>{med_frp:.2f}</td></tr>
    <tr><td>ช่วงละติจูด / Latitude range</td><td>{lat_min:.3f}° – {lat_max:.3f}° N</td></tr>
    <tr><td>ช่วงลองจิจูด / Longitude range</td><td>{lon_min:.3f}° – {lon_max:.3f}° E</td></tr>
    <tr><td>แหล่งข้อมูล / Data source</td><td>NASA FIRMS VIIRS NOAA-20 NRT</td></tr>
    <tr><td>วันที่รายงาน / Report generated</td><td>{date_en} UTC</td></tr>
  </table>

  <h3>🔬 วิธีการ | Methodology</h3>
  <p>ข้อมูลนี้ดึงมาจาก NASA FIRMS API (Fire Information for Resource Management System)
  โดยใช้เซ็นเซอร์ VIIRS ความละเอียด 375 เมตร บนดาวเทียม NOAA-20
  พื้นที่ครอบคลุมกรอบพิกัด 97.5°E–99.5°E, 17.5°N–20.5°N (จังหวัดเชียงใหม่และพื้นที่ใกล้เคียง)</p>

  <p>Data sourced from the NASA FIRMS API using the VIIRS 375m sensor aboard NOAA-20.
  Coverage: bounding box 97.5–99.5°E, 17.5–20.5°N (Chiang Mai province and surroundings).
  FRP (Fire Radiative Power) measures energy output in megawatts — a proxy for fire intensity and burned biomass.</p>

  <p>โค้ดเต็มและข้อมูลดิบเผยแพร่แบบ open source ที่:<br>
  Full code and raw data available open source at:<br>
  <strong>github.com/ChiangFai/ChiangFai</strong></p>
</div>

<div class="footer">
  Open Spatial Analysis of Agricultural Burning Patterns in Northern Thailand &nbsp;·&nbsp;
  <a href="https://github.com/ChiangFai/ChiangFai">github.com/ChiangFai/ChiangFai</a><br>
  Data: NASA FIRMS, Copernicus Sentinel-2 &nbsp;·&nbsp; MIT License &nbsp;·&nbsp;
  ข้อมูลสาธารณะ เผยแพร่เพื่อการวิจัยและสาธารณประโยชน์
</div>
</body>
</html>"""


def build_top_table(df: pd.DataFrame) -> str:
    top = df.nlargest(20, "frp")[["latitude", "longitude", "frp", "confidence", "acq_datetime"]].copy()
    rows = ""
    for _, r in top.iterrows():
        rows += f"<tr><td>{r['latitude']:.4f}°N</td><td>{r['longitude']:.4f}°E</td>"
        rows += f"<td><strong>{r['frp']:.2f}</strong></td><td>{r.get('confidence','–')}</td>"
        rows += f"<td>{str(r.get('acq_datetime','–'))[:16]}</td></tr>"
    header = "<table><tr><th>ละติจูด / Lat</th><th>ลองจิจูด / Lon</th><th>FRP (MW)</th><th>Confidence</th><th>เวลา / Time (UTC)</th></tr>"
    return header + rows + "</table>"


def generate_report(df: pd.DataFrame):
    if "acq_datetime" in df.columns:
        df["acq_datetime"] = pd.to_datetime(df["acq_datetime"])

    now = datetime.utcnow()
    thai_months = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
                   "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    date_th = f"{now.day} {thai_months[now.month]} {now.year + 543}"
    date_en = now.strftime("%d %B %Y %H:%M")

    high_conf = len(df[df["confidence"].isin(["h", "high"])]) if "confidence" in df.columns else 0

    html = TEMPLATE.format(
        date_th=date_th,
        date_en=date_en,
        total_fires=len(df),
        max_frp=df["frp"].max(),
        avg_frp=df["frp"].mean(),
        med_frp=df["frp"].median(),
        high_confidence=high_conf,
        lat_min=df["latitude"].min(),
        lat_max=df["latitude"].max(),
        lon_min=df["longitude"].min(),
        lon_max=df["longitude"].max(),
        top_table=build_top_table(df),
    )

    out = os.path.join(OUTPUT_DIR, f"findings_{now.strftime('%Y%m%d')}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved: {out}")
    print("Open in browser, then File → Print → Save as PDF")
    return out


if __name__ == "__main__":
    snapshots = sorted(glob.glob("data/firms_snapshot_*.csv"))
    if not snapshots:
        print("No snapshots found. Run real_time_alerts.py first.")
    else:
        df = pd.read_csv(snapshots[-1])
        generate_report(df)
