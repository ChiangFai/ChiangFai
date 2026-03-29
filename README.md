**🌐 [ภาษาไทย](README.th.md) · [English](README.md) · [中文](README.zh.md)**

# Open Spatial Analysis of Agricultural Burning Patterns in Northern Thailand

**2018–2026 · Chiang Mai Province · Satellite-derived burn forensics**

This project uses freely available satellite data (NASA FIRMS, Copernicus Sentinel-2) and Google Earth Engine to map, quantify, and analyze wildfire and agricultural burning patterns across Chiang Mai province over an eight-year period.

The goal is to produce reproducible, publicly verifiable spatial datasets that any researcher, journalist, NGO, or government body can independently validate.

---

## What this does

| Module | Purpose |
|---|---|
| `retrospective_analysis.py` | Annual burned area mapping via Sentinel-2 dNBR (2018–2026); exports burn recurrence raster |
| `real_time_alerts.py` | Polls NASA FIRMS API for active fire detections; saves timestamped CSV snapshots |
| `clustering.py` | DBSCAN spatial clustering on fire points; flags temporally simultaneous cluster events |
| `dashboard/app.py` | Streamlit dashboard for interactive exploration |

---

## Quickstart

```bash
pip install -r requirements.txt
```

**Authenticate Google Earth Engine (once):**
```python
# In gee_setup.py, uncomment ee.Authenticate() and run once
python gee_setup.py
```

**Get a free NASA FIRMS API key:**
→ https://firms.modaps.eosdis.nasa.gov/api/map_key/
Set it in `real_time_alerts.py` as `MAP_KEY`.

**Run retrospective analysis:**
```bash
python retrospective_analysis.py
```
This queues a GEE export to your Google Drive (scale 10m, ~few hours).

**Fetch recent fires:**
```bash
python real_time_alerts.py
```

**Cluster and flag coordinated events:**
```bash
python clustering.py
```

**Launch dashboard:**
```bash
streamlit run dashboard/app.py
```

---

## Data sources

| Dataset | Provider | Access |
|---|---|---|
| VIIRS 375m active fires | NASA FIRMS | Free API |
| Sentinel-2 SR (10m) | Copernicus / ESA via GEE | Free (GEE account required) |
| Thailand admin boundaries (ADM2/ADM3) | geoBoundaries | https://www.geoboundaries.org/ |

---

## Methodology notes

- **dNBR threshold:** `> 0.2` used for burned area classification. Agricultural fires in tropical settings may warrant a lower threshold (0.1–0.15); adjust in `get_burned_area()`.
- **Burn season:** Pre-fire composite Nov–Dec; post-fire composite Mar–Apr. Adjust for other regions.
- **FIRMS confidence filter:** Not applied by default — filter on `confidence >= 'nominal'` for stricter analysis.
- **Clustering:** DBSCAN with haversine distance. Default `eps=5km`, `min_samples=3`. Tune for local fire density.

---

## Contributing

Pull requests welcome. Issues for data corrections, methodology improvements, or region expansions are encouraged.

---

## License

MIT. Data remains subject to original provider terms (NASA, ESA/Copernicus).
