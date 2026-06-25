import requests

FORECAST_URL  = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL   = "https://archive-api.open-meteo.com/v1/archive"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"


def get_elevation(lat: float, lon: float) -> float:
    resp = requests.get(ELEVATION_URL, params={"latitude": lat, "longitude": lon}, timeout=10)
    resp.raise_for_status()
    return resp.json().get("elevation", [0])[0]


def get_current_weather(lat: float, lon: float) -> dict:
    params = {
        "latitude":    lat,
        "longitude":   lon,
        "daily":       ["temperature_2m_max", "temperature_2m_min", "precipitation_sum",
                        "relative_humidity_2m_max", "shortwave_radiation_sum", "windspeed_10m_max",
                        "sunshine_duration"],
        "timezone":    "Asia/Manila",
        "forecast_days": 7,
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("daily", {})

    temp_max  = data.get("temperature_2m_max", [27])[0]
    temp_min  = data.get("temperature_2m_min", [24])[0]
    avg_temp  = round((temp_max + temp_min) / 2, 1)
    rainfall  = sum(data.get("precipitation_sum", [0]))
    humidity  = data.get("relative_humidity_2m_max", [80])[0]
    radiation = data.get("shortwave_radiation_sum", [17])[0]
    wind      = data.get("windspeed_10m_max", [3])[0]
    sunshine  = data.get("sunshine_duration", [21600])[0] / 3600  # convert seconds to hours

    return {
        "avg_temperature":        avg_temp,
        "temp_at_flowering":      avg_temp,
        "weekly_rainfall_mm":     round(rainfall, 1),
        "humidity_pct":           humidity,
        "solar_radiation":        round(radiation, 1),
        "wind_speed_ms":          round(wind / 3.6, 1),  # km/h to m/s
        "sunshine_hours":         round(sunshine, 1),
    }


def get_annual_rainfall(lat: float, lon: float) -> float:
    from datetime import date, timedelta
    end   = date.today() - timedelta(days=5)
    start = end - timedelta(days=365)
    params = {
        "latitude":   lat,
        "longitude":  lon,
        "start_date": start.isoformat(),
        "end_date":   end.isoformat(),
        "daily":      "precipitation_sum",
        "timezone":   "Asia/Manila",
    }
    resp = requests.get(ARCHIVE_URL, params=params, timeout=15)
    resp.raise_for_status()
    values = resp.json().get("daily", {}).get("precipitation_sum", [])
    return round(sum(v for v in values if v is not None), 1)
