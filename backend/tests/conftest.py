import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every backend test runs with outbound connections disabled.

    The app is exercised in-process (TestClient uses ASGI, not sockets), so any
    connection attempt means some code tried to reach a real external service.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"Network access attempted during tests: {args!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
