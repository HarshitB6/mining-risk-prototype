import dash
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
import random
import folium
from folium.features import DivIcon
import plotly.express as px
import numpy as np
import os

# ----------------------
# CONFIG
# ----------------------
DEM_PATH = "data/dem_file.tif"  # put your DEM file here
UPLOAD_TMP_DIR = "tmp"
os.makedirs(UPLOAD_TMP_DIR, exist_ok=True)

# Preload DEM overlay if exists
dem_overlay_path = None
dem_bounds = None
try:
    import rasterio
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm

    with rasterio.open(DEM_PATH) as src:
        dem = src.read(1).astype(float)
        bounds = src.bounds
        dem_bounds = [[bounds.bottom, bounds.left], [bounds.top, bounds.right]]

        norm = (dem - np.nanmin(dem)) / (np.nanmax(dem) - np.nanmin(dem) + 1e-9)
        rgba = cm.terrain(norm)
        dem_overlay_path = os.path.join(UPLOAD_TMP_DIR, "dem_overlay.png")
        plt.imsave(dem_overlay_path, rgba)
    print("DEM preloaded successfully.")
except Exception as e:
    print("DEM not loaded:", e)
    dem_overlay_path = None

# ----------------------
# Helpers
# ----------------------
def risk_color(level: str) -> str:
    return {"Low": "#4CAF50", "Medium": "#F4C430", "High": "#E53935"}.get(level, "#4CAF50")

def risk_icon(level: str) -> str:
    return {"Low": "🟢", "Medium": "🟡", "High": "🔴"}.get(level, "🟢")

def compute_score(rain, vib, blast, slope, deterministic=False):
    vib_from_blast = blast * (2.0 if deterministic else random.uniform(1.5, 3.0))
    total_vib = vib + vib_from_blast
    noise = 0 if deterministic else random.uniform(-5, 5)
    score = slope / 2 + rain * 0.4 + total_vib * 5 + blast * 3 + noise
    if score < 40:
        return "Low", score
    elif score < 70:
        return "Medium", score
    else:
        return "High", score

# ----------------------
# Data (standardized lat, lon order)
# ----------------------
benches = [
    {"id": "Bench 1", "slope": 35, "coords": [[23.1792, 72.6508],[23.1792, 72.6524],[23.1779, 72.6529],[23.1768, 72.6518],[23.1775, 72.6506],[23.1792, 72.6508]]},
    {"id": "Bench 2", "slope": 50, "coords": [[23.1735, 72.6448],[23.1736, 72.6468],[23.1724, 72.6473],[23.1715, 72.6462],[23.1719, 72.6450],[23.1735, 72.6448]]},
    {"id": "Bench 3", "slope": 45, "coords": [[23.1710, 72.6504],[23.1708, 72.6517],[23.1696, 72.6521],[23.1688, 72.6510],[23.1694, 72.6499],[23.1710, 72.6504]]},
    {"id": "Bench 4", "slope": 60, "coords": [[23.1670, 72.6420],[23.1672, 72.6445],[23.1653, 72.6450],[23.1643, 72.6433],[23.1651, 72.6416],[23.1670, 72.6420]]},
]

groups = [
    {"benches": ["Bench 1","Bench 2"]},
    {"benches": ["Bench 3","Bench 4"]}
]

rivers = [
    [[23.1785, 72.6390],[23.1760, 72.6450],[23.1738, 72.6510],[23.1745, 72.6570]],
    [[23.1722, 72.6460],[23.1718, 72.6510],[23.1728, 72.6550]],
]

haul_road = [[23.1725, 72.6496],[23.1723, 72.6512]]
truck_xy = [23.1723, 72.6512]

history = []

DRONE_IMG = "https://via.placeholder.com/400x300.png?text=Drone+Image"

# ----------------------
# Dash App
# ----------------------
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

controls_card = dbc.Card([
    dbc.CardHeader(html.H5("Controls")),
    dbc.CardBody([
        dbc.RadioItems(
            id="mode",
            options=[{"label":"Manual", "value":"Manual"}, {"label":"Auto", "value":"Auto"}],
            value="Manual",
            inline=True
        ),
        html.Div(id="manual-controls", children=[
            html.Br(),
            html.H6("Group 1 Inputs"),
            dbc.Label("Rainfall (mm)"),
            dcc.Slider(0, 200, 1, value=10, id="rain1"),
            dbc.Label("Vibration (mm/s)"),
            dcc.Slider(0, 10, 0.1, value=1, id="vib1"),
            dbc.Label("Blast activity (events/day)"),
            dcc.Slider(0, 5, 1, value=0, id="blast1"),
            html.Br(),
            html.H6("Group 2 Inputs"),
            dbc.Label("Rainfall (mm)"),
            dcc.Slider(0, 200, 1, value=10, id="rain2"),
            dbc.Label("Vibration (mm/s)"),
            dcc.Slider(0, 10, 0.1, value=1, id="vib2"),
            dbc.Label("Blast activity (events/day)"),
            dcc.Slider(0, 5, 1, value=0, id="blast2"),
        ]),
        html.Div(id="auto-controls", children=[
            html.Br(),
            dbc.Label("Auto update interval (sec)"),
            dcc.Slider(2, 20, 1, value=5, id="interval"),
        ], style={"display":"none"}),

        html.Br(),
        dbc.Checkbox(id="toggle-dem", value=False, label="Show DEM Overlay", disabled=dem_overlay_path is None),
        html.Br(),
        dbc.Button("Export CSV", id="export-btn", color="primary", className="mt-2"),
        dcc.Download(id="download")
    ])
])

tabs = dbc.Tabs([
    dbc.Tab(label="Charts & Table", tab_id="tab1", children=[
        html.Br(),
        dcc.Graph(id="env1-chart"),
        dcc.Graph(id="env2-chart"),
        dcc.Graph(id="bench-chart"),
        dash_table.DataTable(id="risk-table", style_table={'overflowX':'auto'}, style_cell={'textAlign':'center'}),
        html.Br(),
        html.H5("Drone Imagery"),
        html.Img(src=DRONE_IMG, style={"width":"100%","maxWidth":"400px"})
    ]),
    dbc.Tab(label="Map", tab_id="tab2", children=[
        html.Br(),
        html.Iframe(id="map", srcDoc="", width="100%", height="600")
    ])
])

app.layout = dbc.Container([
    html.H2("GeoSentinal", style={'textAlign': 'center', 'marginBottom':50}),
    dbc.Row([
        dbc.Col(controls_card, width=3),
        dbc.Col(tabs, width=9)
    ]),
    dcc.Interval(id="auto-update", interval=5000, n_intervals=0, disabled=True)
], fluid=True)

# ----------------------
# Callbacks
# ----------------------
@app.callback(
    Output("manual-controls", "style"),
    Output("auto-controls", "style"),
    Output("auto-update", "disabled"),
    Input("mode", "value")
)
def toggle_mode(mode):
    if mode=="Manual":
        return {"display":"block"}, {"display":"none"}, True
    else:
        return {"display":"none"}, {"display":"block"}, False

@app.callback(
    Output("auto-update", "interval"),
    Input("interval", "value")
)
def update_interval(value):
    return value * 1000

@app.callback(
    Output("env1-chart", "figure"),
    Output("env2-chart", "figure"),
    Output("bench-chart", "figure"),
    Output("risk-table", "data"),
    Output("risk-table", "columns"),
    Output("map", "srcDoc"),
    Input("rain1", "value"),
    Input("vib1", "value"),
    Input("blast1", "value"),
    Input("rain2", "value"),
    Input("vib2", "value"),
    Input("blast2", "value"),
    Input("auto-update", "n_intervals"),
    Input("toggle-dem", "value"),
    State("mode", "value")
)
def update_dashboard(rain1, vib1, blast1, rain2, vib2, blast2, n_intervals, show_dem, mode):
    global history
    deterministic = mode == "Manual"

    if mode=="Auto":
        rain1, vib1, blast1 = random.randint(0,200), round(random.uniform(0,10),1), random.randint(0,5)
        rain2, vib2, blast2 = random.randint(0,200), round(random.uniform(0,10),1), random.randint(0,5)

    results = []
    group_inputs = [(groups[0], rain1, vib1, blast1), (groups[1], rain2, vib2, blast2)]
    for g, gr, gv, gb in group_inputs:
        for bench_id in g["benches"]:
            bench = next(b for b in benches if b["id"]==bench_id)
            risk, score = compute_score(gr, gv, gb, bench["slope"], deterministic)
            results.append({"Bench": bench_id, "Slope": bench["slope"], "Rainfall": gr,
                            "Vibration": gv, "Blast": gb, "Score": round(score,1), "Risk": risk})

    history.append({"rain1": rain1, "vib1": vib1, "blast1": blast1,
                    "rain2": rain2, "vib2": vib2, "blast2": blast2,
                    **{r["Bench"]: r["Score"] for r in results}})
    if len(history) > 200:
        history.pop(0)

    hist_df = pd.DataFrame(history)
    env1_df = hist_df[["rain1","vib1","blast1"]].rename(columns={"rain1":"Rain","vib1":"Vibration","blast1":"Blast"})
    env1_fig = px.line(env1_df, y=["Rain","Vibration","Blast"], title="Environmental Inputs - Group 1", markers=True)

    env2_df = hist_df[["rain2","vib2","blast2"]].rename(columns={"rain2":"Rain","vib2":"Vibration","blast2":"Blast"})
    env2_fig = px.line(env2_df, y=["Rain","Vibration","Blast"], title="Environmental Inputs - Group 2", markers=True)

    bench_fig = px.line(hist_df, y=[b["id"] for b in benches], title="Bench Risk Trend", markers=True)

    df = pd.DataFrame(results)
    df["Status"] = df["Risk"].map(risk_icon)
    columns=[{"name":i,"id":i} for i in df.columns]
    data=df.to_dict("records")

    # Map
    m = folium.Map(location=[23.172, 72.649], zoom_start=14, tiles="CartoDB Positron", control_scale=True)
    for line in rivers:
        folium.PolyLine(locations=line, color="#1E88E5", weight=3, opacity=0.8).add_to(m)
    folium.PolyLine(locations=haul_road, color="#666", weight=5, opacity=0.9).add_to(m)
    folium.Marker(location=truck_xy, icon=folium.Icon(color="red",icon="truck",prefix="fa"), tooltip="Hauler").add_to(m)

    for r in results:
        bench = next(b for b in benches if b["id"]==r["Bench"])
        lats = [pt[0] for pt in bench["coords"]]
        lons = [pt[1] for pt in bench["coords"]]
        center = [sum(lats)/len(lats), sum(lons)/len(lons)]
        for layer in range(3):
            risk, score = compute_score(r["Rainfall"], r["Vibration"], r["Blast"], bench["slope"] + layer*2, deterministic)
            folium.Circle(
                location=center,
                radius=30*(layer+1),
                color=risk_color(risk),
                fill=True,
                fill_opacity=0.5,
                tooltip=f"{bench['id']} - Layer {layer+1}: {risk} ({score:.1f})"
            ).add_to(m)
        folium.Marker(location=center, icon=DivIcon(html=f"<b>{bench['id']}</b>")).add_to(m)

    if show_dem and dem_overlay_path:
        folium.raster_layers.ImageOverlay(
            name="DEM Overlay",
            image=dem_overlay_path,
            bounds=dem_bounds,
            opacity=0.6,
            interactive=True,
            cross_origin=False,
            zindex=1,
        ).add_to(m)
        folium.LayerControl().add_to(m)

    return env1_fig, env2_fig, bench_fig, data, columns, m._repr_html_()

@app.callback(
    Output("download", "data"),
    Input("export-btn", "n_clicks"),
    prevent_initial_call=True
)
def export_csv(n):
    df = pd.DataFrame(history)
    return dcc.send_data_frame(df.to_csv, "risk_report.csv")

if __name__ == "__main__":
    app.run(debug=False)
