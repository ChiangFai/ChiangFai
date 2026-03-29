# 泰国北部农业燃烧模式的开放空间分析

**2018–2026 · 清迈府 · 卫星衍生燃烧取证**

本项目使用免费的卫星数据（NASA FIRMS、Copernicus Sentinel-2）和 Google Earth Engine，对清迈府八年间的野火和农业燃烧模式进行制图、量化和分析。

目标是生成可重现、可公开验证的空间数据集，供研究人员、记者、NGO 或政府机构独立核实。

---

## 功能概述

| 模块 | 用途 |
|---|---|
| `retrospective_analysis.py` | 通过 Sentinel-2 dNBR 进行年度烧毁面积制图（2018–2026）；导出燃烧复发栅格数据 |
| `real_time_alerts.py` | 轮询 NASA FIRMS API 获取活跃火点探测数据；保存带时间戳的 CSV 快照 |
| `clustering.py` | 对火点进行 DBSCAN 空间聚类；标记时间上同步的聚类事件 |
| `dashboard/app.py` | 用于交互式探索的 Streamlit 仪表板 |

---

## 快速开始

```bash
pip install -r requirements.txt
```

**验证 Google Earth Engine（仅需一次）：**
```python
# 在 gee_setup.py 中取消注释 ee.Authenticate() 并运行一次
python gee_setup.py
```

**获取免费的 NASA FIRMS API key：**
→ https://firms.modaps.eosdis.nasa.gov/api/map_key/
在 `real_time_alerts.py` 中设置为 `MAP_KEY`

**运行回溯分析：**
```bash
python retrospective_analysis.py
```
此操作将向您的 Google Drive 提交 GEE 导出任务（分辨率 10m，约需数小时）。

**获取近期火情数据：**
```bash
python real_time_alerts.py
```

**聚类并标记协同事件：**
```bash
python clustering.py
```

**启动仪表板：**
```bash
streamlit run dashboard/app.py
```

---

## 数据来源

| 数据集 | 提供方 | 获取方式 |
|---|---|---|
| VIIRS 375m 活跃火点 | NASA FIRMS | 免费 API |
| Sentinel-2 SR（10m）| Copernicus / ESA via GEE | 免费（需 GEE 账户）|
| 泰国行政边界（ADM2/ADM3）| geoBoundaries | https://www.geoboundaries.org/ |

---

## 方法说明

- **dNBR 阈值：** 使用 `> 0.2` 进行烧毁面积分类。热带地区的农业火灾可能需要较低的阈值（0.1–0.15）；在 `get_burned_area()` 中调整。
- **燃烧季节：** 火前复合影像为 11–12 月；火后复合影像为 3–4 月。其他地区请相应调整。
- **FIRMS 置信度过滤：** 默认不应用——如需更严格的分析，可按 `confidence >= 'nominal'` 进行过滤。
- **聚类：** 使用 haversine 距离的 DBSCAN。默认 `eps=5km`，`min_samples=3`。根据当地火点密度进行调整。

---

## 贡献

欢迎提交 pull requests。鼓励就数据纠错、方法改进或区域扩展提交 issues。

---

## 许可证

MIT。数据仍受原始提供方条款约束（NASA、ESA/Copernicus）。
