                        html.H2("Activity Suggestions"),
                        html.Div(id="suggestions", className="suggestions"),
                    ]
                ),
                html.Div(
                    children=[
                        html.H2("Local Attraction Ideas"),
                        html.Ul(id="attractions", className="attractions"),
                    ]
                ),
            ],
        ),
        html.Section(
            className="table-section",
            children=[
                html.H2("Supabase Weather Data"),
                dash_table.DataTable(
                    id="weather-table",
                    page_size=16,
                    sort_action="native",
                    style_table={"overflowX": "auto"},
                    style_cell={
                        "fontFamily": "Arial",
                        "fontSize": 13,
                        "padding": "8px",
                        "textAlign": "left",
                    },
                    style_header={"fontWeight": "bold", "backgroundColor": "#eef2f5"},
                ),
            ],
        ),
    ],
)


@app.callback(
    Output("status", "children"),
    Output("stored-count", "children"),
    Output("first-code", "children"),
    Output("rainiest-day", "children"),
    Output("temperature-chart", "figure"),
    Output("precipitation-chart", "figure"),
    Output("suggestions", "children"),
    Output("attractions", "children"),
    Output("weather-table", "data"),
    Output("weather-table", "columns"),
    Input("fetch-button", "n_clicks"),
    State("day-count", "value"),
)
def update_dashboard(n_clicks: int, day_count: int):
    """Fetch, save, read, and render weather data whenever the button is clicked."""
    # Clamp input defensively so the API always receives a valid forecast_days
    # value even if a browser or user sends something unexpected.
    days = max(1, min(int(day_count or 1), 16))

    try:
        if n_clicks:
            saved_df, status = fetch_save_and_read(days)
        else:
            saved_df = read_existing_weather(days)
            status = "Showing weather rows already saved in Supabase. Click Fetch forecast to refresh."
    except Exception as error:
        saved_df = pd.DataFrame()
        status = f"Could not connect, fetch, or load data: {error}"

    if saved_df.empty:
        empty_fig = build_empty_figure("No saved weather data yet")
        return status, "0", "N/A", "N/A", empty_fig, empty_fig, [], [], [], []

    # Add suggestions after reading from the database. The weather itself stays
    # normalized in Supabase, while suggestions remain app logic.
    saved_df["activity_suggestion"] = saved_df.apply(make_activity_suggestion, axis=1)

    temp_fig = px.line(
        saved_df,
        x="forecast_date",
        y=["temperature_max", "temperature_min"],
        markers=True,
        title="Daily Temperature Forecast",
        labels={"value": "Temperature (F)", "forecast_date": "Date", "variable": "Metric"},
    )
    temp_fig.update_layout(template="plotly_white", legend_title_text="")

    precip_fig = px.bar(
        saved_df,
        x="forecast_date",
        y="precipitation_probability_max",
        title="Precipitation Probability by Day",
        labels={"precipitation_probability_max": "Probability (%)", "forecast_date": "Date"},
    )
    precip_fig.update_layout(template="plotly_white")

    suggestion_cards = [
        html.Article(
            className="suggestion-card",
            children=[
                html.Strong(f"{row.forecast_date}: code {row.weather_code_id}"),
                html.Span(row.description or "No description available"),
                html.P(row.activity_suggestion),
            ],
        )
        for row in saved_df.itertuples()
    ]

    attraction_items = [html.Li(name) for name in pick_attractions(saved_df)]
    table_columns = [{"name": column, "id": column} for column in saved_df.columns]
    rainiest = saved_df.sort_values("precipitation_probability_max", ascending=False).iloc[0]

    return (
        status,
        str(len(saved_df)),
        f"{saved_df.iloc[0]['weather_code_id']} - {saved_df.iloc[0]['description']}",
        f"{rainiest['forecast_date']} ({rainiest['precipitation_probability_max']}%)",
        temp_fig,
        precip_fig,
        suggestion_cards,
        attraction_items,
        saved_df.to_dict("records"),
        table_columns,
    )


if __name__ == "__main__":
    app.run(debug=True)