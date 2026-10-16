
import json
import os
import time
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.getenv("MODEL_API_KEY"))
MODEL = "openai/gpt-oss-120b"
MAX_STEPS = 5


# Mock tools
def get_weather(city: str) -> dict:
    return {
        "city": city,
        "temperature_c": 30,
        "condition": "Cloudy",
        "source": "mock"
    }


def get_calendar(date: str) -> dict:
    return {
        "date": date,
        "events": [
            {"title": "Team meeting", "time": "10:00"},
            {"title": "Gym", "time": "18:00"}
        ],
        "source": "mock"
    }


# Explicit dispatch registry
TOOL_REGISTRY = {
    "get_weather": get_weather,
    "get_calendar": get_calendar
}


# Tool schemas
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather information for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"}
                },
                "required": ["city"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar",
            "description": "Get calendar events for a date in YYYY-MM-DD format.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"}
                },
                "required": ["date"],
                "additionalProperties": False
            }
        }
    }
]


def execute_tool(name: str, args: dict) -> dict:
    if name not in TOOL_REGISTRY:
        return {"error": "Unknown tool"}

    try:
        return TOOL_REGISTRY[name](**args)

    except (ValueError, TypeError, KeyError) as exc:
        return {
            "error": "Invalid tool arguments",
            "details": str(exc)
        }


def chat(user_message: str):
    messages = [
        {"role": "user", "content": user_message}
    ]

    total_input_tokens = 0
    total_output_tokens = 0

    start = time.perf_counter()

    for step in range(MAX_STEPS):

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )

        if response.usage:
            total_input_tokens += response.usage.prompt_tokens or 0
            total_output_tokens += response.usage.completion_tokens or 0

        if not response.choices:
            raise RuntimeError("Model returned no content")

        # Preserve the model's complete response.
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        tool_calls = message.tool_calls or []

        # No tools requested: final response.
        if not tool_calls:
            elapsed = time.perf_counter() - start

            print("\nAssistant:")
            print(message.content)

            print("\nMetrics:")
            print("Input tokens:", total_input_tokens)
            print("Output tokens:", total_output_tokens)
            print(f"Latency: {elapsed:.2f}s")
            return

        # Execute all requested tools.
        for call in tool_calls:
            print(f"\nExecuting tool: {call.function.name}")
            print(f"Arguments: {call.function.arguments}")

            # Groq returns arguments as a JSON string.
            try:
                args = json.loads(call.function.arguments or "{}")
                result = execute_tool(call.function.name, args)
            except json.JSONDecodeError as exc:
                result = {
                    "error": "Invalid tool arguments",
                    "details": str(exc)
                }

            # Return tool results to the model.
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result)
            })

    raise RuntimeError("Maximum tool steps exceeded")


if __name__ == "__main__":
    chat(
        "Check the weather in Singapore and "
        "my calendar for 2026-10-16. "
        "Give me a short morning briefing."
    )
