"""
Supabase PostgreSQL ETL Loader
--------------------------------
Loads tourism and weather datasets into a normalized PostgreSQL schema
using pandas + SQLAlchemy.

Required packages:
    pip install pandas sqlalchemy psycopg2-binary openpyxl

Before running:
1. Create tables in Supabase using the provided DDL script.
2. Update DATABASE_URL below.
3. Place source files in the same folder as this script.

Files expected:
- daily_weather_forecast.csv
- tourism.csv
- weather_codes.xlsx
"""

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.types import (
    Integer,
    Float,
    String,
    Boolean,
    Date,
    DateTime
)
from sqlalchemy.dialects.postgresql import UUID
import os
from dotenv import load_dotenv
load_dotenv()  # Loads variables from .env
password = os.getenv("DB_PASSWORD")
DB_REF = os.getenv("DB_REF")
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# =========================================================
# DATABASE CONNECTION
# =========================================================

DATABASE_URL = (
    "postgresql+psycopg2://"
    f"postgres:{password}"
    f"@db.{DB_REF}.supabase.co:5432/postgres"
)

engine = create_engine(DATABASE_URL)

# =========================================================
# LOAD SOURCE FILES
# =========================================================

weather_df = pd.read_csv("C:\\Users\\miasi\\Documents\\GitHub\\pipeline_2026\\data\\daily_weather_forecast.csv")
weather_codes_df = pd.read_excel("C:\\Users\\miasi\\Documents\\GitHub\\pipeline_2026\\data\\weather_codes.xlsx")
tourism_df = pd.read_csv("C:\\Users\\miasi\\Documents\\GitHub\\pipeline_2026\\data\\tourism.csv")

print("Source files loaded successfully.")

# =========================================================
# CLEAN WEATHER DATA
# =========================================================

weather_df = weather_df.rename(columns={
    "date": "forecast_date",
    "weather_code": "weather_code_id",
    "temperature_2m_max": "temperature_max",
    "temperature_2m_min": "temperature_min"
})

weather_df["forecast_date"] = pd.to_datetime(
    weather_df["forecast_date"]
)

weather_df["sunrise"] = pd.to_datetime(
    weather_df["sunrise"]
)

weather_df["sunset"] = pd.to_datetime(
    weather_df["sunset"]
)

# =========================================================
# CLEAN WEATHER CODE LOOKUP
# =========================================================

weather_codes_df = weather_codes_df.rename(columns={
    "Code": "weather_code_id",
    "Description": "description"
})

# =========================================================
# CLEAN TOURISM DATA
# =========================================================

unnamed_cols = [
    col for col in tourism_df.columns
    if "Unnamed" in col
]

tourism_df = tourism_df.drop(columns=unnamed_cols)

# =========================================================
# CREATE LOCATION TABLE
# =========================================================

location_df = tourism_df[[
    "street_address",
    "city",
    "state"
]].drop_duplicates().reset_index(drop=True)

location_df["location_id"] = location_df.index + 1

# =========================================================
# MERGE LOCATION IDS
# =========================================================

tourism_df = tourism_df.merge(
    location_df,
    on=["street_address", "city", "state"],
    how="left"
)

# =========================================================
# CREATE ATTRACTION TABLE
# =========================================================

attraction_df = tourism_df[[
    "attraction_uuid",
    "attraction",
    "phone_number",
    "website",
    "is_indoor",
    "adult_only",
    "location_id"
]].copy()

attraction_df = attraction_df.rename(columns={
    "attraction": "attraction_name"
})

# =========================================================
# CREATE CATEGORY TABLE
# =========================================================

category_columns = [
    "water",
    "play_sweat_it_out",
    "small_kid_friendly_under_10",
    "big_kid_friendly_over_10",
    "culture",
    "nature"
]

category_df = pd.DataFrame({
    "category_name": category_columns
})

category_df["category_id"] = category_df.index + 1

# =========================================================
# CREATE BRIDGE TABLE
# =========================================================

bridge_rows = []

for _, row in tourism_df.iterrows():

    for category in category_columns:

        value = row.get(category)

        if pd.notnull(value):

            if str(value).strip().lower() in [
                "1",
                "true",
                "yes",
                "y"
            ]:

                category_id = category_df.loc[
                    category_df["category_name"] == category,
                    "category_id"
                ].iloc[0]

                bridge_rows.append({
                    "attraction_uuid": row["attraction_uuid"],
                    "category_id": category_id
                })

attraction_category_df = pd.DataFrame(bridge_rows)

# =========================================================
# LOAD TABLES TO SUPABASE
# =========================================================

print("Loading weather_code table...")

weather_codes_df.to_sql(
    "weather_code",
    engine,
    schema="public",
    if_exists="append",
    index=False,
    method="multi",
    chunksize=1000,
    dtype={
        "weather_code_id": Integer(),
        "description": String(255)
    }
)

print("Loading weather_forecast table...")

weather_df.to_sql(
    "weather_forecast",
    engine,
    schema="public",
    if_exists="append",
    index=False,
    method="multi",
    chunksize=1000,
    dtype={
        "forecast_date": Date(),
        "weather_code_id": Integer(),
        "temperature_max": Float(),
        "temperature_min": Float(),
        "sunrise": DateTime(),
        "sunset": DateTime()
    }
)

print("Loading location table...")

location_df.to_sql(
    "location",
    engine,
    schema="public",
    if_exists="append",
    index=False,
    method="multi",
    chunksize=1000,
    dtype={
        "location_id": Integer(),
        "street_address": String(255),
        "city": String(100),
        "state": String(50)
    }
)

print("Loading attraction table...")

attraction_df.to_sql(
    "attraction",
    engine,
    schema="public",
    if_exists="append",
    index=False,
    method="multi",
    chunksize=1000,
    dtype={
        "attraction_uuid": UUID(as_uuid=False),
        "attraction_name": String(255),
        "phone_number": String(50),
        "website": String(255),
        "is_indoor": Boolean(),
        "adult_only": Boolean(),
        "location_id": Integer()
    }
)

print("Loading category table...")

category_df.to_sql(
    "category",
    engine,
    schema="public",
    if_exists="append",
    index=False,
    method="multi",
    chunksize=1000,
    dtype={
        "category_id": Integer(),
        "category_name": String(100)
    }
)

print("Loading attraction_category bridge table...")

attraction_category_df.to_sql(
    "attraction_category",
    engine,
    schema="public",
    if_exists="append",
    index=False,
    method="multi",
    chunksize=1000,
    dtype={
        "attraction_uuid": UUID(as_uuid=False),
        "category_id": Integer()
    }
)

print("===================================")
print("ETL LOAD COMPLETE")
print("===================================")