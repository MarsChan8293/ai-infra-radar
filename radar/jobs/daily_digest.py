"""Daily digest job: aggregate recent top alerts and dispatch one summary payload."""
from __future__ import annotations

from typing import Any, Callable


def run_daily_digest_job(
    repository: Any,
    dispatch: Callable[[dict], None],
) -> int:
    """Gather digest candidates, rank by score, and dispatch one summary payload.

    Parameters
    ----------
    repository:
        Must expose ``get_digest_candidates() -> list[Alert]``.
    dispatch:
        Callable that receives the digest payload dict.  In production this is
        wired to ``AlertDispatcher``'s channel senders; in tests it can be any
        callable (e.g. ``list.append``).

    Returns
    -------
    int
        1 if a digest payload was dispatched, 0 if there were no candidates.
    """
    candidates = repository.get_digest_candidates()
    if not candidates:
        return 0

    payload = {
        "type": "daily_digest",
        "count": len(candidates),
        "items": [
            {
                "alert_id": alert.id,
                "alert_type": alert.alert_type,
                "source": alert.source,
                "score": alert.score,
            }
            for alert in candidates
        ],
    }
    dispatch(payload)
    return 1
