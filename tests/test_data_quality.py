from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from mooc.domain.market import (
    DataSource,
    QuoteQuality,
    is_stale,
    quality_for,
    to_utc,
)

NOW = datetime(2026, 11, 8, 20, 0, tzinfo=UTC)


def test_to_utc_assumes_naive_is_utc():
    naive = datetime(2026, 11, 8, 20, 0)
    assert to_utc(naive) == NOW
    assert to_utc(naive).tzinfo is UTC


def test_to_utc_converts_offsets():
    shifted = datetime(2026, 11, 8, 15, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert to_utc(shifted) == NOW


def test_is_stale_boundaries():
    assert is_stale(NOW - timedelta(seconds=30), now=NOW, max_age_seconds=60) is False
    assert is_stale(NOW - timedelta(seconds=60), now=NOW, max_age_seconds=60) is False
    assert is_stale(NOW - timedelta(seconds=61), now=NOW, max_age_seconds=60) is True


def test_is_stale_rejects_negative_age():
    with pytest.raises(ValueError):
        is_stale(NOW, now=NOW, max_age_seconds=-1)


def test_quality_for_marks_stale_and_missing():
    quality = quality_for(
        DataSource.DELAYED,
        NOW - timedelta(minutes=20),
        now=NOW,
        max_age_seconds=900,
        missing_fields=("bid", "volume"),
    )
    assert quality.source is DataSource.DELAYED
    assert quality.is_stale is True
    assert quality.missing_fields == ("bid", "volume")


def test_quality_for_fresh_is_not_stale():
    quality = quality_for(DataSource.REALTIME, NOW, now=NOW, max_age_seconds=60)
    assert quality.is_stale is False
    assert quality == QuoteQuality(source=DataSource.REALTIME, observed_at=NOW)


def test_historical_is_never_realtime_by_default():
    # Provenance is explicit: a historical value stays historical.
    quality = quality_for(
        DataSource.HISTORICAL, NOW - timedelta(days=1), now=NOW, max_age_seconds=60
    )
    assert quality.source is DataSource.HISTORICAL
    assert quality.source is not DataSource.REALTIME
    assert quality.is_stale is True
