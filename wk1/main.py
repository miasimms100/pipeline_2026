import requests
import pandas as pd
# from pprint import pprint

from requests_cache import Path

# API endpoint
base_url = "https://api.open-meteo.com/v1/forecast"
params = {
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

response = requests.get(base_url, params=params).json()

daily_data = response.get("daily", {})
if not daily_data:
    print("No daily data returned. Raw response:\n", response)
else:
    daily_df = pd.DataFrame(daily_data)
    if "time" in daily_df.columns:
        daily_df["date"] = pd.to_datetime(daily_df["time"], unit="s")
        daily_df = daily_df.drop(columns=["time"])
        daily_df = daily_df.set_index(daily_df["date"].dt.date)
        daily_df.index.name = "date"
        daily_df = daily_df.drop(columns=["date"])

    if "sunrise" in daily_df.columns:
        daily_df["sunrise"] = pd.to_datetime(daily_df["sunrise"], unit="s").dt.strftime("%H:%M")
    if "sunset" in daily_df.columns:
        daily_df["sunset"] = pd.to_datetime(daily_df["sunset"], unit="s").dt.strftime("%H:%M")

   

    # print("\nDaily forecast table:\n")
    # print(daily_df.to_string(index=True, justify="left", float_format="{:.2f}".format))
    # pprint(daily_df.dtypes)

path = Path('data/weather_codes.xlsx')

try:
    df = pd.read_excel(path)
    print('columns:', df.columns.tolist())

    if 'Code' in df.columns:
        df['Code'] = df['Code'].astype(str).str.split(r'\s*,\s*')
        df = df.explode('Code')
        df['Code'] = pd.to_numeric(df['Code'], errors='coerce')
        df = df.dropna(subset=['Code'])
        df['Code'] = df['Code'].astype(int)

        if 'Description' in df.columns:
            if 'daily_df' in locals():
                daily_df = daily_df.reset_index()
                daily_df = daily_df.merge(df, left_on='weather_code', right_on='Code', how='left')
                daily_df = daily_df.set_index('date')
                daily_df = daily_df.drop(columns=['Code'], errors='ignore')
                print('\nMerged daily_df with weather code descriptions:')
                print(daily_df[['weather_code', 'Description']].head(20).to_string(index=False))
            else:
                print('daily_df is not available to join with the weather codes lookup.')
        else:
            print('The weather codes lookup file is missing a description column.')
    else:
        print('The weather codes lookup file is missing a code column.')

except Exception as e:
    import traceback; traceback.print_exc()

 # Save the formatted daily data to CSV in the data folder
daily_df.to_csv("data/daily_weather_forecast.csv", index=True)