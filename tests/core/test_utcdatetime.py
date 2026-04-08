"""Tests for UTCDateTime TypeDecorator bind-parameter validation."""
from datetime import datetime, timezone, timedelta

import pytest

from radar.core.models import UTCDateTime

_type = UTCDateTime()
_dialect = None  # SQLAlchemy passes dialect; None is fine for unit tests


class TestUTCDatetimeBindParam:
    def test_none_passes_through(self):
        assert _type.process_bind_param(None, _dialect) is None

    def test_utc_aware_datetime_returns_naive_for_storage(self):
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = _type.process_bind_param(dt, _dialect)
        # SQLite stores as naive; we strip tzinfo after confirming UTC
        assert result.tzinfo is None
        assert result == datetime(2024, 1, 15, 12, 0, 0)

    def test_non_utc_aware_datetime_is_normalized_to_utc(self):
        eastern = timezone(timedelta(hours=-5))
        dt = datetime(2024, 1, 15, 7, 0, 0, tzinfo=eastern)  # 12:00 UTC
        result = _type.process_bind_param(dt, _dialect)
        assert result.tzinfo is None
        assert result == datetime(2024, 1, 15, 12, 0, 0)

    def test_naive_datetime_raises_value_error(self):
        naive = datetime(2024, 1, 15, 12, 0, 0)
        with pytest.raises(ValueError, match="naive"):
            _type.process_bind_param(naive, _dialect)
