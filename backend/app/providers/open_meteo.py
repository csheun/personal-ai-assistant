"""Open-Meteo client (https://open-meteo.com/en/docs): geocoding + forecast. No API key required.

Free for non-commercial use with fair-use limits. Forecasts cover today up to 16 days ahead.
"""

import logging
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.providers.errors import ProviderError

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MAX_FORECAST_DAYS = 16

_CURRENT = "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m"
_DAILY = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum"


class Place(BaseModel):
    name: str
    country: str | None = None
    admin1: str | None = None  # state / region
    latitude: float
    longitude: float
    timezone: str | None = None


class OpenMeteoClient:
    def __init__(self, http: httpx.AsyncClient, *, timeout_seconds: float = 8.0) -> None:
        self._http = http
        self._timeout = timeout_seconds

    async def geocode(self, query: str) -> Place:
        """Resolves "Paris" or "Paris, France" / "Springfield, Illinois" to coordinates."""
        name, _, qualifier = (part.strip() for part in query.partition(","))
        data = await self._get(GEOCODING_URL, {"name": name, "count": 10, "language": "en", "format": "json"})
        try:
            places = [Place.model_validate(item) for item in data.get("results") or []]
        except ValidationError as exc:
            raise ProviderError("open-meteo", "bad_response", "The weather service returned unexpected data.") from exc
        if qualifier:
            wanted = qualifier.lower()
            places = [
                p for p in places
                if wanted in {(p.country or "").lower(), (p.admin1 or "").lower()}
                or (p.country or "").lower().startswith(wanted)
            ] or places
        if not places:
            raise ProviderError("open-meteo", "not_found", f"Couldn't find a place called '{query}'.")
        return places[0]

    async def forecast(
        self, place: Place, *, start: date | None, end: date | None, fahrenheit: bool = False
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "latitude": place.latitude,
            "longitude": place.longitude,
            "current": _CURRENT,
            "daily": _DAILY,
            "timezone": "auto",
        }
        if start and end:
            params |= {"start_date": start.isoformat(), "end_date": end.isoformat()}
        else:
            params["forecast_days"] = 1
        if fahrenheit:
            params |= {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch"}
        return await self._get(FORECAST_URL, params)

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._http.get(url, params=params, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise ProviderError("open-meteo", "timeout", "The weather service didn't respond in time.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("open-meteo", "unavailable", "Couldn't reach the weather service.") from exc

        if response.status_code == 400:
            reason = _json(response).get("reason", "invalid request")
            logger.warning("Open-Meteo rejected request: %s", reason)
            raise ProviderError("open-meteo", "bad_request", f"The weather service rejected the request ({reason}).")
        if response.status_code == 429:
            raise ProviderError("open-meteo", "rate_limited", "The weather service is busy. Try again shortly.")
        if response.status_code >= 400:
            raise ProviderError("open-meteo", "unavailable", f"The weather service returned an error ({response.status_code}).")
        data = _json(response)
        if not data:
            raise ProviderError("open-meteo", "bad_response", "The weather service returned unexpected data.")
        return data


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
