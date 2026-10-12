"""Forecast from Open-Meteo (free, no key)."""

import time
from datetime import date

import requests

# WMO weather interpretation codes, shortened for a forecast table.
WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorms", 96: "Storms, hail", 99: "Storms, hail",
}


def _get(url, params, tries=2):
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))


def fetch(cfg):
    """Open-Meteo, falling back to the National Weather Service (US only)."""
    try:
        return _open_meteo(cfg)
    except requests.RequestException as e:
        print(f"weather: Open-Meteo failed ({e}), trying weather.gov")
        return _nws(cfg)


def _nws(cfg):
    p = cfg["paper"]
    headers = {"User-Agent": f"{p['name']} (personal newspaper)"}
    point = requests.get(f"https://api.weather.gov/points/{p['latitude']},{p['longitude']}",
                         headers=headers, timeout=30)
    point.raise_for_status()
    forecast = requests.get(point.json()["properties"]["forecast"], headers=headers, timeout=30)
    forecast.raise_for_status()

    by_day = {}
    for period in forecast.json()["properties"]["periods"]:
        day = date.fromisoformat(period["startTime"][:10])
        d = by_day.setdefault(day, {"date": day, "summary": None, "high": None, "low": None,
                                    "rain_chance": 0, "snow": 0.0})
        chance = (period.get("probabilityOfPrecipitation") or {}).get("value") or 0
        d["rain_chance"] = max(d["rain_chance"], chance)
        if period["isDaytime"]:
            d["high"] = period["temperature"]
            d["summary"] = period["shortForecast"].split(" then ")[0]
        else:
            d["low"] = period["temperature"]
            d["summary"] = d["summary"] or period["shortForecast"].split(" then ")[0]
    days = [d for d in by_day.values() if d["high"] is not None or d["low"] is not None]
    for d in days:
        d["summary"] = d["summary"].replace("Showers And Thunderstorms", "T-storms").replace("Thunderstorms", "T-storms").replace(" And ", " & ")
        d["high"] = d["high"] if d["high"] is not None else d["low"]
        d["low"] = d["low"] if d["low"] is not None else d["high"]
    return {"today": days[0], "days": days[:5]}


def _open_meteo(cfg):
    p = cfg["paper"]
    r = _get(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": p["latitude"],
            "longitude": p["longitude"],
            "timezone": p["timezone"],
            "temperature_unit": "fahrenheit",
            "precipitation_unit": "inch",
            "forecast_days": 5,
            "daily": ",".join([
                "weather_code", "temperature_2m_max", "temperature_2m_min",
                "precipitation_probability_max", "snowfall_sum",
            ]),
        },
    )
    d = r.json()["daily"]
    days = []
    for i, day in enumerate(d["time"]):
        days.append({
            "date": date.fromisoformat(day),
            "summary": WMO.get(d["weather_code"][i], "—"),
            "high": round(d["temperature_2m_max"][i]),
            "low": round(d["temperature_2m_min"][i]),
            "rain_chance": d["precipitation_probability_max"][i] or 0,
            # Open-Meteo reports snowfall in inches when precipitation_unit=inch.
            "snow": round(d["snowfall_sum"][i] or 0, 1),
        })
    return {"today": days[0], "days": days}
