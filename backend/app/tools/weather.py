"""MOCKED weather tool. Returns deterministic fake data; no external API is called.

Replace `_get_weather` with a real provider (e.g. Open-Meteo) in a later milestone;
the input/output models are the contract and should not need to change.
"""

import hashlib
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolInput

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
