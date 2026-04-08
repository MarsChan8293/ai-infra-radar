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
        self._dispatch_channels(
            alert_id=alert_id,
            alert_payload=alert_payload,
            channels=channels,
            idempotency_prefix=str(alert_id),
        )

    def dispatch_raw(
        self,
        *,
        alert_payload: dict,
        channels: dict[str, Any],
        delivery_key_prefix: str,
    ) -> None:
        """Fan a non-alert payload out to every channel and record raw delivery logs."""
        self._dispatch_channels(
            alert_id=None,
            alert_payload=alert_payload,
            channels=channels,
            idempotency_prefix=delivery_key_prefix,
        )

    def _dispatch_channels(
        self,
        *,
        alert_id: int | None,
        alert_payload: dict,
        channels: dict[str, Any],
        idempotency_prefix: str,
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
                if channel == "webhook":
                    if self._send_webhook is None:
                        status = "skipped"
                    else:
                        url = str(config)
                        self._send_webhook(url, alert_payload)
                elif channel == "email":
                    if self._send_email is None:
                        status = "skipped"
                    else:
                        self._send_email(alert_payload)
                else:
                    raise ValueError(f"Unknown channel: {channel!r}")
            except Exception:
                status = "failed"

            self._repo.record_delivery_log(
                alert_id=alert_id,
                channel=channel,
                status=status,
                idempotency_key=f"{idempotency_prefix}:{channel}",
            )
