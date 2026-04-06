"""Alert dispatcher: fans a single alert out to all enabled delivery channels."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class AlertDispatcher:
    """Sends an alert to one or more channels and records delivery logs.

    Parameters
    ----------
    repository:
        Any repository exposing ``record_delivery_log`` and
        ``get_delivery_logs``.
    send_webhook:
        Callable ``(url: str, payload: dict) -> None``.  Pass ``None`` to
        disable the webhook channel entirely.
    send_email:
        Callable ``(payload: dict) -> None``.  Pass ``None`` to disable the
        email channel entirely.
    """

    def __init__(
        self,
        *,
        repository: Any,
        send_webhook: Callable[[str, dict], None] | None = None,
        send_email: Callable[[dict], None] | None = None,
    ) -> None:
        self._repo = repository
        self._send_webhook = send_webhook
        self._send_email = send_email

    def dispatch(
        self,
        *,
        alert_id: int,
        alert_payload: dict,
        channels: dict[str, Any],
    ) -> None:
        """Fan *alert_payload* out to every channel in *channels*.

        ``channels`` is a mapping from channel name to channel-specific
        configuration:
        - ``"webhook"``: the target URL string
        - ``"email"``: ``True`` (uses the injected sender as-is)

        A delivery log row is written for every channel regardless of outcome.
        """
        for channel, config in channels.items():
            status = "sent"
            try:
                if channel == "webhook" and self._send_webhook is not None:
                    url = str(config)
                    self._send_webhook(url, alert_payload)
                elif channel == "email" and self._send_email is not None:
                    self._send_email(alert_payload)
                elif channel not in ("webhook", "email"):
                    raise ValueError(f"Unknown channel: {channel!r}")
            except Exception:
                status = "failed"

            self._repo.record_delivery_log(
                alert_id=alert_id,
                channel=channel,
                status=status,
            )
