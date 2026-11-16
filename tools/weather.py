"""Daily forecast from Open-Meteo (free, no key). Plain Python, no Claude."""

import httpx2

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
NOVI_SAD = (45.2671, 19.8335)


def get_forecast(lat: float = NOVI_SAD[0], lon: float = NOVI_SAD[1], days: int = 1) -> list[dict]:
    """Return one dict per day: date, min/max °C, max rain chance %, snowfall cm.

    Open-Meteo has no "snow chance"; snowfall_cm > 0 is the closest signal.
    """
    resp = httpx2.get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_min,temperature_2m_max,"
            "precipitation_probability_max,snowfall_sum",
            "timezone": "Europe/Belgrade",
            "forecast_days": days,
        },
        timeout=10,
    )
    resp.raise_for_status()
    d = resp.json()["daily"]
    return [
        {
            "date": d["time"][i],
            "min_c": d["temperature_2m_min"][i],
            "max_c": d["temperature_2m_max"][i],
            "precip_chance_pct": d["precipitation_probability_max"][i],
            "snowfall_cm": d["snowfall_sum"][i],
        }
        for i in range(len(d["time"]))
    ]
