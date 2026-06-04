"""
Louisville Weather Activity Recommender
---------------------------------------
Simple Dash app that reads the local weather and tourism files created by the
pipeline scripts, then recommends attractions based on the selected forecast day.

Run with:
    python app.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
from dash import Dash, Input, Output, dash_table, dcc, html


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

FORECAST_PATH = DATA_DIR / "daily_weather_forecast.csv"
TOURISM_PATH = DATA_DIR / "tourism.csv"
WEATHER_CODES_PATH = DATA_DIR / "weather_codes.xlsx"

CATEGORY_COLUMNS = [
    "water",
    "play_sweat_it_out",
    "small_kid_friendly_under_10",
    "big_kid_friendly_over_10",
    "culture",
    "nature",
]

CATEGORY_LABELS = {
    "water": "Water",
    "play_sweat_it_out": "Active",
    "small_kid_friendly_under_10": "Small kid friendly",
    "big_kid_friendly_over_10": "Big kid friendly",
    "culture": "Culture",
    "nature": "Nature",
}


def load_weather_codes() -> pd.DataFrame:
    """Return one row per WMO weather code with a readable description."""
    weather_codes_df = pd.read_excel(WEATHER_CODES_PATH)
    weather_codes_df["Code"] = weather_codes_df["Code"].astype(str).str.split(r"\s*,\s*")
    weather_codes_df = weather_codes_df.explode("Code")
    weather_codes_df["Code"] = pd.to_numeric(weather_codes_df["Code"], errors="coerce")
    weather_codes_df = weather_codes_df.dropna(subset=["Code"])
    weather_codes_df["Code"] = weather_codes_df["Code"].astype(int)

    return weather_codes_df.rename(
        columns={"Code": "weather_code", "Description": "description"}
    ).drop_duplicates(subset=["weather_code"])


def load_forecast() -> pd.DataFrame:
    """Read the pipeline output and enrich it with weather descriptions."""
    forecast_df = pd.read_csv(FORECAST_PATH, parse_dates=["date"])
    weather_codes_df = load_weather_codes()

    forecast_df = forecast_df.merge(weather_codes_df, on="weather_code", how="left")
    forecast_df["date_label"] = forecast_df["date"].dt.strftime("%a, %b %d")
    forecast_df["avg_temp_f"] = (
        forecast_df["temperature_2m_max"] + forecast_df["temperature_2m_min"]
    ) / 2

    return forecast_df.sort_values("date")


def load_tourism() -> pd.DataFrame:
    """Read attraction data and remove blank spreadsheet export columns."""
    tourism_df = pd.read_csv(TOURISM_PATH)
    blank_columns = [column for column in tourism_df.columns if "Unnamed" in column]
    tourism_df = tourism_df.drop(columns=blank_columns, errors="ignore")

    # Store flags as booleans so filtering is easier to read later.
    flag_columns = ["is_indoor", "adult_only", *CATEGORY_COLUMNS]
    for column in flag_columns:
        if column in tourism_df.columns:
            tourism_df[column] = pd.to_numeric(tourism_df[column], errors="coerce").fillna(0) == 1

    return tourism_df


def classify_weather(row: pd.Series) -> dict:
    """Translate a forecast row into recommendation-friendly weather labels."""
    avg_temp = row["avg_temp_f"]
    rain_chance = row["precipitation_probability_max"]
    uv_index = row["uv_index_max"]

    if rain_chance >= 60 or row["precipitation_sum"] > 0.25:
        activity_mode = "indoor"
        summary = "Rain is likely, so indoor attractions are the strongest match."
    elif avg_temp >= 85 or uv_index >= 8:
        activity_mode = "mixed"
        summary = "Hot or high-UV weather favors indoor, water, or shaded options."
    elif 50 <= avg_temp <= 84:
        activity_mode = "outdoor"
        summary = "Comfortable weather supports outdoor and active plans."
    else:
        activity_mode = "indoor"
        summary = "Cool weather makes indoor or low-exposure plans more comfortable."

    return {"activity_mode": activity_mode, "summary": summary}


def score_attractions(
    tourism_df: pd.DataFrame,
    forecast_row: pd.Series,
    selected_categories: list[str],
    include_adult_only: bool,
) -> pd.DataFrame:
    """Rank local attractions with simple weather and preference rules."""
    weather_class = classify_weather(forecast_row)
    ranked_df = tourism_df.copy()
    ranked_df["score"] = 0

    # Weather fit: rain and extreme temperatures push indoor attractions higher.
    if weather_class["activity_mode"] == "indoor":
        ranked_df.loc[ranked_df["is_indoor"], "score"] += 4
        ranked_df.loc[~ranked_df["is_indoor"], "score"] -= 1
    elif weather_class["activity_mode"] == "outdoor":
        ranked_df.loc[~ranked_df["is_indoor"], "score"] += 4
        ranked_df.loc[ranked_df["nature"] | ranked_df["play_sweat_it_out"], "score"] += 2
    else:
        ranked_df.loc[ranked_df["is_indoor"] | ranked_df["water"], "score"] += 3

    # User-selected categories add points but do not fully hide other good matches.
    for category in selected_categories:
        if category in ranked_df.columns:
            ranked_df.loc[ranked_df[category], "score"] += 3

    if not include_adult_only and "adult_only" in ranked_df.columns:
        ranked_df = ranked_df[~ranked_df["adult_only"]]

    return ranked_df.sort_values(["score", "attraction"], ascending=[False, True]).head(8)


def build_temperature_chart(forecast_df: pd.DataFrame):
    """Create a Plotly chart for daily high and low temperatures."""
    fig = px.line(
        forecast_df,
        x="date",
        y=["temperature_2m_max", "temperature_2m_min"],
        markers=True,
        labels={"value": "Temperature (F)", "date": "Date", "variable": "Metric"},
        title="16-Day Temperature Forecast",
    )
    fig.update_layout(template="plotly_white", legend_title_text="")
    return fig


def build_precipitation_chart(forecast_df: pd.DataFrame):
    """Create a Plotly chart for precipitation probability."""
    fig = px.bar(
        forecast_df,
        x="date",
        y="precipitation_probability_max",
        labels={"precipitation_probability_max": "Rain chance (%)", "date": "Date"},
        title="Precipitation Probability",
    )
    fig.update_layout(template="plotly_white")
    return fig


forecast_df = load_forecast()
tourism_df = load_tourism()

app = Dash(__name__)
server = app.server

app.layout = html.Main(
    className="page",
    children=[
        html.Header(
            className="header",
            children=[
                html.Div(
                    children=[
                        html.H1("Louisville Weather Activity Recommender"),
                        html.P(
                            "Pick a forecast day and activity interests to see weather-aware "
                            "recommendations from the local tourism dataset."
                        ),
                    ]
                ),
            ],
        ),
        html.Section(
            className="controls",
            children=[
                html.Label("Forecast day", htmlFor="date-select"),
                dcc.Dropdown(
                    id="date-select",
                    options=[
                        {"label": row.date_label, "value": row.date.strftime("%Y-%m-%d")}
                        for row in forecast_df.itertuples()
                    ],
                    value=forecast_df.iloc[0]["date"].strftime("%Y-%m-%d"),
                    clearable=False,
                ),
                html.Label("Categories", htmlFor="category-select"),
                dcc.Dropdown(
                    id="category-select",
                    options=[
                        {"label": label, "value": column}
                        for column, label in CATEGORY_LABELS.items()
                    ],
                    value=["culture", "nature"],
                    multi=True,
                ),
                html.Label(
                    children=[
                        html.Input(id="adult-only-toggle", type="checkbox", checked=False),
                        html.Span("Include adult-only attractions"),
                    ],
                    className="checkbox-label",
                ),
            ],
        ),
        html.Section(
            className="metrics",
            children=[
                html.Div([html.Span("Forecast"), html.Strong(id="weather-summary")]),
                html.Div([html.Span("Temperature"), html.Strong(id="temperature-summary")]),
                html.Div([html.Span("Recommendation"), html.Strong(id="activity-summary")]),
            ],
        ),
        html.Section(
            className="dashboard-grid",
            children=[
                html.Div(
                    className="chart-panel",
                    children=[dcc.Graph(id="temperature-chart", figure=build_temperature_chart(forecast_df))],
                ),
                html.Div(
                    className="chart-panel",
                    children=[
                        dcc.Graph(
                            id="precipitation-chart",
                            figure=build_precipitation_chart(forecast_df),
                        )
                    ],
                ),
            ],
        ),
        html.Section(
            className="recommendation-grid",
            children=[
                html.Div(
                    children=[
                        html.H2("Top Attraction Matches"),
                        html.Div(id="recommendation-cards", className="suggestions"),
                    ]
                ),
                html.Div(
                    children=[
                        html.H2("Selected Forecast Details"),
                        dash_table.DataTable(
                            id="forecast-table",
                            page_size=1,
                            style_table={"overflowX": "auto"},
                            style_cell={
                                "fontFamily": "Arial",
                                "fontSize": 13,
                                "padding": "8px",
                                "textAlign": "left",
                            },
                            style_header={"fontWeight": "bold", "backgroundColor": "#eef2f5"},
                        ),
                    ]
                ),
            ],
        ),
    ],
)


@app.callback(
    Output("weather-summary", "children"),
    Output("temperature-summary", "children"),
    Output("activity-summary", "children"),
    Output("recommendation-cards", "children"),
    Output("forecast-table", "data"),
    Output("forecast-table", "columns"),
    Input("date-select", "value"),
    Input("category-select", "value"),
    Input("adult-only-toggle", "checked"),
)
def update_recommendations(date_value: str, selected_categories: list[str], include_adult_only: bool):
    """Update forecast summaries and attraction recommendations from user inputs."""
    selected_categories = selected_categories or []
    selected_date = pd.to_datetime(date_value)
    forecast_row = forecast_df[forecast_df["date"] == selected_date].iloc[0]
    weather_class = classify_weather(forecast_row)
    ranked_attractions = score_attractions(
        tourism_df,
        forecast_row,
        selected_categories,
        bool(include_adult_only),
    )

    cards = []
    for row in ranked_attractions.itertuples():
        website = str(row.website).strip()
        website_href = website if website.startswith("http") else f"https://{website}"
        category_matches = [
            CATEGORY_LABELS[column]
            for column in selected_categories
            if column in ranked_attractions.columns and getattr(row, column)
        ]
        category_text = ", ".join(category_matches) if category_matches else "General match"

        cards.append(
            html.Article(
                className="suggestion-card",
                children=[
                    html.Strong(row.attraction),
                    html.Span("Indoor" if row.is_indoor else "Outdoor"),
                    html.P(category_text),
                    html.A("Website", href=website_href, target="_blank"),
                ],
            )
        )

    table_df = pd.DataFrame([forecast_row]).drop(columns=["date_label"], errors="ignore")
    table_df["date"] = table_df["date"].dt.strftime("%Y-%m-%d")

    return (
        f"{forecast_row['date_label']} - {forecast_row.get('description', 'No description')}",
        f"{forecast_row['temperature_2m_min']:.0f}F low / {forecast_row['temperature_2m_max']:.0f}F high",
        weather_class["summary"],
        cards,
        table_df.to_dict("records"),
        [{"name": column, "id": column} for column in table_df.columns],
    )


if __name__ == "__main__":
    app.run(debug=True)
