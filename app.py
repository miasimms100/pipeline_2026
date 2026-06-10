"""
Louisville Weather Activity Recommender
---------------------------------------
Simple Dash app that reads the local weather and tourism files created by the
pipeline scripts, then recommends attractions based on the selected forecast day.

Run with:
    python app.py
"""

from pathlib import Path
import os

import pandas as pd
from dash import ALL, Dash, Input, Output, State, dash_table, dcc, html

from load_script import main as refresh_database


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

FORECAST_PATH = DATA_DIR / "daily_weather_forecast.csv"
TOURISM_PATH = DATA_DIR / "tourism.csv"
WEATHER_CODES_PATH = DATA_DIR / "weather_codes_v2.xlsx"

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
    """Return one row per WMO weather code with a readable description.

    Supports the v2 workbook which contains explicit columns:
    - weather_code, weather_category, weather_description, severity_level, assets
    Falls back to legacy `Code`/`Description` format if v2 columns aren't present.
    """
    weather_codes_df = pd.read_excel(WEATHER_CODES_PATH)

    if "weather_code" in weather_codes_df.columns:
        # Normalize asset column name if provided as `asset`.
        if "asset" in weather_codes_df.columns and "assets" not in weather_codes_df.columns:
            weather_codes_df = weather_codes_df.rename(columns={"asset": "assets"})

        # Ensure numeric weather_code and drop invalid rows
        weather_codes_df["weather_code"] = pd.to_numeric(weather_codes_df["weather_code"], errors="coerce")
        weather_codes_df = weather_codes_df.dropna(subset=["weather_code"]) 
        weather_codes_df["weather_code"] = weather_codes_df["weather_code"].astype(int)

        # Rename description column for backward compatibility
        if "weather_description" in weather_codes_df.columns:
            weather_codes_df = weather_codes_df.rename(columns={"weather_description": "description"})

        cols = ["weather_code", "weather_category", "description", "severity_level"]
        if "assets" in weather_codes_df.columns:
            cols.append("assets")

        return weather_codes_df[cols].drop_duplicates(subset=["weather_code"])

    # Legacy fallback
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


def build_date_options(forecast_df: pd.DataFrame) -> list[dict]:
    """Return the most recent forecast dates as dropdown options."""
    latest_forecast = forecast_df.sort_values("date").tail(15)
    return [
        {
            "label": f"Day {idx + 1} — {row.date_label}",
            "value": row.date.strftime("%Y-%m-%d"),
        }
        for idx, row in enumerate(latest_forecast.itertuples())
    ]


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
                html.Label("Forecast range", htmlFor="date-select"),
                dcc.Dropdown(
                    id="date-select",
                    options=build_date_options(forecast_df),
                    value=[build_date_options(forecast_df)[0]["value"]],
                    multi=True,
                    clearable=False,
                ),
                dcc.Checklist(
                    id="adult-only-toggle",
                    options=[
                        {"label": "Include adult-only attractions", "value": "include"}
                    ],
                    value=[],
                    className="checkbox-label",
                ),
                html.Button(
                    "Refresh Weather Data",
                    id="refresh-db-button",
                    className="refresh-button",
                ),
                html.Div(
                    id="refresh-status-output",
                    style={"marginTop": "10px", "display": "none"},
                ),
            ],
        ),
        html.Section(
            className="metrics",
            children=[
                html.Div([html.Span("Temperature"), html.Strong(id="temperature-summary")]),
            ],
        ),
        html.Section(
            className="forecast-days-grid",
            id="forecast-day-panels",
            children=[
                html.Div(
                    "Select one or more forecast days from the range above to view the daily forecast summary, temperature range, and the top 3 activity recommendations.",
                    className="forecast-placeholder",
                )
            ],
        ),
    ],
)


@app.callback(
    Output("refresh-status-output", "children"),
    Output("refresh-status-output", "style"),
    Output("date-select", "options"),
    Output("date-select", "value"),
    Input("refresh-db-button", "n_clicks"),
    prevent_initial_call=True,
)
def update_database(n_clicks):
    """Trigger database refresh with latest weather data from Open-Meteo and reload the UI options."""
    global forecast_df
    if not n_clicks:
        options = build_date_options(forecast_df)
        return "", {"display": "none"}, options, [options[0]["value"]]
    
    try:
        refresh_database()
        # Reload forecast data into memory
        forecast_df = load_forecast()
        latest_options = build_date_options(forecast_df)
        latest_value = [latest_options[0]["value"]] if latest_options else []
        message = "✓ Weather data updated successfully!"
        style = {
            "marginTop": "10px",
            "padding": "12px",
            "backgroundColor": "#d4edda",
            "color": "#155724",
            "borderRadius": "4px",
            "border": "1px solid #c3e6cb",
        }
        return message, style, latest_options, latest_value
    except Exception as e:
        message = f"✗ Error updating weather data: {str(e)}"
        style = {
            "marginTop": "10px",
            "padding": "12px",
            "backgroundColor": "#f8d7da",
            "color": "#721c24",
            "borderRadius": "4px",
            "border": "1px solid #f5c6cb",
        }
        return message, style, build_date_options(forecast_df), [build_date_options(forecast_df)[-1]["value"]]


@app.callback(
    Output("temperature-summary", "children"),
    Output("forecast-day-panels", "children"),
    Input("date-select", "value"),
    Input("adult-only-toggle", "value"),
    Input({"type": "day-category-select", "date": ALL}, "value"),
    State({"type": "day-category-select", "date": ALL}, "id"),
    prevent_initial_call=False,
)
def update_recommendations(
    selected_dates: list[str],
    adult_only_values: list[str],
    day_category_values: list[list[str]],
    day_category_ids: list[dict],
):
    """Update forecast summaries and daily activity recommendations from user inputs."""
    selected_dates = selected_dates or []
    adult_only_values = adult_only_values or []
    if isinstance(selected_dates, str):
        selected_dates = [selected_dates]

    categories_by_day = {}
    for item, value in zip(day_category_ids or [], day_category_values or []):
        date_key = None
        if isinstance(item, dict) and "date" in item:
            date_key = item["date"]
        elif isinstance(item, dict) and "id" in item and isinstance(item["id"], dict):
            date_key = item["id"].get("date")

        if date_key is not None:
            categories_by_day[date_key] = value or []

    selected_dates = selected_dates[:15]
    if not selected_dates:
        return (
            "No forecast selected",
            [
                html.Div(
                    "Please select one or more days from the Forecast range dropdown.",
                    className="empty-state",
                )
            ],
        )

    day_panels = []
    selected_labels = []
    for date_value in selected_dates:
        selected_date = pd.to_datetime(date_value)
        forecast_row = forecast_df[forecast_df["date"] == selected_date]
        if forecast_row.empty:
            continue
        forecast_row = forecast_row.iloc[0]
        selected_labels.append(forecast_row["date_label"])
        selected_categories = categories_by_day.get(date_value, [])
        weather_class = classify_weather(forecast_row)
        ranked_attractions = score_attractions(
            tourism_df,
            forecast_row,
            selected_categories,
            "include" in adult_only_values,
        ).head(3)

        activity_cards = []
        for row in ranked_attractions.itertuples():
            website = str(row.website).strip()
            website_href = website if website.startswith("http") else f"https://{website}" if website else "#"
            category_matches = [
                CATEGORY_LABELS[column]
                for column in selected_categories
                if column in ranked_attractions.columns and getattr(row, column)
            ]
            category_text = ", ".join(category_matches) if category_matches else "General match"

            activity_cards.append(
                html.Article(
                    className="day-activity-card",
                    children=[
                        html.Strong(row.attraction),
                        html.Span("Indoor" if row.is_indoor else "Outdoor"),
                        html.P(category_text),
                        html.A("Visit website", href=website_href, target="_blank"),
                    ],
                )
            )

        # Build header with optional weather asset icon
        header_children = []
        asset_file = forecast_row.get("assets") or forecast_row.get("asset")
        asset_path = None
        if asset_file and isinstance(asset_file, str) and asset_file.strip():
            candidate = Path(__file__).resolve().parent / "assets" / asset_file
            if candidate.exists():
                asset_path = asset_file
        if not asset_path:
            asset_path = "default-weather-icon.svg"

        header_children.append(html.Img(src=f"/assets/{asset_path}", className="weather-icon", alt="Weather icon"))
        header_children.extend([
            html.H2(forecast_row["date_label"]),
            html.P(forecast_row.get("description", "No description")),
        ])

        day_panels.append(
            html.Article(
                className="forecast-day-panel",
                children=[
                    html.Div(
                        className="forecast-day-header",
                        children=header_children,
                    ),
                    html.Div(
                        className="day-filter-row",
                        children=[
                            html.Label("Event types"),
                            dcc.Dropdown(
                                id={"type": "day-category-select", "date": date_value},
                                options=[
                                    {"label": label, "value": key}
                                    for key, label in CATEGORY_LABELS.items()
                                ],
                                value=categories_by_day.get(date_value, []),
                                multi=True,
                                placeholder="Choose event types",
                                clearable=False,
                            ),
                        ],
                    ),
                    html.Div(
                        className="day-summary-cards",
                        children=[
                            html.Div(
                                className="day-summary-card",
                                children=[
                                    html.Span("Forecast"),
                                    html.Strong(forecast_row.get("description", "No description")),
                                ],
                            ),
                            html.Div(
                                className="day-summary-card",
                                children=[
                                    html.Span("Temperature"),
                                    html.Strong(
                                        f"{forecast_row['temperature_2m_min']:.0f}F low / {forecast_row['temperature_2m_max']:.0f}F high"
                                    ),
                                ],
                            ),
                            html.Div(
                                className="day-summary-card",
                                children=[
                                    html.Span("Recommendation"),
                                    html.Strong(weather_class["activity_mode"].capitalize()),
                                    html.Small(
                                        weather_class["summary"],
                                        className="recommendation-detail",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="day-activities-group",
                        children=[
                            html.H3("Top 3 activities"),
                            html.Div(className="day-activities", children=activity_cards),
                        ],
                    ),
                ],
            )
        )

    range_text = (
        f"{selected_labels[0]} through {selected_labels[-1]}"
        if len(selected_labels) > 1
        else selected_labels[0]
    )

    return (
        range_text,
        day_panels,
    )


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", "8050")))
