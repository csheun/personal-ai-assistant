import asyncio

import pytest
from pydantic import BaseModel

from app.tools import Tool, ToolInput, ToolRegistry, build_default_registry


@pytest.fixture
def registry() -> ToolRegistry:
    return build_default_registry()


async def test_weather_returns_validated_mocked_output(registry: ToolRegistry) -> None:
    result = await registry.execute("get_weather", {"city": "Singapore"})

    assert result.ok and result.error is None
    assert result.mocked is True
    assert result.output["city"] == "Singapore"
    assert result.output["unit"] == "celsius"
    assert result.output["mocked"] is True


async def test_weather_is_deterministic_per_city(registry: ToolRegistry) -> None:
    first = await registry.execute("get_weather", {"city": "Paris"})
    second = await registry.execute("get_weather", {"city": "paris"})
    assert first.output["temperature"] == second.output["temperature"]


async def test_web_search_respects_max_results(registry: ToolRegistry) -> None:
    result = await registry.execute("web_search", {"query": "langgraph", "max_results": 2})

    assert result.ok
    assert len(result.output["results"]) == 2
    assert result.output["mocked"] is True


async def test_defaults_are_applied_and_reported(registry: ToolRegistry) -> None:
    result = await registry.execute("web_search", {"query": "  fastapi  "})
    # Arguments in the result are the *validated* ones (stripped, defaults filled).
    assert result.arguments == {"query": "fastapi", "max_results": 3}


async def test_unknown_tool_is_rejected(registry: ToolRegistry) -> None:
    result = await registry.execute("delete_everything", {})
    assert not result.ok
    assert result.error.code == "unknown_tool"


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("get_weather", {}),  # missing required field
        ("get_weather", {"city": ""}),  # empty string
        ("get_weather", {"city": "Paris", "unit": "kelvin"}),  # bad enum
        ("get_weather", {"city": "Paris", "extra": 1}),  # unexpected field
        ("web_search", {"query": "x", "max_results": 50}),  # out of range
        ("web_search", {"query": 123}),  # wrong type
    ],
)
async def test_invalid_arguments_are_rejected_before_execution(
    registry: ToolRegistry, name: str, arguments: dict
) -> None:
    result = await registry.execute(name, arguments)
    assert not result.ok
    assert result.error.code == "invalid_arguments"
    assert result.error.details


class _EchoIn(ToolInput):
    value: str


class _EchoOut(BaseModel):
    value: str


async def test_handler_exception_is_contained_and_not_leaked() -> None:
    async def boom(_: _EchoIn) -> _EchoOut:
        raise RuntimeError("secret internal detail")

    registry = ToolRegistry()
    registry.register(Tool("boom", "fails", _EchoIn, _EchoOut, boom))

    result = await registry.execute("boom", {"value": "x"})
    assert not result.ok
    assert result.error.code == "execution_failed"
    assert "secret" not in result.error.message


async def test_handler_timeout() -> None:
    async def slow(args: _EchoIn) -> _EchoOut:
        await asyncio.sleep(1)
        return _EchoOut(value=args.value)

    registry = ToolRegistry(timeout_seconds=0.01)
    registry.register(Tool("slow", "slow", _EchoIn, _EchoOut, slow))

    result = await registry.execute("slow", {"value": "x"})
    assert result.error.code == "timeout"


def test_filtered_registry_drops_side_effect_tools(registry: ToolRegistry) -> None:
    safe = registry.filtered(lambda tool: not tool.side_effects)
    assert "telegram_send_message" in registry.names
    assert "telegram_send_message" not in safe.names
    assert "get_weather" in safe.names


def test_duplicate_registration_fails() -> None:
    registry = build_default_registry()
    with pytest.raises(ValueError):
        registry.register(registry.get("get_weather"))


def test_llm_schemas_mark_mocked_tools(registry: ToolRegistry) -> None:
    schemas = {s["function"]["name"]: s["function"] for s in registry.llm_schemas()}
    assert {"get_weather", "web_search", "summarize", "telegram_send_message"} <= set(schemas)
    assert schemas["get_weather"]["description"].startswith("[MOCKED DATA]")
    assert schemas["get_weather"]["parameters"]["required"] == ["city"]


async def test_expected_failures_keep_their_safe_message() -> None:
    from app.tools import ToolFailure

    async def missing(_: _EchoIn) -> _EchoOut:
        raise ToolFailure("not_found", "Couldn't find a place called 'Atlantis'.")

    registry = ToolRegistry()
    registry.register(Tool("lookup", "x", _EchoIn, _EchoOut, missing))
    result = await registry.execute("lookup", {"value": "x"})
    assert (result.error.code, result.error.message) == ("not_found", "Couldn't find a place called 'Atlantis'.")


async def test_per_tool_timeout_overrides_the_default() -> None:
    async def slow(args: _EchoIn) -> _EchoOut:
        await asyncio.sleep(0.05)
        return _EchoOut(value=args.value)

    registry = ToolRegistry(timeout_seconds=0.01)
    registry.register(Tool("patient", "x", _EchoIn, _EchoOut, slow, timeout_seconds=1.0))
    assert (await registry.execute("patient", {"value": "x"})).ok
