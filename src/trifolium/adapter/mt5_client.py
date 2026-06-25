"""Connection lifecycle wrapper for the official MetaTrader5 Python package."""

from __future__ import annotations

from contextlib import contextmanager
from types import TracebackType
from typing import Iterator

import MetaTrader5 as mt5

from trifolium.adapter.settings import MT5Settings, load_settings


class MT5ConnectionError(RuntimeError):
    """Raised when MT5 cannot initialize or return required state."""


class MT5Client:
    """Small lifecycle wrapper that initializes and shuts down MT5 explicitly."""

    def __init__(self, settings: MT5Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.initialized = False

    def connect(self) -> None:
        """Initialize MT5 using credentials from environment, never hardcoded."""

        ok = mt5.initialize(
            login=self.settings.login,
            password=self.settings.password,
            server=self.settings.server,
        )
        if not ok:
            code, message = mt5.last_error()
            raise MT5ConnectionError(f"mt5.initialize failed: {code} {message}")
        self.initialized = True

    def shutdown(self) -> None:
        """Close the MT5 connection if it was initialized."""

        if self.initialized:
            mt5.shutdown()
            self.initialized = False

    def __enter__(self) -> "MT5Client":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.shutdown()


@contextmanager
def mt5_session(settings: MT5Settings | None = None) -> Iterator[MT5Client]:
    """Context manager for a bounded MT5 session."""

    client = MT5Client(settings)
    client.connect()
    try:
        yield client
    finally:
        client.shutdown()


def terminal_info() -> dict[str, object]:
    """Return MT5 terminal information as a plain dictionary."""

    info = mt5.terminal_info()
    if info is None:
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"mt5.terminal_info failed: {code} {message}")
    return info._asdict()
