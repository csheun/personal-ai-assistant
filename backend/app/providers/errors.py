from typing import Literal

ProviderErrorKind = Literal[
    "not_found",
    "timeout",
    "rate_limited",
    "auth",
    "unavailable",
    "bad_response",
    "bad_request",
    # The request may have reached the provider, but no confirmation came back. For actions
    # (sending a message) this means "maybe done": callers must not retry blindly.
    "uncertain",
]


class ProviderError(Exception):
    """A provider call failed. `message` is safe to show; raw responses are only logged."""

    def __init__(self, provider: str, kind: ProviderErrorKind, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.kind = kind
        self.message = message
