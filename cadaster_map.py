"""
Generate an interactive Leaflet webmap from merged parcels.
- Reprojects EPSG:2039 -> WGS84
- Hebrew + RTL UI
- Sidebar with: basemap switcher, symbology by column, per-column filters
- Uses CartoDB / Esri tiles (no OSM "Access blocked" 403)
"""

from pathlib import Path
import json
import pandas as pd
import geopandas as gpd


# ---------------------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------------------
def read_parcels(file_path):
    return pd.read_excel(file_path)


df = read_parcels('parcels.xlsx')

parcels = gpd.read_file(
    r'C:\Users\Medad\OneDrive - Keren Kayemeth LeIsrael, Jewish National Fund'
    r'\Desktop\GeomAI\SmartCAD\scripts_exe\scripts\temp_compi\parcel.gpkg'
)

merged = pd.merge(
    df,
    parcels[['PARCEL', 'GUSH_NUM', 'mavatStaDE', 'geometry',
             'mavat_code', 'pl_number']],
    left_on=['חלקה', 'גוש'],
    right_on=['PARCEL', 'GUSH_NUM'],
    how='inner'
)

# ---------------------------------------------------------------------------
# 2. CRS handling: 2039 -> WGS84
# ---------------------------------------------------------------------------
merged_gdf = gpd.GeoDataFrame(merged, geometry='geometry', crs=parcels.crs)

if merged_gdf.crs is None:
    merged_gdf.set_crs(epsg=2039, inplace=True)
elif merged_gdf.crs.to_epsg() != 2039:
    merged_gdf = merged_gdf.to_crs(epsg=2039)

merged_wgs84 = merged_gdf.to_crs(epsg=4326)

GPKG_OUT = Path('merged_parcels.gpkg')
merged_gdf.to_file(GPKG_OUT, driver='GPKG', engine='pyogrio')

# ---------------------------------------------------------------------------
# 3. Build GeoJSON
# ---------------------------------------------------------------------------
merged_wgs84 = merged_wgs84[~merged_wgs84.geometry.is_empty & merged_wgs84.geometry.notna()].copy()

if len(merged_wgs84):
    minx, miny, maxx, maxy = merged_wgs84.total_bounds
    bounds = [[miny, minx], [maxy, maxx]]
else:
    bounds = [[29.5, 34.2], [33.4, 35.9]]


def _to_jsonable(v):
    if pd.isna(v):
        return None
    if isinstance(v, (pd.Timestamp,)):
        return str(v)
    try:
        return v.item()
    except Exception:
        return v if isinstance(v, (int, float, bool, str)) else str(v)


properties_cols = [c for c in merged_wgs84.columns if c != 'geometry']
features = []
for _, row in merged_wgs84.iterrows():
    props = {c: _to_jsonable(row[c]) for c in properties_cols}
    features.append({
        "type": "Feature",
        "properties": props,
        "geometry": row.geometry.__geo_interface__,
    })

geojson = {"type": "FeatureCollection", "features": features}
geojson_str = json.dumps(geojson, ensure_ascii=False)
bounds_str = json.dumps(bounds)

# ---------------------------------------------------------------------------
# 4. HTML template (uses placeholders to avoid f-string {} headaches)
# ---------------------------------------------------------------------------
HTML_OUT = Path('merged_parcels_map.html')

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<title>מפת חלקות</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<style>
  :root {
    --bg: #f5f7fa;
    --panel: #ffffff;
    --border: #e1e4e8;
    --text: #2c3e50;
    --muted: #6b7280;
    --accent: #1f6feb;
    --accent-soft: #dbeafe;
    --shadow: 0 2px 8px rgba(0,0,0,0.08);
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; height: 100%;
    font-family: "Segoe UI", "Arial Hebrew", Arial, sans-serif;
    color: var(--text); background: var(--bg);
  }
  body { display: flex; flex-direction: column; }

  header {
    height: 50px;
    background: linear-gradient(90deg, #1f6feb, #2c3e50);
    color: white; display: flex; align-items: center;
    padding: 0 18px; box-shadow: var(--shadow);
    z-index: 1100; flex-shrink: 0;
  }
  header h1 { margin: 0; font-size: 16px; font-weight: 600; }
  header .stats { margin-right: auto; font-size: 13px; }
  header .stats b { font-weight: 700; }

  #main { flex: 1; display: flex; min-height: 0; }
  #sidebar {
    width: 340px; background: var(--panel);
    border-left: 1px solid var(--border);
    overflow-y: auto; flex-shrink: 0;
  }
  #map { flex: 1; }

  .panel { border-bottom: 1px solid var(--border); }
  .panel-header {
    padding: 12px 14px; cursor: pointer;
    background: #fafbfc; display: flex;
    align-items: center; justify-content: space-between;
    font-weight: 600; font-size: 13px; user-select: none;
  }
  .panel-header:hover { background: #f1f3f5; }
  .panel-header .arrow { font-size: 11px; color: var(--muted); transition: transform 0.2s; }
  .panel.collapsed .arrow { transform: rotate(-90deg); }
  .panel.collapsed .panel-body { display: none; }
  .panel-body { padding: 12px 14px; font-size: 13px; }

  label.row { display: block; margin-bottom: 8px; font-size: 12px; color: var(--muted); }
  select, input[type="text"] {
    width: 100%; padding: 6px 8px;
    border: 1px solid var(--border); border-radius: 4px;
    font-family: inherit; font-size: 13px; background: white;
  }
  select:focus, input[type="text"]:focus {
    outline: none; border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-soft);
  }
  button {
    padding: 6px 12px; border: 1px solid var(--border);
    background: white; border-radius: 4px; cursor: pointer;
    font-family: inherit; font-size: 12px;
  }
  button:hover { background: #f1f3f5; }
  button.primary { background: var(--accent); color: white; border-color: var(--accent); }
  button.primary:hover { background: #1a5fc7; }

  .filter-col { border: 1px solid var(--border); border-radius: 4px; margin-bottom: 6px; overflow: hidden; }
  .filter-col-header {
    padding: 7px 10px; background: #fafbfc; cursor: pointer;
    display: flex; justify-content: space-between; font-size: 12px; user-select: none;
  }
  .filter-col-header:hover { background: #f1f3f5; }
  .filter-col-body { display: none; padding: 8px 10px; }
  .filter-col.expanded .filter-col-body { display: block; }
  .filter-col-search { margin-bottom: 6px; padding: 4px 6px; font-size: 12px; }
  .filter-checks {
    max-height: 180px; overflow-y: auto;
    border: 1px solid var(--border); border-radius: 3px;
    padding: 4px 6px; background: #fff;
  }
  .filter-checks label { display: block; font-size: 12px; padding: 2px 0; cursor: pointer; }
  .filter-checks input { margin-left: 6px; }
  .filter-badge {
    background: var(--accent); color: white;
    border-radius: 10px; padding: 1px 7px;
    font-size: 10px; margin-right: 6px;
  }

  #legend {
    margin-top: 8px; padding: 8px;
    background: #fafbfc; border: 1px solid var(--border);
    border-radius: 4px; font-size: 12px;
    max-height: 240px; overflow-y: auto;
  }
  #legend .legend-row { display: flex; align-items: center; margin-bottom: 4px; }
  #legend .swatch {
    width: 16px; height: 16px; border-radius: 3px;
    margin-left: 8px; border: 1px solid rgba(0,0,0,0.15); flex-shrink: 0;
  }
  #legend .legend-label { font-size: 12px; flex: 1; word-break: break-word; }

  .leaflet-popup-content {
    direction: rtl; text-align: right;
    font-size: 13px; min-width: 240px;
    margin: 10px 12px !important;
  }
  .leaflet-popup-content table { border-collapse: collapse; width: 100%; }
  .leaflet-popup-content th, .leaflet-popup-content td {
    border-bottom: 1px solid #eee; padding: 4px 6px;
    text-align: right; vertical-align: top;
  }
  .leaflet-popup-content th {
    background: #f4f4f4; font-weight: 600; width: 40%; white-space: nowrap;
  }
  .popup-title {
    margin: 0 0 6px 0; font-size: 13px; font-weight: 700;
    color: var(--accent); border-bottom: 2px solid var(--accent-soft);
    padding-bottom: 4px;
  }

  .toolbar { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }

  @media (max-width: 760px) {
    #main { flex-direction: column; }
    #sidebar { width: 100%; height: 45%; border-left: none; border-bottom: 1px solid var(--border); }
  }
</style>
</head>
<body>

<header>
  <h1>🗺️ מפת חלקות ממוזגות</h1>
  <div class="stats">
    מציג <b id="visibleCount">0</b> מתוך <b id="totalCount">0</b> חלקות
  </div>
</header>

<div id="main">
  <aside id="sidebar">

    <div class="panel" id="panel-basemap">
      <div class="panel-header" onclick="togglePanel('panel-basemap')">
        <span>🗺️ שכבת רקע</span><span class="arrow">▾</span>
      </div>
      <div class="panel-body">
        <select id="basemapSelect"></select>
      </div>
    </div>

    <div class="panel" id="panel-symb">
      <div class="panel-header" onclick="togglePanel('panel-symb')">
        <span>🎨 סימבולוגיה</span><span class="arrow">▾</span>
      </div>
      <div class="panel-body">
        <label class="row">צבע לפי שדה:</label>
        <select id="colorBySelect"></select>

        <label class="row" style="margin-top:10px;">פלטה:</label>
        <select id="paletteSelect">
          <option value="auto">אוטומטי</option>
          <option value="categorical">קטגוריאלי (חי)</option>
          <option value="warm">חם (צהוב→אדום)</option>
          <option value="cool">קר (תכלת→כחול)</option>
          <option value="green">ירוק</option>
          <option value="viridis">Viridis</option>
        </select>

        <div id="legend"><i style="color:var(--muted)">בחר שדה כדי לראות מקרא</i></div>
      </div>
    </div>

    <div class="panel" id="panel-filt">
      <div class="panel-header" onclick="togglePanel('panel-filt')">
        <span>🔍 סינון</span><span class="arrow">▾</span>
      </div>
      <div class="panel-body">
        <div class="toolbar">
          <button class="primary" onclick="applyAllFilters()">החל סינון</button>
          <button onclick="clearAllFilters()">נקה הכל</button>
          <button onclick="zoomToFiltered()">זום לסינון</button>
        </div>
        <div id="filtersList"></div>
      </div>
    </div>

  </aside>

  <div id="map"></div>
</div>

<script>
  const GEOJSON = __GEOJSON_DATA__;
  const BOUNDS  = __BOUNDS_DATA__;

  const EXCLUDED_COLS = new Set(['geometry']);
  const ALL_COLS = (GEOJSON.features[0]
    ? Object.keys(GEOJSON.features[0].properties).filter(c => !EXCLUDED_COLS.has(c))
    : []);

  function isNumericColumn(col) {
    let total = 0, numeric = 0;
    for (const f of GEOJSON.features) {
      const v = f.properties[col];
      if (v === null || v === undefined || v === '') continue;
      total++;
      if (!isNaN(parseFloat(v)) && isFinite(v)) numeric++;
    }
    return total > 0 && (numeric / total) > 0.8;
  }

  // Tag column = string column where values look like comma-separated lists
  // (e.g. בעלות = "רט\"ג, רמ\"י, רשות לפיתוח"). At least one row contains a comma.
  function isTagColumn(col) {
    let total = 0, withComma = 0;
    for (const f of GEOJSON.features) {
      const v = f.properties[col];
      if (v === null || v === undefined || v === '') continue;
      total++;
      if (String(v).indexOf(',') !== -1) withComma++;
    }
    return total > 0 && withComma > 0;
  }

  function splitTags(v) {
    if (v === null || v === undefined || v === '') return [];
    return String(v).split(',').map(s => normalizeValue(s)).filter(s => s.length > 0);
  }

  // Normalize for comparison/grouping: strip RTL/LTR marks, zero-width chars,
  // trim and collapse internal whitespace. Used so that "רמ\"י" and "רמ\"י "
  // (e.g. with a trailing space or invisible mark) collapse to the same key.
  function normalizeValue(v) {
    if (v === null || v === undefined) return '';
    let s = String(v);
    // remove zero-width + bidi control chars
    s = s.replace(/[\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]/g, '');
    // trim & collapse all whitespace (including non-breaking space)
    s = s.replace(/\s+/g, ' ').trim();
    return s;
  }

  const COL_META = {};
  ALL_COLS.forEach(c => {
    const numeric = isNumericColumn(c);
    COL_META[c] = {
      numeric,
      isTag: !numeric && isTagColumn(c),
      uniques: null,     // tag-split (or non-tag) values
      uniquesRaw: null,  // full original values for tag cols
    };
  });

  function getUniques(col, forceSplit) {
    // forceSplit: undefined => auto (split if isTag), true => always split, false => never split
    const shouldSplit = (forceSplit === undefined) ? COL_META[col].isTag : !!forceSplit;
    if (shouldSplit && COL_META[col].uniques) return COL_META[col].uniques;
    if (!shouldSplit && COL_META[col].uniquesRaw) return COL_META[col].uniquesRaw;

    const set = new Set();
    for (const f of GEOJSON.features) {
      const v = f.properties[col];
      if (v === null || v === undefined || v === '') continue;
      if (shouldSplit) {
        splitTags(v).forEach(t => set.add(t));
      } else {
        const norm = normalizeValue(v);
        if (norm.length > 0) set.add(norm);
      }
    }
    const arr = [...set].sort((a,b) => {
      if (COL_META[col].numeric) return parseFloat(a) - parseFloat(b);
      return a.localeCompare(b, 'he');
    });
    if (shouldSplit) COL_META[col].uniques = arr;
    else COL_META[col].uniquesRaw = arr;
    return arr;
  }

  // -------- Basemaps (work from file://) --------
  const BASEMAPS = {
    'CartoDB - Voyager': L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
      { maxZoom: 19, attribution: '© CARTO © OpenStreetMap', subdomains: 'abcd' }
    ),
    'CartoDB - בהיר': L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
      { maxZoom: 19, attribution: '© CARTO', subdomains: 'abcd' }
    ),
    'CartoDB - כהה': L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      { maxZoom: 19, attribution: '© CARTO', subdomains: 'abcd' }
    ),
    'Esri - רחובות': L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 19, attribution: 'Tiles © Esri' }
    ),
    'Esri - תצלום אוויר': L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 19, attribution: 'Tiles © Esri' }
    ),
    'Esri - טופוגרפי': L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 19, attribution: 'Tiles © Esri' }
    ),
  };

  const map = L.map('map', { zoomControl: true });
  let currentBase = BASEMAPS['CartoDB - Voyager'];
  currentBase.addTo(map);

  const basemapSelect = document.getElementById('basemapSelect');
  Object.keys(BASEMAPS).forEach(name => {
    const opt = document.createElement('option');
    opt.value = name; opt.textContent = name;
    basemapSelect.appendChild(opt);
  });
  basemapSelect.addEventListener('change', e => {
    map.removeLayer(currentBase);
    currentBase = BASEMAPS[e.target.value];
    currentBase.addTo(map);
  });

  // -------- Symbology --------
  const PALETTES = {
    categorical: ['#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00','#ffd92f',
                  '#a65628','#f781bf','#1b9e77','#d95f02','#7570b3','#66a61e',
                  '#e7298a','#666666','#1f78b4','#33a02c'],
    warm:    ['#ffffb2','#fecc5c','#fd8d3c','#f03b20','#bd0026'],
    cool:    ['#f1eef6','#bdc9e1','#74a9cf','#2b8cbe','#045a8d'],
    green:   ['#edf8e9','#bae4b3','#74c476','#31a354','#006d2c'],
    viridis: ['#440154','#3b528b','#21908d','#5dc863','#fde725'],
  };

  const state = {
    colorBy: '',
    palette: 'auto',
    filters: {},
  };

  function colorScale(values, paletteName) {
    const palette = PALETTES[paletteName] || PALETTES.categorical;
    const m = {};
    values.forEach((v, i) => { m[String(v)] = palette[i % palette.length]; });
    return v => m[String(v)] || '#888';
  }

  function quantileBreaks(vals, n) {
    const sorted = [...vals].sort((a,b)=>a-b);
    const breaks = [];
    for (let i = 1; i < n; i++) {
      const idx = Math.floor((i / n) * sorted.length);
      breaks.push(sorted[idx]);
    }
    return breaks;
  }

  function shade(hex, amt) {
    const c = hex.replace('#','');
    const r = Math.max(0, Math.min(255, parseInt(c.substr(0,2),16) + amt));
    const g = Math.max(0, Math.min(255, parseInt(c.substr(2,2),16) + amt));
    const b = Math.max(0, Math.min(255, parseInt(c.substr(4,2),16) + amt));
    return '#' + [r,g,b].map(x => x.toString(16).padStart(2,'0')).join('');
  }

  function buildStyleFn() {
    if (!state.colorBy) {
      return () => ({ color:'#1f4e79', weight:1.5, fillColor:'#3498db', fillOpacity:0.4 });
    }
    let col = state.colorBy;
    let usePrimaryTag = false;
    if (col.indexOf('__tag__:') === 0) {
      col = col.substring('__tag__:'.length);
      usePrimaryTag = true;
    }
    const meta = COL_META[col];
    const reqPal = state.palette;

    if (meta.numeric) {
      const vals = GEOJSON.features
        .map(f => parseFloat(f.properties[col]))
        .filter(v => !isNaN(v));
      if (!vals.length) {
        return () => ({ color:'#666', weight:1.5, fillColor:'#bbb', fillOpacity:0.4 });
      }
      const min = Math.min(...vals), max = Math.max(...vals);
      const palName = (reqPal === 'auto' || reqPal === 'categorical') ? 'warm' : reqPal;
      const palette = PALETTES[palName];
      const breaks = quantileBreaks(vals, palette.length);
      function classify(v) {
        const x = parseFloat(v);
        if (isNaN(x)) return '#888';
        for (let i = 0; i < breaks.length; i++) {
          if (x <= breaks[i]) return palette[i];
        }
        return palette[palette.length - 1];
      }
      buildLegendNumeric(col, min, max, breaks, palette);
      return f => {
        const c = classify(f.properties[col]);
        return { color: shade(c, -20), weight:1, fillColor:c, fillOpacity:0.6 };
      };
    } else {
      const splitMode = !!(meta.isTag && usePrimaryTag);
      const uniques = getUniques(col, splitMode);
      const palName = (reqPal === 'auto' || reqPal === 'warm' || reqPal === 'cool' ||
                      reqPal === 'green' || reqPal === 'viridis')
                      ? 'categorical' : reqPal;
      const scale = colorScale(uniques, palName);
      const legendTitle = splitMode ? (col + ' (תגית ראשונה)') : col;
      buildLegendCategorical(legendTitle, uniques, scale);
      if (splitMode) {
        return f => {
          const tags = splitTags(f.properties[col]);
          const primary = tags[0];
          const c = primary ? scale(primary) : '#aaa';
          return { color: shade(c, -20), weight:1, fillColor:c, fillOpacity:0.6 };
        };
      }
      return f => {
        const v = f.properties[col];
        const norm = normalizeValue(v);
        const c = (norm === '') ? '#aaa' : scale(norm);
        return { color: shade(c, -20), weight:1, fillColor:c, fillOpacity:0.6 };
      };
    }
  }

  function buildLegendCategorical(col, uniques, scale) {
    const div = document.getElementById('legend');
    let h = '<div style="font-weight:600;margin-bottom:6px;">' + escapeHtml(col) + '</div>';
    const max = Math.min(uniques.length, 60);
    for (let i = 0; i < max; i++) {
      const v = uniques[i];
      h += '<div class="legend-row"><div class="swatch" style="background:' +
           scale(v) + '"></div><div class="legend-label">' + escapeHtml(v) + '</div></div>';
    }
    if (uniques.length > max) {
      h += '<div style="color:var(--muted);font-size:11px;">' +
           '+' + (uniques.length - max) + ' ערכים נוספים</div>';
    }
    div.innerHTML = h;
  }

  function buildLegendNumeric(col, min, max, breaks, palette) {
    const div = document.getElementById('legend');
    let h = '<div style="font-weight:600;margin-bottom:6px;">' + escapeHtml(col) + '</div>';
    const edges = [min, ...breaks, max];
    for (let i = 0; i < palette.length; i++) {
      const lo = edges[i], hi = edges[i+1];
      h += '<div class="legend-row"><div class="swatch" style="background:' + palette[i] +
           '"></div><div class="legend-label">' + fmt(lo) + ' – ' + fmt(hi) + '</div></div>';
    }
    div.innerHTML = h;
  }

  function fmt(v) {
    if (typeof v !== 'number') return String(v);
    if (Number.isInteger(v)) return v.toString();
    return v.toFixed(2);
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, m => (
      { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[m]
    ));
  }

  // -------- GeoJSON layer --------
  let layer;

  function buildPopup(props) {
    let rows = '';
    Object.keys(props).forEach(k => {
      const v = props[k];
      if (v === null || v === undefined || v === '') return;
      rows += '<tr><th>' + escapeHtml(k) + '</th><td>' + escapeHtml(v) + '</td></tr>';
    });
    return '<div class="popup-title">פרטי חלקה</div><table>' + rows + '</table>';
  }

  function passesFilters(feature) {
    for (const col in state.filters) {
      const allowed = state.filters[col];
      if (!allowed || allowed.size === 0) continue;
      const v = feature.properties[col];
      if (v === null || v === undefined || v === '') return false;
      if (COL_META[col].isTag) {
        // feature passes if ANY of its tags is selected
        const tags = splitTags(v);
        if (!tags.some(t => allowed.has(t))) return false;
      } else {
        if (!allowed.has(normalizeValue(v))) return false;
      }
    }
    return true;
  }

  function rebuildLayer() {
    if (layer) map.removeLayer(layer);
    const styleFn = buildStyleFn();
    layer = L.geoJSON(GEOJSON, {
      filter: passesFilters,
      style: styleFn,
      onEachFeature: (feature, lyr) => {
        lyr.bindPopup(buildPopup(feature.properties), { maxWidth: 380 });
        lyr.on('mouseover', () => lyr.setStyle({ weight: 3, fillOpacity: 0.85 }));
        lyr.on('mouseout',  () => layer.resetStyle(lyr));
      }
    }).addTo(map);
    updateCounts();
  }

  function updateCounts() {
    const total = GEOJSON.features.length;
    let visible = 0;
    GEOJSON.features.forEach(f => { if (passesFilters(f)) visible++; });
    document.getElementById('totalCount').textContent = total;
    document.getElementById('visibleCount').textContent = visible;
  }

  function zoomToFiltered() {
    if (!layer) return;
    const b = layer.getBounds();
    if (b.isValid()) map.fitBounds(b, { padding: [25, 25] });
  }

  // -------- Symbology UI --------
  const colorBySelect = document.getElementById('colorBySelect');
  colorBySelect.innerHTML = '<option value="">— ללא —</option>' +
    ALL_COLS.map(c => {
      if (COL_META[c].numeric) {
        return '<option value="' + escapeHtml(c) + '">' + escapeHtml(c) + ' (מספרי)</option>';
      }
      if (COL_META[c].isTag) {
        // two options for tag columns
        return '<option value="__tag__:' + escapeHtml(c) + '">' + escapeHtml(c) + ' (תגית ראשונה)</option>' +
               '<option value="' + escapeHtml(c) + '">' + escapeHtml(c) + ' (מקורי)</option>';
      }
      return '<option value="' + escapeHtml(c) + '">' + escapeHtml(c) + '</option>';
    }).join('');
  colorBySelect.addEventListener('change', e => {
    state.colorBy = e.target.value;
    if (!state.colorBy) document.getElementById('legend').innerHTML =
      '<i style="color:var(--muted)">בחר שדה כדי לראות מקרא</i>';
    rebuildLayer();
  });
  document.getElementById('paletteSelect').addEventListener('change', e => {
    state.palette = e.target.value;
    if (state.colorBy) rebuildLayer();
  });

  // -------- Filters UI --------
  const filtersList = document.getElementById('filtersList');

  ALL_COLS.forEach(col => {
    const uniques = getUniques(col);
    const wrap = document.createElement('div');
    wrap.className = 'filter-col';
    wrap.dataset.col = col;

    wrap.innerHTML =
      '<div class="filter-col-header">' +
        '<span>' + escapeHtml(col) +
          (COL_META[col].isTag
            ? ' <span style="background:var(--accent-soft);color:var(--accent);' +
              'font-size:10px;padding:1px 6px;border-radius:8px;font-weight:600;">תגיות</span>'
            : '') +
          ' <span style="color:var(--muted);font-size:10px;">(' + uniques.length + ')</span>' +
        '</span>' +
        '<span></span>' +
      '</div>' +
      '<div class="filter-col-body">' +
        '<input type="text" class="filter-col-search" placeholder="חיפוש..." />' +
        '<div class="toolbar" style="margin:6px 0;">' +
          '<button data-act="check">סמן הכל</button>' +
          '<button data-act="uncheck">נקה</button>' +
        '</div>' +
        '<div class="filter-checks">' +
          uniques.slice(0, 500).map(v =>
            '<label><input type="checkbox" value="' + escapeHtml(v) + '">' + escapeHtml(v) + '</label>'
          ).join('') +
          (uniques.length > 500
            ? '<div style="color:var(--muted);font-size:11px;padding:4px 0;">' +
              'מציג 500 מתוך ' + uniques.length + ' — השתמש בחיפוש</div>'
            : '') +
        '</div>' +
      '</div>';

    wrap.querySelector('.filter-col-header').addEventListener('click', () => {
      wrap.classList.toggle('expanded');
    });

    const search = wrap.querySelector('.filter-col-search');
    search.addEventListener('input', e => {
      e.stopPropagation();
      const q = e.target.value.toLowerCase();
      wrap.querySelectorAll('.filter-checks label').forEach(l => {
        l.style.display = l.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
    search.addEventListener('click', e => e.stopPropagation());

    wrap.querySelectorAll('button[data-act]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const check = btn.dataset.act === 'check';
        wrap.querySelectorAll('.filter-checks input[type="checkbox"]').forEach(cb => {
          if (cb.parentNode.style.display !== 'none') cb.checked = check;
        });
      });
    });

    filtersList.appendChild(wrap);
  });

  function applyAllFilters() {
    state.filters = {};
    document.querySelectorAll('.filter-col').forEach(wrap => {
      const col = wrap.dataset.col;
      const checked = wrap.querySelectorAll('.filter-checks input[type="checkbox"]:checked');
      const headerSpan = wrap.querySelector('.filter-col-header > span:first-child');
      const oldBadge = headerSpan.querySelector('.filter-badge');
      if (oldBadge) oldBadge.remove();

      if (checked.length > 0) {
        state.filters[col] = new Set([...checked].map(cb => cb.value));
        headerSpan.insertAdjacentHTML('afterbegin',
          '<span class="filter-badge">' + checked.length + '</span>');
      }
    });
    rebuildLayer();
  }

  function clearAllFilters() {
    document.querySelectorAll('.filter-checks input[type="checkbox"]').forEach(cb => cb.checked = false);
    document.querySelectorAll('.filter-badge').forEach(b => b.remove());
    state.filters = {};
    rebuildLayer();
  }

  function togglePanel(id) {
    document.getElementById(id).classList.toggle('collapsed');
  }

  // -------- Init --------
  rebuildLayer();
  if (GEOJSON.features.length > 0) {
    map.fitBounds(BOUNDS, { padding: [20, 20] });
  } else {
    map.setView([31.5, 34.9], 8);
  }
</script>
</body>
</html>
"""

html_content = (HTML_TEMPLATE
                .replace('__GEOJSON_DATA__', geojson_str)
                .replace('__BOUNDS_DATA__', bounds_str))

HTML_OUT.write_text(html_content, encoding='utf-8')

print(f"✔ GPKG saved:  {GPKG_OUT.resolve()}")
print(f"✔ HTML saved:  {HTML_OUT.resolve()}")
print(f"  Features:    {len(merged_wgs84)}")
print(f"  Columns:     {len(properties_cols)}")