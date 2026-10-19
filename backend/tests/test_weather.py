from datetime import date

import httpx
import pytest

from app.providers.errors import ProviderError
from app.providers.open_meteo import FORECAST_URL, GEOCODING_URL, OpenMeteoClient
from app.tools import ToolRegistry
from app.tools.weather import ForecastInput, make_weather_tool
from tests.http_fakes import FORECAST, PARIS_FR, PARIS_TX, SINGAPORE, fake_http, raises

TODAY = date(2026, 10, 19)


def open_meteo(places: list[dict], forecast: dict = FORECAST, status: int = 200) -> tuple[ToolRegistry, list[httpx.Request]]:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(GEOCODING_URL):
            return httpx.Response(200, json={"results": places} if places else {"generationtime_ms": 0.1})
        return httpx.Response(status, json=forecast if status == 200 else {"error": True, "reason": "Invalid date"})

    http, seen = fake_http(handler)
    registry = ToolRegistry()
    registry.register(make_weather_tool(OpenMeteoClient(http), today=lambda: TODAY))
    return registry, seen


async def test_forecast_for_tomorrow_is_normalized() -> None:
    registry, seen = open_meteo([SINGAPORE])
    result = await registry.execute("get_weather", {"location": "Singapore", "start_date": "2026-10-20"})

    assert result.ok, result.error
    out = result.output
    assert out["location"]["name"] == "Singapore" and out["mocked"] is False
    assert out["daily"] == [
        {"date": "2026-10-20", "condition": "Thunderstorm", "temperature_max": 32.1, "temperature_min": 25.4,
         "precipitation_probability_percent": 80, "precipitation_total": 12.3}
    ]  # fmt: skip
    assert out["current"] is None  # tomorrow only: current conditions aren't relevant
    params = seen[1].url.params
    assert (params["start_date"], params["end_date"], params["latitude"]) == ("2026-10-20", "2026-10-20", "1.29")


async def test_no_dates_gives_current_conditions() -> None:
    registry, seen = open_meteo([SINGAPORE])
    out = (await registry.execute("get_weather", {"location": "Singapore"})).output
    assert out["current"]["condition"] == "Partly cloudy" and out["current"]["temperature"] == 31.2
    assert seen[1].url.params["forecast_days"] == "1"


async def test_country_qualifier_picks_the_right_place() -> None:
    registry, _ = open_meteo([PARIS_TX, PARIS_FR])
    out = (await registry.execute("get_weather", {"location": "Paris, France"})).output
    assert out["location"]["country"] == "France"


async def test_unknown_place_is_not_found() -> None:
    registry, _ = open_meteo([])
    result = await registry.execute("get_weather", {"location": "Atlantis"})
    assert (result.error.code, result.error.message) == ("not_found", "Couldn't find a place called 'Atlantis'.")


async def test_dates_outside_the_forecast_window_are_rejected_before_calling_the_api() -> None:
    registry, seen = open_meteo([SINGAPORE])
    result = await registry.execute("get_weather", {"location": "Singapore", "start_date": "2026-12-01"})
    assert result.error.code == "invalid_arguments" and "2026-11-03" in result.error.message
    assert seen == []


def test_date_range_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="before start_date"):
        ForecastInput(location="x", start_date="2026-10-21", end_date="2026-10-20")
    with pytest.raises(ValueError, match="requires start_date"):
        ForecastInput(location="x", end_date="2026-10-20")


@pytest.mark.parametrize(
    ("handler", "code", "message"),
    [
        (raises(httpx.ReadTimeout("slow")), "timeout", "didn't respond in time"),
        (raises(httpx.ConnectError("refused")), "provider_error", "Couldn't reach"),
        (lambda r: httpx.Response(503, text="down"), "provider_error", "error (503)"),
        (lambda r: httpx.Response(429), "provider_error", "busy"),
        (lambda r: httpx.Response(200, text="<html>not json</html>"), "provider_error", "unexpected data"),
    ],
)
async def test_provider_failures_become_safe_tool_errors(handler, code: str, message: str) -> None:  # type: ignore[no-untyped-def]
    http, _ = fake_http(handler)
    registry = ToolRegistry()
    registry.register(make_weather_tool(OpenMeteoClient(http), today=lambda: TODAY))
    result = await registry.execute("get_weather", {"location": "Singapore"})
    assert not result.ok and result.error.code == code and message in result.error.message


async def test_api_rejection_reason_is_reported() -> None:
    registry, _ = open_meteo([SINGAPORE], status=400)
    result = await registry.execute("get_weather", {"location": "Singapore", "start_date": "2026-10-20"})
    assert result.error.code == "provider_error" and "Invalid date" in result.error.message


async def test_client_raises_typed_errors() -> None:
    http, _ = fake_http(lambda r: httpx.Response(200, json={"results": [{"name": "x"}]}))  # missing coordinates
    with pytest.raises(ProviderError) as caught:
        await OpenMeteoClient(http).geocode("x")
    assert caught.value.kind == "bad_response"
