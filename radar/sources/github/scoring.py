"""Burst-signal scoring for GitHub repository search items.

Scores are deterministic floats in [0.0, 1.0] computed from a weighted
log-normalised combination of stargazers and forks counts.
"""
from __future__ import annotations

import math

# Cap values used for log-normalisation; chosen to place common high-activity
# repos clearly above 0.6 while keeping the scale meaningful.
_STAR_CAP = 10_000
_FORK_CAP = 1_000

# Weight attributed to stars vs forks.
_WEIGHT_STARS = 0.7
_WEIGHT_FORKS = 0.3


def score_github_item(item: dict) -> float:
    """Return a burst score in [0.0, 1.0] for *item*.

    The formula is a weighted sum of log-normalised stargazers and forks counts.
    Both components are capped so that extreme outliers do not distort the
    scale for the average-activity repo.
    """
    stars = max(0, item.get("stargazers_count", 0))
    forks = max(0, item.get("forks_count", 0))

    star_score = min(math.log1p(stars) / math.log1p(_STAR_CAP), 1.0)
    fork_score = min(math.log1p(forks) / math.log1p(_FORK_CAP), 1.0)

    return _WEIGHT_STARS * star_score + _WEIGHT_FORKS * fork_score
