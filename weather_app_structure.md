# Weather Recommendation App Structure

This repo can stay simple for the first working version of the Louisville weather
recommendation app. The current structure already separates app assets, source
data, ETL scripts, and documentation.

## Recommended Layout

```text
pipeline_2026/
  app.py                         # Dash app and recommendation rules
  main.py                        # Basic weather API pipeline
  week3_main.py                  # Teaching ETL pipeline with validation and aggregation
  load_script.py                 # Supabase schema creation and normalized table load
  requirements.txt               # Python package list
  README.md                      # Project overview and run instructions
  weather_app_structure.md       # App structure and change proposal
  schema_documentation.md        # Database table documentation
  weather_app_proposal.md        # Original project proposal
  assets/
    weather_dashboard.css        # Dash styling loaded automatically
    *.svg                        # Weather icons available for future UI work
  data/
    daily_weather_forecast.csv   # Forecast output used by the Dash app
    tourism.csv                  # Attraction data used for recommendations
    weather_codes.xlsx           # Weather-code lookup table
```

## Current App Changes

- Replace the incomplete `app.py` with a runnable Dash app.
- Read local files from `data/` so the app can run before Supabase is required.
- Reuse the weather-code lookup logic from `main.py` and `week3_main.py`.
- Reuse the tourism category columns from `load_script.py`.
- Add simple weather rules for indoor, outdoor, mixed, and category-based activity matches.
- Add Plotly temperature and precipitation charts.
- Keep custom CSS in `assets/weather_dashboard.css`, which Dash loads automatically.

## Future Optional Changes

- Move recommendation rules into `recommendations.py` once they become more complex.
- Add `database.py` only when the app needs to read directly from Supabase.
- Add tests for `classify_weather()` and `score_attractions()` after rules stabilize.
- Add icon support from the existing SVG files after the basic dashboard is approved.
