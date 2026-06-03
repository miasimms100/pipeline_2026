import requests
import pandas as pd
from requests_cache import Path

"""
API Practice Examples - Open-Meteo Weather API

This script demonstrates how to:
1. Make API calls using the requests library
2. Extract and transform JSON responses into DataFrames
3. Perform data processing operations (merging, expanding, formatting)
4. Save processed data to CSV files

API Reference: https://open-meteo.com/en/docs
"""

# ============================================================================
# API CALL 1: Open-Meteo Weather Forecast API
# ============================================================================
print("=" * 80)
print("API CALL 1: Fetching Weather Forecast Data")
print("=" * 80)

# The Open-Meteo API provides free access to weather data without authentication
# Endpoint: https://api.open-meteo.com/v1/forecast
base_url = "https://api.open-meteo.com/v1/forecast"

# Parameters dictionary specifies the location, variables, and formatting options
# - latitude/longitude: Geographic coordinates (Louisville, KY in this example)
# - daily: List of daily weather variables to retrieve from the API
# - timezone: Convert timestamps to local timezone (America/New_York)
# - forecast_days: Number of days to forecast (max 16 days)
# - timeformat: Return timestamps as Unix time (seconds since 1970-01-01)
# - units: Specify temperature, wind, and precipitation units
params = {
    # Location coordinates
    "latitude": 38.2542,  # Louisville, KY latitude
    "longitude": -85.7594,  # Louisville, KY longitude
    
    # Daily weather variables requested from API
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
    # Timezone for timestamp conversion
    "timezone": "America/New_York",  # Eastern Time (ET)
    
    # Forecast parameters
    "forecast_days": 16,  # Request 16-day forecast (Open-Meteo max: 16 days)
    "timeformat": "unixtime",  # Use Unix timestamps (easier to parse than ISO8601)
    
    # Unit specifications for returned data
    "wind_speed_unit": "mph",  # Wind speed in miles per hour
    "temperature_unit": "fahrenheit",  # Temperature in Fahrenheit (not Celsius)
    "precipitation_unit": "inch",  # Precipitation in inches (not mm)
}

# Make the HTTP GET request to the API and parse the JSON response
# The response will contain a 'daily' object with arrays of each requested variable
response = requests.get(base_url, params=params).json()
print("\nAPI Response Keys:", response.keys())

# ============================================================================
# DATA PROCESSING 1: Transform Daily Weather Data
# ============================================================================
print("\n" + "=" * 80)
print("DATA PROCESSING 1: Transform Daily Weather Data")
print("=" * 80)

# Extract the 'daily' data from response (contains arrays of weather variables)
# response.get() safely retrieves the key, returning empty dict if not found
daily_data = response.get("daily", {})

if not daily_data:
    print("No daily data returned. Raw response:\n", response)
else:
    # Convert the nested dictionary of arrays into a pandas DataFrame
    # This makes it easier to manipulate and transform the data
    daily_df = pd.DataFrame(daily_data)
    print("\nOriginal Columns:", daily_df.columns.tolist())
    print("Original Shape:", daily_df.shape)
    
    # TRANSFORMATION 1: Convert unix timestamp to readable dates
    # Unix timestamps (seconds since 1970-01-01) need to be converted to datetime
    if "time" in daily_df.columns:
        # Convert Unix time (seconds) to pandas datetime, then extract just the date
        daily_df["date"] = pd.to_datetime(daily_df["time"], unit="s")
        daily_df = daily_df.drop(columns=["time"])  # Remove original unix timestamp
        daily_df = daily_df.set_index(daily_df["date"].dt.date)  # Use date as index for easy filtering
        daily_df.index.name = "date"
        daily_df = daily_df.drop(columns=["date"])  # Remove duplicate date column
        print("\nAfter timestamp conversion:")
        print(daily_df.head(3))

    # TRANSFORMATION 2: Convert sunrise/sunset from unix time to HH:MM format
    # This makes the time values human-readable (e.g., "06:15" instead of 1715350500)
    if "sunrise" in daily_df.columns:
        # strftime("%H:%M") formats the datetime as HH:MM (24-hour format)
        daily_df["sunrise"] = pd.to_datetime(daily_df["sunrise"], unit="s").dt.strftime("%H:%M")
    if "sunset" in daily_df.columns:
        daily_df["sunset"] = pd.to_datetime(daily_df["sunset"], unit="s").dt.strftime("%H:%M")
    
    print("\nAfter time formatting:")
    print(daily_df[["sunrise", "sunset"]].head(3))

# ============================================================================
# DATA PROCESSING 2: Read Excel File and Split Codes
# ============================================================================
print("\n" + "=" * 80)
print("DATA PROCESSING 2: Load Weather Codes from Excel")
print("=" * 80)

# Load a reference file mapping weather codes to descriptions
# Example: Code 0 = "Clear sky", Code 1,2,3 = "Partly cloudy", etc.
path = Path('data/weather_codes.xlsx')

try:
    # Read Excel file into a DataFrame
    # This file contains weather code lookups with descriptions
    df = pd.read_excel(path)
    print("\nWeather Codes - Original Columns:", df.columns.tolist())
    print("Original Shape:", df.shape)
    print("\nFirst 5 rows:")
    print(df.head(5).to_string(index=False))

    # ========================================================================
    # DATA PROCESSING 3: Split Comma-Separated Codes into Separate Rows
    # ========================================================================
    print("\n" + "=" * 80)
    print("DATA PROCESSING 3: Expand Comma-Separated Codes")
    print("=" * 80)
    
    # Some weather descriptions apply to multiple codes (e.g., "1,2,3")
    # This section splits those comma-separated values into individual rows
    # After expansion: one row per code instead of multiple codes per row
    if 'Code' in df.columns:
        print("\nBefore explode:", df.shape)
        
        # Convert Code column to string and split on commas (with optional whitespace)
        df['Code'] = df['Code'].astype(str).str.split(r'\s*,\s*')
        
        # explode() creates a new row for each item in the list
        # Duplicates the Description column for each code
        df = df.explode('Code')
        
        # Convert split codes to numeric type (handles invalid entries)
        df['Code'] = pd.to_numeric(df['Code'], errors='coerce')
        df = df.dropna(subset=['Code'])  # Remove any rows where Code conversion failed
        df['Code'] = df['Code'].astype(int)  # Convert to integer type
        print("After explode:", df.shape)
        print("\nFirst 10 rows after expansion:")
        print(df.head(10).to_string(index=False))

        # ====================================================================
        # DATA PROCESSING 4: Merge Forecast Data with Weather Code Descriptions
        # ====================================================================
        print("\n" + "=" * 80)
        print("DATA PROCESSING 4: Merge Forecast with Weather Codes")
        print("=" * 80)
        
        # This step joins the forecast data (daily_df) with the code descriptions (df)
        # Result: Each forecast row gets a Description column matching its weather_code
        if 'Description' in df.columns:
            if 'daily_df' in locals():
                print("\nBefore merge - daily_df shape:", daily_df.shape)
                
                # reset_index() converts the date index back to a regular column
                # This is necessary for the merge operation
                daily_df_reset = daily_df.reset_index()
                
                # Merge (SQL LEFT JOIN equivalent) on weather_code = Code
                # left_on: column from daily_df to match
                # right_on: column from df to match
                # how='left': keep all rows from daily_df, add Code descriptions where they match
                daily_df_merged = daily_df_reset.merge(df, left_on='weather_code', right_on='Code', how='left')
                
                daily_df_merged = daily_df_merged.set_index('date')  # Restore date as index
                daily_df_merged = daily_df_merged.drop(columns=['Code'], errors='ignore')  # Remove duplicate Code column
                print("After merge - daily_df shape:", daily_df_merged.shape)
                
                print('\nMerged data - Weather Code and Description:')
                print(daily_df_merged[['weather_code', 'Description']].head(10).to_string(index=False))
            else:
                print('daily_df is not available to join with the weather codes lookup.')
        else:
            print('The weather codes lookup file is missing a Description column.')
    else:
        print('The weather codes lookup file is missing a Code column.')

except Exception as e:
    import traceback
    print("Error reading weather codes:")
    traceback.print_exc()

# ============================================================================
# DATA PROCESSING 5: Save to CSV
# ============================================================================
print("\n" + "=" * 80)
print("DATA PROCESSING 5: Save Forecast Data to CSV")
print("=" * 80)

# Save the processed DataFrame to a CSV file for later use
# CSV format is universal and easy to import into other applications
try:
    if 'daily_df' in locals():
        output_path = "data/daily_weather_forecast.csv"
        # to_csv() exports the DataFrame with the date index included
        daily_df.to_csv(output_path, index=True)
        print(f"\n✓ Data saved to {output_path}")
        print(f"  Shape: {daily_df.shape}")
        print(f"  Columns: {daily_df.columns.tolist()}")
except Exception as e:
    print(f"Error saving to CSV: {e}")

print("\n" + "=" * 80)
print("API Practice Complete")
print("=" * 80)

# ============================================================================
# API CALL 2: Open-Meteo Current Weather API (Using openmeteo library)
# ============================================================================
print("\n" + "=" * 80)
print("API CALL 2: Fetching Current Weather Data")
print("=" * 80)

try:
    import openmeteo_requests
    
    # Setup the Open-Meteo API client
    # The openmeteo_requests library is a Python wrapper for the Open-Meteo API
    # It provides convenience methods like weather_api() instead of raw HTTP calls
    openmeteo = openmeteo_requests.Client()
    
    # Alternative approach: Use the official Python SDK for cleaner API interactions
    url = "https://api.open-meteo.com/v1/forecast"
    
    # Current weather parameters (similar to forecast but retrieves current conditions)
    # current: List of variables for the most recent observation
    params = {
        "latitude": 38.2542,
        "longitude": -85.7594,
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "is_day",
            "precipitation",
"weather_code",  # Current weather condition code
        "cloud_cover"  # Current cloud cover percentage
    ],
    "timezone": "America/New_York",  # Convert times to Eastern Time
    "forecast_days": 16,  # Still needed even for current weather (for consistency)
    "timeformat": "unixtime",  # Unix timestamps
    "wind_speed_unit": "mph",
    "temperature_unit": "fahrenheit",
    "precipitation_unit": "inch",
    }
    
    print("\nAPI Request Parameters:")
    print(f"  URL: {url}")
    print(f"  Latitude: {params['latitude']}")
    print(f"  Longitude: {params['longitude']}")
    
    # ========================================================================
    # DATA PROCESSING 6: Parse Current Weather Response
    # ========================================================================
    print("\n" + "=" * 80)
    print("DATA PROCESSING 6: Parse Current Weather Data")
    print("=" * 80)
    
    # Call the weather_api() method with URL and parameters
    # Returns a list of Response objects (one per location requested)
    responses = openmeteo.weather_api(url, params=params)
    
    # Process first location (index 0)
    # For multiple locations, use a for-loop to iterate through all responses
    response = responses[0]
    
    # Extract location metadata from the response object
    print("\nLocation Information:")
    print(f"  Coordinates: {response.Latitude()}°N {response.Longitude()}°E")
    print(f"  Elevation: {response.Elevation()} m asl")
    print(f"  Timezone: {response.Timezone()} {response.TimezoneAbbreviation()}")
    print(f"  UTC Offset: {response.UtcOffsetSeconds()}s")
    
    # Extract current weather data from the response
    # IMPORTANT: The order of Variables() calls MUST match the order of variables in params['current']
    # If you request ["temperature_2m", "relative_humidity_2m", ...], 
    # then Variables(0) is temperature, Variables(1) is humidity, etc.
    current = response.Current()
    
    # Access each variable by its position in the requested array (0-indexed)
    current_temperature_2m = current.Variables(0).Value()  # Index 0 = temperature_2m
    current_relative_humidity_2m = current.Variables(1).Value()  # Index 1 = relative_humidity_2m
    current_apparent_temperature = current.Variables(2).Value()  # Index 2 = apparent_temperature
    current_is_day = current.Variables(3).Value()  # Index 3 = is_day (1=daytime, 0=nighttime)
    current_precipitation = current.Variables(4).Value()  # Index 4 = precipitation
    current_weather_code = current.Variables(5).Value()  # Index 5 = weather_code
    current_cloud_cover = current.Variables(6).Value()  # Index 6 = cloud_cover
    
    # Display the parsed current weather data
    print("\nCurrent Weather Conditions:")
    print(f"  Time: {current.Time()}")  # Unix timestamp of the observation
    print(f"  Temperature: {current_temperature_2m}°F")  # Actual air temperature at 2m height
    print(f"  Relative Humidity: {current_relative_humidity_2m}%")  # Percentage of moisture in air
    print(f"  Apparent Temperature: {current_apparent_temperature}°F")  # "Feels like" temperature (accounts for wind/humidity)
    print(f"  Is Daytime: {bool(current_is_day)}")  # True if sun is above horizon
    print(f"  Precipitation: {current_precipitation} in")  # Current precipitation rate
    print(f"  Weather Code: {current_weather_code}")  # Weather condition code (reference lookup table)
    print(f"  Cloud Cover: {current_cloud_cover}%")  # Percentage of sky covered by clouds
    
except ImportError:
    print("openmeteo_requests library not installed. Install with: pip install openmeteo-requests")
    print("Alternative: Use requests library directly (see API CALL 1 for example)")
except Exception as e:
    import traceback
    print("Error fetching current weather data:")
    traceback.print_exc()

print("\n" + "=" * 80)
print("API Practice Complete - All examples executed successfully!")
print("=" * 80)