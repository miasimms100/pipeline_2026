"""
Week 3 teaching ETL pipeline: Transformation & Data Quality

This file expands the original weather pipeline with explicit examples of:

- Cleaning and normalization
- Aggregation layers and derived metrics
- Incremental loading strategies
- Data validation checks
- Logging and error handling

The goal is to give students a clean, reproducible, documented example they can
use as a model when producing their own data engineering code.
"""

from pathlib import Path
import logging

import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Logging and error handling example:
# A reliable pipeline should leave a useful execution trail. Logging is better
# than print statements because logs can be filtered, timestamped, and captured
# by schedulers or orchestration tools.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reproducibility example:
# Keep source URLs, request parameters, and file locations in one predictable
# configuration area so a future user can rerun the same pipeline.
# ---------------------------------------------------------------------------
BASE_URL = "https://api.open-meteo.com/v1/forecast"
DATA_DIR = Path("data")
LOOKUP_PATH = DATA_DIR / "weather_codes.xlsx"
DAILY_OUTPUT_PATH = DATA_DIR / "daily_weather_forecast.csv"
WEEKLY_OUTPUT_PATH = DATA_DIR / "weekly_weather_summary.csv"

PARAMS = {
    "latitude": 38.2542,
    "longitude": -85.7594,
    "daily": [
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "sunrise",
        "sunset",
        "precipitation_sum",
        "precipitation_hours",
        "precipitation_probability_max",
        "daylight_duration",
        "sunshine_duration",
        "uv_index_max",
    ],
    "timezone": "America/New_York",
    "forecast_days": 16,
    "timeformat": "unixtime",
    "wind_speed_unit": "mph",
    "temperature_unit": "fahrenheit",
    "precipitation_unit": "inch",
}


def extract_weather_forecast() -> dict:
    """Extract raw weather data from the API."""
    logger.info("Extracting weather forecast from Open-Meteo API")

    try:
        response = requests.get(BASE_URL, params=PARAMS, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        # Error handling example:
        # Raise a clear failure with context instead of silently producing a
        # partial or empty dataset.
        logger.exception("Weather API request failed")
        raise RuntimeError("Unable to extract weather forecast data") from error


def validate_raw_response(raw_response: dict) -> None:
    """Validate that the API response contains the minimum structure we need."""
    # Data validation check example:
    # Validate required source fields before transformation. This catches source
    # contract changes early and gives students a clear failure point.
    if not isinstance(raw_response, dict):
        raise ValueError("API response must be a dictionary")

    daily_data = raw_response.get("daily")
    if not daily_data:
        raise ValueError(f"No daily data returned. Raw response: {raw_response}")

    required_fields = {"time", "weather_code", "temperature_2m_max", "temperature_2m_min"}
    missing_fields = required_fields.difference(daily_data)
    if missing_fields:
        raise ValueError(f"Daily forecast is missing required fields: {sorted(missing_fields)}")

    logger.info("Raw response validation passed")


def clean_and_normalize_forecast(raw_response: dict) -> pd.DataFrame:
    """Clean, normalize, and standardize the raw API response."""
    daily_df = pd.DataFrame(raw_response["daily"])

    # Cleaning and normalization example:
    # Convert Unix timestamps into a real date column, use a stable date index,
    # and remove the raw timestamp column once it has served its purpose.
    daily_df["date"] = pd.to_datetime(daily_df["time"], unit="s").dt.date
    daily_df = daily_df.drop(columns=["time"]).set_index("date")

    # Cleaning and normalization example:
    # Convert sunrise and sunset from Unix seconds into readable local time.
    for column in ["sunrise", "sunset"]:
        if column in daily_df.columns:
            daily_df[column] = pd.to_datetime(daily_df[column], unit="s").dt.strftime("%H:%M")

    # Cleaning and normalization example:
    # Standardize column names. A predictable naming convention makes downstream
    # joins, BI tools, and tests easier to maintain.
    daily_df = daily_df.rename(
        columns={
            "temperature_2m_max": "temp_max_f",
            "temperature_2m_min": "temp_min_f",
            "precipitation_sum": "precipitation_inches",
            "precipitation_probability_max": "precipitation_probability_pct",
            "daylight_duration": "daylight_seconds",
            "sunshine_duration": "sunshine_seconds",
        }
    )

    # Cleaning example:
    # Enforce numeric types after extraction. errors="coerce" turns bad values
    # into NaN so validation can catch them instead of letting strings leak into
    # analytical calculations.
    numeric_columns = [
        "weather_code",
        "temp_max_f",
        "temp_min_f",
        "precipitation_inches",
        "precipitation_hours",
        "precipitation_probability_pct",
        "daylight_seconds",
        "sunshine_seconds",
        "uv_index_max",
    ]
    for column in numeric_columns:
        if column in daily_df.columns:
            daily_df[column] = pd.to_numeric(daily_df[column], errors="coerce")

    # Derived metrics example:
    # Create fields that are easier for analysts to consume than raw source
    # values. These are deterministic transformations, so they belong in ETL.
    daily_df["temp_range_f"] = daily_df["temp_max_f"] - daily_df["temp_min_f"]
    daily_df["avg_temp_f"] = (daily_df["temp_max_f"] + daily_df["temp_min_f"]) / 2
    daily_df["daylight_hours"] = daily_df["daylight_seconds"] / 3600
    daily_df["sunshine_hours"] = daily_df["sunshine_seconds"] / 3600
    daily_df["sunshine_pct_of_daylight"] = (
        daily_df["sunshine_seconds"] / daily_df["daylight_seconds"] * 100
    ).round(1)
    daily_df["has_precipitation"] = daily_df["precipitation_inches"].fillna(0) > 0

    logger.info("Cleaned and normalized %s forecast rows", len(daily_df))
    return daily_df


def load_weather_code_lookup(path: Path) -> pd.DataFrame:
    """Load and normalize the weather-code lookup table."""
    logger.info("Loading weather-code lookup from %s", path)

    try:
        lookup_df = pd.read_excel(path)
    except FileNotFoundError as error:
        logger.exception("Weather-code lookup file was not found")
        raise FileNotFoundError(f"Missing lookup file: {path}") from error

    # Data validation check example:
    # A lookup table must contain the keys and descriptive attributes required
    # for a trustworthy enrichment join.
    required_columns = {"Code", "Description"}
    missing_columns = required_columns.difference(lookup_df.columns)
    if missing_columns:
        raise ValueError(f"Weather-code lookup is missing columns: {sorted(missing_columns)}")

    # Cleaning and normalization example:
    # The source lookup can store multiple comma-separated codes in one row.
    # Split and explode them so there is exactly one weather code per row.
    lookup_df["Code"] = lookup_df["Code"].astype(str).str.split(r"\s*,\s*")
    lookup_df = lookup_df.explode("Code")
    lookup_df["Code"] = pd.to_numeric(lookup_df["Code"], errors="coerce")
    lookup_df = lookup_df.dropna(subset=["Code"])
    lookup_df["Code"] = lookup_df["Code"].astype(int)

    # Data quality example:
    # Drop duplicate lookup keys so the enrichment join remains many-to-one.
    lookup_df = lookup_df.drop_duplicates(subset=["Code"])

    logger.info("Loaded %s normalized weather-code lookup rows", len(lookup_df))
    return lookup_df


def enrich_with_weather_descriptions(daily_df: pd.DataFrame, lookup_df: pd.DataFrame) -> pd.DataFrame:
    """Join normalized forecast data to normalized weather-code descriptions."""
    # Transformation example:
    # Enrichment joins convert coded source data into business-readable data.
    enriched_df = (
        daily_df.reset_index()
        .merge(lookup_df, left_on="weather_code", right_on="Code", how="left")
        .drop(columns=["Code"], errors="ignore")
        .set_index("date")
    )

    # Data validation check example:
    # After a lookup join, check whether any source codes failed to match.
    missing_descriptions = enriched_df["Description"].isna().sum()
    if missing_descriptions:
        logger.warning("%s forecast rows did not match a weather-code description", missing_descriptions)

    return enriched_df


def validate_clean_forecast(daily_df: pd.DataFrame) -> None:
    """Run data quality checks after transformation and enrichment."""
    required_columns = {
        "weather_code",
        "temp_max_f",
        "temp_min_f",
        "avg_temp_f",
        "temp_range_f",
        "precipitation_inches",
        "Description",
    }
    missing_columns = required_columns.difference(daily_df.columns)
    if missing_columns:
        raise ValueError(f"Clean forecast is missing required columns: {sorted(missing_columns)}")

    # Data validation check example:
    # Required analytical fields should not be null after cleaning.
    required_non_null = ["weather_code", "temp_max_f", "temp_min_f", "avg_temp_f"]
    null_counts = daily_df[required_non_null].isna().sum()
    if null_counts.any():
        raise ValueError(f"Null values found in required fields: {null_counts.to_dict()}")

    # Data validation check example:
    # Check business rules, not only data types. A max temperature lower than a
    # min temperature indicates a transformation or source-quality problem.
    invalid_temperature_rows = daily_df[daily_df["temp_max_f"] < daily_df["temp_min_f"]]
    if not invalid_temperature_rows.empty:
        raise ValueError("Found rows where temp_max_f is lower than temp_min_f")

    # Data validation check example:
    # Percentages and physical measurements should stay in expected ranges.
    invalid_probability_rows = daily_df[
        ~daily_df["precipitation_probability_pct"].between(0, 100, inclusive="both")
    ]
    if not invalid_probability_rows.empty:
        raise ValueError("Found precipitation probability outside 0-100 percent")

    invalid_precipitation_rows = daily_df[daily_df["precipitation_inches"] < 0]
    if not invalid_precipitation_rows.empty:
        raise ValueError("Found negative precipitation values")

    duplicate_dates = daily_df.index[daily_df.index.duplicated()].unique()
    if len(duplicate_dates) > 0:
        raise ValueError(f"Duplicate date keys found: {list(duplicate_dates)}")

    logger.info("Clean forecast validation passed")


def build_weekly_aggregation(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Create an aggregation layer for weekly reporting."""
    aggregation_df = daily_df.copy()
    aggregation_df.index = pd.to_datetime(aggregation_df.index)

    # Aggregation layer example:
    # A reporting layer summarizes row-level facts into business-friendly
    # metrics. Here each week receives average temperatures, total precipitation,
    # and counts of rainy days.
    weekly_df = aggregation_df.resample("W").agg(
        avg_temp_f=("avg_temp_f", "mean"),
        max_temp_f=("temp_max_f", "max"),
        min_temp_f=("temp_min_f", "min"),
        total_precipitation_inches=("precipitation_inches", "sum"),
        rainy_days=("has_precipitation", "sum"),
        avg_uv_index=("uv_index_max", "mean"),
    )

    weekly_df = weekly_df.round(
        {
            "avg_temp_f": 1,
            "max_temp_f": 1,
            "min_temp_f": 1,
            "total_precipitation_inches": 2,
            "avg_uv_index": 1,
        }
    )

    logger.info("Built weekly aggregation with %s rows", len(weekly_df))
    return weekly_df


def incremental_upsert(new_df: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    """Append new data and replace matching date keys from prior pipeline runs."""
    # Incremental loading strategy example:
    # Instead of overwriting blindly, read the existing target if it exists,
    # combine it with the new extract, and keep the latest version for each date.
    # This is a simple date-key upsert pattern.
    if output_path.exists():
        logger.info("Existing output found. Applying incremental upsert into %s", output_path)
        existing_df = pd.read_csv(output_path, parse_dates=["date"])
        existing_df["date"] = existing_df["date"].dt.date
        existing_df = existing_df.set_index("date")

        combined_df = pd.concat([existing_df, new_df])
        combined_df = combined_df[~combined_df.index.duplicated(keep="last")]
        combined_df = combined_df.sort_index()
    else:
        logger.info("No existing output found. Performing initial full load")
        combined_df = new_df.sort_index()

    return combined_df


def load_outputs(daily_df: pd.DataFrame, weekly_df: pd.DataFrame) -> None:
    """Load cleaned daily data and weekly aggregates to reproducible CSV outputs."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    final_daily_df = incremental_upsert(daily_df, DAILY_OUTPUT_PATH)

    # Load example:
    # Write index=True because date is the natural key for this dataset.
    final_daily_df.to_csv(DAILY_OUTPUT_PATH, index=True)
    weekly_df.to_csv(WEEKLY_OUTPUT_PATH, index=True)

    logger.info("Saved daily forecast to %s", DAILY_OUTPUT_PATH)
    logger.info("Saved weekly summary to %s", WEEKLY_OUTPUT_PATH)


def main() -> None:
    """Run the full extract, transform, validate, and load process."""
    try:
        raw_response = extract_weather_forecast()
        validate_raw_response(raw_response)

        daily_df = clean_and_normalize_forecast(raw_response)
        weather_codes_df = load_weather_code_lookup(LOOKUP_PATH)
        daily_df = enrich_with_weather_descriptions(daily_df, weather_codes_df)

        validate_clean_forecast(daily_df)
        weekly_df = build_weekly_aggregation(daily_df)

        load_outputs(daily_df, weekly_df)

        logger.info("ETL pipeline completed successfully")
        logger.info("Sample enriched forecast rows:\n%s", daily_df.head().to_string())
        logger.info("Sample weekly aggregation rows:\n%s", weekly_df.head().to_string())
    except Exception:
        # Logging and error handling example:
        # Log the full traceback, then re-raise so automation tools correctly
        # mark the pipeline run as failed.
        logger.exception("ETL pipeline failed")
        raise


if __name__ == "__main__":
    main()
