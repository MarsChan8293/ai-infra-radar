"""Daily digest job: aggregate recent digest items and dispatch one summary payload."""
from __future__ import annotations

from typing import Any, Callable


def run_daily_digest_job(
    repository: Any,
    dispatch: Callable[[dict], None],
) -> int:
    """Gather digest candidate items and dispatch one summary payload.

    Parameters
    ----------
    repository:
        Must expose ``get_digest_candidate_items() -> list[dict]``.
    dispatch:
        Callable that receives the digest payload dict.  In production this is
        wired to ``AlertDispatcher``'s channel senders; in tests it can be any
        callable (e.g. ``list.append``).

    Returns
    -------
    int
        1 if a digest payload was dispatched, 0 if there were no candidates.
    """
    items = repository.get_digest_candidate_items()
    if not items:
        return 0

    payload = {
        "type": "daily_digest",
        "count": len(items),
        "items": items,
    }
    dispatch(payload)
    return 1
