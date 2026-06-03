"""
Supabase PostgreSQL ETL Loader
------------------------------
Creates the PostgreSQL table schema in Supabase and loads:

- data/daily_weather_forecast.csv
- data/tourism.csv
- data/weather_codes.xlsx

Required packages:
    pip install pandas sqlalchemy psycopg2-binary openpyxl python-dotenv

.env values expected:
    DB_PASSWORD=your_supabase_database_password
    DB_REF=your_supabase_project_ref

Optional:
    SUPABASE_DB_URL=postgresql+psycopg2://...
    RESET_TABLES=true
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.types import Boolean, Date, Float, Integer, String, Time


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

WEATHER_FORECAST_CSV = DATA_DIR / "daily_weather_forecast.csv"
TOURISM_CSV = DATA_DIR / "tourism.csv"
WEATHER_CODES_XLSX = DATA_DIR / "weather_codes.xlsx"

CATEGORY_COLUMNS = [
    "water",
    "play_sweat_it_out",
    "small_kid_friendly_under_10",
    "big_kid_friendly_over_10",
    "culture",
    "nature",
]

# Connection configuration
# This helper builds the database connection URL from environment variables.
# It reads credentials from a .env file and supports a direct SUPABASE_DB_URL override.

def get_database_url() -> str:
    load_dotenv()

    database_url = os.getenv("SUPABASE_DB_URL")
    if database_url:
        return database_url

    password = os.getenv("DB_PASSWORD")
    db_ref = os.getenv("DB_REF")

    if not password or not db_ref:
        raise RuntimeError(
            "Set SUPABASE_DB_URL, or set both DB_PASSWORD and DB_REF in your .env file."
        )

    return (
        "postgresql+psycopg2://"
        f"postgres:{password}"
        f"@db.{db_ref}.supabase.co:5432/postgres"
    )


def table_reset_enabled() -> bool:
    # Allow users to choose whether to drop existing tables before loading data.
    # This is useful when you want a fresh import instead of appending to old data.
    return os.getenv("RESET_TABLES", "true").strip().lower() in {"1", "true", "yes", "y"}


# Schema creation
# This function defines the tables and relationships used by the ETL process.
# It optionally drops existing tables and recreates the schema from scratch.
def create_schema(engine) -> None:
    drop_sql = """
    DROP TABLE IF EXISTS public.attraction_category CASCADE;
    DROP TABLE IF EXISTS public.attraction CASCADE;
    DROP TABLE IF EXISTS public.category CASCADE;
    DROP TABLE IF EXISTS public.location CASCADE;
    DROP TABLE IF EXISTS public.weather_forecast CASCADE;
    DROP TABLE IF EXISTS public.weather_code CASCADE;
    """

    create_sql = """
    CREATE TABLE IF NOT EXISTS public.weather_code (
        weather_code_id INTEGER PRIMARY KEY,
        description TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS public.weather_forecast (
        forecast_id BIGSERIAL PRIMARY KEY,
        forecast_date DATE NOT NULL UNIQUE,
        weather_code_id INTEGER NOT NULL REFERENCES public.weather_code(weather_code_id),
        temperature_max DOUBLE PRECISION,
        temperature_min DOUBLE PRECISION,
        sunrise TIME,
        sunset TIME,
        precipitation_sum DOUBLE PRECISION,
        precipitation_hours DOUBLE PRECISION,
        precipitation_probability_max INTEGER,
        daylight_duration DOUBLE PRECISION,
        sunshine_duration DOUBLE PRECISION,
        uv_index_max DOUBLE PRECISION
    );

    CREATE TABLE IF NOT EXISTS public.location (
        location_id INTEGER PRIMARY KEY,
        street_address TEXT NOT NULL,
        city TEXT NOT NULL,
        state TEXT NOT NULL,
        UNIQUE (street_address, city, state)
    );

    CREATE TABLE IF NOT EXISTS public.attraction (
        attraction_id INTEGER PRIMARY KEY,
        attraction_name TEXT NOT NULL,
        phone_number TEXT,
        website TEXT,
        is_indoor BOOLEAN NOT NULL DEFAULT false,
        adult_only BOOLEAN NOT NULL DEFAULT false,
        location_id INTEGER NOT NULL REFERENCES public.location(location_id)
    );

    CREATE TABLE IF NOT EXISTS public.category (
        category_id INTEGER PRIMARY KEY,
        category_name TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS public.attraction_category (
        attraction_id INTEGER NOT NULL REFERENCES public.attraction(attraction_id),
        category_id INTEGER NOT NULL REFERENCES public.category(category_id),
        PRIMARY KEY (attraction_id, category_id)
    );
    """

    with engine.begin() as conn:
        if table_reset_enabled():
            conn.execute(text(drop_sql))
        conn.execute(text(create_sql))


# Data transformation helper
# The weather codes file contains descriptions and one or more numeric codes per row.
# This function expands those rows into a normalized table of weather_code_id -> description.
def expand_weather_codes(weather_codes_df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, row in weather_codes_df.iterrows():
        description = row["Description"]
        codes = re.findall(r"\d+", str(row["Code"]))

        for code in codes:
            rows.append(
                {
                    "weather_code_id": int(code),
                    "description": description,
                }
            )

    return pd.DataFrame(rows).drop_duplicates(subset=["weather_code_id"])


# Source ingestion
# Reads raw CSV/XLSX files into pandas DataFrames for later transformation.
def load_source_files() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    weather_df = pd.read_csv(WEATHER_FORECAST_CSV)
    weather_codes_df = pd.read_excel(WEATHER_CODES_XLSX)
    tourism_df = pd.read_csv(TOURISM_CSV)

    print("Source files loaded successfully.")
    return weather_df, weather_codes_df, tourism_df


# Weather data transformation
# Rename columns and convert raw values into types that match the target schema.
def build_weather_tables(
    weather_df: pd.DataFrame,
    weather_codes_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    weather_code_df = expand_weather_codes(weather_codes_df)

    weather_forecast_df = weather_df.rename(
        columns={
            "date": "forecast_date",
            "weather_code": "weather_code_id",
            "temperature_2m_max": "temperature_max",
            "temperature_2m_min": "temperature_min",
        }
    )

    weather_forecast_df["forecast_date"] = pd.to_datetime(
        weather_forecast_df["forecast_date"]
    ).dt.date
    weather_forecast_df["sunrise"] = pd.to_datetime(
        weather_forecast_df["sunrise"], format="%H:%M"
    ).dt.time
    weather_forecast_df["sunset"] = pd.to_datetime(
        weather_forecast_df["sunset"], format="%H:%M"
    ).dt.time

    return weather_code_df, weather_forecast_df


# Tourism data transformation
# Create normalized location, attraction, category, and relationship tables from the tourism CSV.
def build_tourism_tables(
    tourism_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    unnamed_cols = [col for col in tourism_df.columns if "Unnamed" in col]
    tourism_df = tourism_df.drop(columns=unnamed_cols)

    location_df = (
        tourism_df[["street_address", "city", "state"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    location_df["location_id"] = location_df.index + 1

    tourism_df = tourism_df.merge(
        location_df,
        on=["street_address", "city", "state"],
        how="left",
    )

    attraction_df = tourism_df[
        [
            "attraction_uuid",
            "attraction",
            "phone_number",
            "website",
            "is_indoor",
            "adult_only",
            "location_id",
        ]
    ].copy()

    attraction_df = attraction_df.rename(
        columns={
            "attraction_uuid": "attraction_id",
            "attraction": "attraction_name",
        }
    )
    attraction_df["attraction_id"] = attraction_df["attraction_id"].astype(int)
    attraction_df["is_indoor"] = attraction_df["is_indoor"].astype(bool)
    attraction_df["adult_only"] = attraction_df["adult_only"].astype(bool)

    category_df = pd.DataFrame({"category_name": CATEGORY_COLUMNS})
    category_df["category_id"] = category_df.index + 1

    category_id_by_name = dict(zip(category_df["category_name"], category_df["category_id"]))
    bridge_rows = []

    for _, row in tourism_df.iterrows():
        for category in CATEGORY_COLUMNS:
            value = row.get(category)
            if pd.notnull(value) and str(value).strip().lower() in {"1", "true", "yes", "y"}:
                bridge_rows.append(
                    {
                        "attraction_id": int(row["attraction_uuid"]),
                        "category_id": int(category_id_by_name[category]),
                    }
                )

    attraction_category_df = pd.DataFrame(bridge_rows).drop_duplicates()

    return location_df, attraction_df, category_df, attraction_category_df


# Data loading helper
# Writes a DataFrame to the target PostgreSQL table using SQLAlchemy.
def write_table(df: pd.DataFrame, table_name: str, engine, dtype: dict) -> None:
    print(f"Loading {table_name} table...")
    df.to_sql(
        table_name,
        engine,
        schema="public",
        if_exists="append",
        index=False,
        method="multi",
        chunksize=1000,
        dtype=dtype,
    )


# Table loader
# Loads all transformed DataFrames into the matching database tables in the correct order.
def load_tables(
    engine,
    weather_code_df: pd.DataFrame,
    weather_forecast_df: pd.DataFrame,
    location_df: pd.DataFrame,
    attraction_df: pd.DataFrame,
    category_df: pd.DataFrame,
    attraction_category_df: pd.DataFrame,
) -> None:
    write_table(
        weather_code_df,
        "weather_code",
        engine,
        {
            "weather_code_id": Integer(),
            "description": String(),
        },
    )
    write_table(
        weather_forecast_df,
        "weather_forecast",
        engine,
        {
            "forecast_date": Date(),
            "weather_code_id": Integer(),
            "temperature_max": Float(),
            "temperature_min": Float(),
            "sunrise": Time(),
            "sunset": Time(),
            "precipitation_sum": Float(),
            "precipitation_hours": Float(),
            "precipitation_probability_max": Integer(),
            "daylight_duration": Float(),
            "sunshine_duration": Float(),
            "uv_index_max": Float(),
        },
    )
    write_table(
        location_df,
        "location",
        engine,
        {
            "location_id": Integer(),
            "street_address": String(),
            "city": String(),
            "state": String(),
        },
    )
    write_table(
        attraction_df,
        "attraction",
        engine,
        {
            "attraction_id": Integer(),
            "attraction_name": String(),
            "phone_number": String(),
            "website": String(),
            "is_indoor": Boolean(),
            "adult_only": Boolean(),
            "location_id": Integer(),
        },
    )
    write_table(
        category_df,
        "category",
        engine,
        {
            "category_id": Integer(),
            "category_name": String(),
        },
    )
    write_table(
        attraction_category_df,
        "attraction_category",
        engine,
        {
            "attraction_id": Integer(),
            "category_id": Integer(),
        },
    )


# Main workflow orchestration
# This function ties the ETL steps together: connect, extract raw files, transform data, create schema,
# and load the cleaned data into the database.
def main() -> None:
    engine = create_engine(get_database_url())

    weather_df, weather_codes_df, tourism_df = load_source_files()
    weather_code_df, weather_forecast_df = build_weather_tables(weather_df, weather_codes_df)
    location_df, attraction_df, category_df, attraction_category_df = build_tourism_tables(
        tourism_df
    )

    print("Creating Supabase PostgreSQL schema...")
    create_schema(engine)

    load_tables(
        engine,
        weather_code_df,
        weather_forecast_df,
        location_df,
        attraction_df,
        category_df,
        attraction_category_df,
    )

    print("===================================")
    print("ETL LOAD COMPLETE")
    print("===================================")


if __name__ == "__main__":
    main()