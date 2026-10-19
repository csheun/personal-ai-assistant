"""Weather tool, in two implementations under the same name:

- `weather_tool`: MOCKED, deterministic fake data (MOCK_MODE=true).
- `make_weather_tool(client)`: real current conditions + daily forecast from Open-Meteo.

HTTP details live in app/providers/open_meteo.py; this module only shapes what the planner
and the synthesizer see.
"""

import hashlib
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.providers.errors import ProviderError
from app.providers.open_meteo import MAX_FORECAST_DAYS, OpenMeteoClient
from app.tools.base import Tool, ToolFailure, ToolInput
from app.tools.provider_errors import as_tool_failure

_CONDITIONS = ["Sunny", "Partly cloudy", "Cloudy", "Light rain", "Thunderstorms", "Windy"]


class WeatherInput(ToolInput):
    city: str = Field(min_length=1, max_length=100, description="City name, e.g. 'Singapore' or 'Paris, FR'.")
    unit: Literal["celsius", "fahrenheit"] = Field(default="celsius", description="Temperature unit.")


class WeatherOutput(BaseModel):
    city: str
    temperature: float
    unit: Literal["celsius", "fahrenheit"]
    condition: str
    humidity_percent: int
    observed_at: datetime
    mocked: Literal[True] = True
    source: str = "mock"


async def _get_weather(args: WeatherInput) -> WeatherOutput:
    # Seed from the city name so the same city always gets the same fake weather (stable tests, believable demos).
    seed = int(hashlib.sha256(args.city.lower().encode()).hexdigest(), 16)
    celsius = 5 + seed % 30
    temperature = celsius if args.unit == "celsius" else round(celsius * 9 / 5 + 32, 1)
    return WeatherOutput(
        city=args.city,
        temperature=temperature,
        unit=args.unit,
        condition=_CONDITIONS[seed % len(_CONDITIONS)],
        humidity_percent=40 + seed % 50,
        observed_at=datetime.now(UTC),
    )


weather_tool = Tool(
    name="get_weather",
    description="Get the current weather for a city.",
    input_model=WeatherInput,
    output_model=WeatherOutput,
    handler=_get_weather,
    mocked=True,
)


# --- real: Open-Meteo -----------------------------------------------------------------------

# WMO weather interpretation codes, as documented by Open-Meteo.
WMO_CODES: dict[int, str] = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light rain showers", 81: "Rain showers", 82: "Violent rain showers", 85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}  # fmt: skip


class ForecastInput(ToolInput):
    location: str = Field(
        min_length=1, max_length=100, description="Place name, optionally with country or region: 'Singapore', 'Paris, France'."
    )
    start_date: date | None = Field(default=None, description="First day (YYYY-MM-DD). Omit for current conditions only.")
    end_date: date | None = Field(default=None, description="Last day, inclusive (YYYY-MM-DD). Defaults to start_date.")
    unit: Literal["celsius", "fahrenheit"] = "celsius"

    @model_validator(mode="after")
    def _check_dates(self) -> "ForecastInput":
        if self.end_date and not self.start_date:
            raise ValueError("end_date requires start_date")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class Place(BaseModel):
    name: str
    region: str | None
    country: str | None
    latitude: float
    longitude: float
    timezone: str | None


class CurrentConditions(BaseModel):
    time: str
    condition: str
    temperature: float | None
    feels_like: float | None
    humidity_percent: float | None
    precipitation: float | None
    wind_speed: float | None


class DailyForecast(BaseModel):
    date: str
    condition: str
    temperature_max: float | None
    temperature_min: float | None
    precipitation_probability_percent: float | None
    precipitation_total: float | None


class ForecastOutput(BaseModel):
    location: Place
    units: dict[str, str]
    current: CurrentConditions | None
    daily: list[DailyForecast]
    source: str = "open-meteo"
    mocked: bool = False


def make_weather_tool(
    client: OpenMeteoClient, *, today: Callable[[], date] = date.today, timeout_seconds: float | None = None
) -> Tool[ForecastInput, ForecastOutput]:
    async def get_forecast(args: ForecastInput) -> ForecastOutput:
        start = args.start_date
        end = args.end_date or start
        if start:
            last = today() + timedelta(days=MAX_FORECAST_DAYS - 1)
            if start < today() or end > last:  # type: ignore[operator]
                raise ToolFailure(
                    "invalid_arguments",
                    f"Forecasts are available from {today().isoformat()} to {last.isoformat()}.",
                )
        try:
            place = await client.geocode(args.location)
            data = await client.forecast(place, start=start, end=end, fahrenheit=args.unit == "fahrenheit")
        except ProviderError as exc:
            raise as_tool_failure(exc) from exc
        include_current = start is None or start <= today() <= end  # type: ignore[operator]
        return _normalize(place, data, include_current)

    return Tool(
        name="get_weather",
        description="Current conditions and/or the daily forecast (today up to 16 days ahead) for a place.",
        input_model=ForecastInput,
        output_model=ForecastOutput,
        handler=get_forecast,
        timeout_seconds=timeout_seconds,
    )


def _normalize(place, data: dict, include_current: bool) -> ForecastOutput:  # type: ignore[no-untyped-def]
    current_raw, current_units = data.get("current") or {}, data.get("current_units") or {}
    daily_raw = data.get("daily") or {}
    days = daily_raw.get("time") or []

    def column(name: str) -> list:  # type: ignore[type-arg]
        values = daily_raw.get(name) or []
        return values + [None] * (len(days) - len(values))

    daily = [
        DailyForecast(
            date=day,
            condition=WMO_CODES.get(code, "Unknown") if code is not None else "Unknown",
            temperature_max=tmax,
            temperature_min=tmin,
            precipitation_probability_percent=prob,
            precipitation_total=total,
        )
        for day, code, tmax, tmin, prob, total in zip(
            days,
            column("weather_code"),
            column("temperature_2m_max"),
            column("temperature_2m_min"),
            column("precipitation_probability_max"),
            column("precipitation_sum"),
            strict=True,
        )
    ]
    current = None
    if include_current and current_raw:
        code = current_raw.get("weather_code")
        current = CurrentConditions(
            time=str(current_raw.get("time", "")),
            condition=WMO_CODES.get(code, "Unknown") if code is not None else "Unknown",
            temperature=current_raw.get("temperature_2m"),
            feels_like=current_raw.get("apparent_temperature"),
            humidity_percent=current_raw.get("relative_humidity_2m"),
            precipitation=current_raw.get("precipitation"),
            wind_speed=current_raw.get("wind_speed_10m"),
        )
    units = {
        "temperature": current_units.get("temperature_2m") or (data.get("daily_units") or {}).get("temperature_2m_max", "°C"),
        "wind_speed": current_units.get("wind_speed_10m", "km/h"),
        "precipitation": (data.get("daily_units") or {}).get("precipitation_sum", "mm"),
    }
    return ForecastOutput(
        location=Place(
            name=place.name,
            region=place.admin1,
            country=place.country,
            latitude=place.latitude,
            longitude=place.longitude,
            timezone=data.get("timezone") or place.timezone,
        ),
        units=units,
        current=current,
        daily=daily,
    )
