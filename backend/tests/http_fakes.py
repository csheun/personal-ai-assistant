"""Fake HTTP for provider tests: httpx.MockTransport routes requests to a handler, no sockets involved."""

from collections.abc import Callable

import httpx

Handler = Callable[[httpx.Request], httpx.Response]


def fake_http(handler: Handler) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(record)), seen


def raises(error: Exception) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


SINGAPORE = {"name": "Singapore", "latitude": 1.29, "longitude": 103.85, "country": "Singapore", "admin1": None, "timezone": "Asia/Singapore"}
PARIS_TX = {"name": "Paris", "latitude": 33.66, "longitude": -95.55, "country": "United States", "admin1": "Texas", "timezone": "America/Chicago"}
PARIS_FR = {"name": "Paris", "latitude": 48.85, "longitude": 2.35, "country": "France", "admin1": "Île-de-France", "timezone": "Europe/Paris"}

FORECAST = {
    "timezone": "Asia/Singapore",
    "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
    "current": {"time": "2026-10-19T14:00", "temperature_2m": 31.2, "apparent_temperature": 36.0, "relative_humidity_2m": 70,
                "precipitation": 0.0, "weather_code": 2, "wind_speed_10m": 11.5},
    "daily_units": {"temperature_2m_max": "°C", "precipitation_sum": "mm"},
    "daily": {"time": ["2026-10-20"], "weather_code": [95], "temperature_2m_max": [32.1], "temperature_2m_min": [25.4],
              "precipitation_probability_max": [80], "precipitation_sum": [12.3]},
}  # fmt: skip
