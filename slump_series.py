"""スランプ時系列の連結・平均化ロジック。

日を跨いだ差枚の平行移動連結（chain_days）と、時刻バケット平均
（average_series）を提供する。plot_slump.py から import して使う。

実行:
    単体では実行しない。グラフ生成は python plot_slump.py
    テストは python -m unittest tests.test_slump_series
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    JST = ZoneInfo("Asia/Tokyo")
except ZoneInfoNotFoundError:
    JST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class SlumpSample:
    sampled_at: datetime
    slump_value: int


@dataclass(frozen=True)
class ChainedSample:
    data_date: date
    sampled_at: datetime
    original_value: int
    chained_value: int
    hours_from_origin: float
    is_day_start: bool


def to_jst(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(JST)


def parse_timestamptz(value: str) -> datetime:
    return to_jst(datetime.fromisoformat(value.replace("Z", "+00:00")))


def chain_days(
    days: Iterable[tuple[date, list[SlumpSample]]],
) -> list[ChainedSample]:
    """古い日から順に、当日の終点が翌日の始点になるよう平行移動して連結する。"""
    result: list[ChainedSample] = []
    x_cursor = 0.0
    offset = 0
    started = False

    for data_date, samples in days:
        if not samples:
            continue
        ordered = sorted(samples, key=lambda sample: sample.sampled_at)
        first_ts = ordered[0].sampled_at
        shift = (offset - ordered[0].slump_value) if started else 0

        for index, sample in enumerate(ordered):
            hours = (sample.sampled_at - first_ts).total_seconds() / 3600.0
            chained = sample.slump_value + shift
            result.append(
                ChainedSample(
                    data_date=data_date,
                    sampled_at=sample.sampled_at,
                    original_value=sample.slump_value,
                    chained_value=chained,
                    hours_from_origin=x_cursor + hours,
                    is_day_start=index == 0,
                )
            )

        offset = result[-1].chained_value
        x_cursor = result[-1].hours_from_origin
        started = True

    return result


def average_series(
    series_by_machine: dict[object, list[SlumpSample]],
    bucket_minutes: int = 20,
    min_machines: int = 3,
) -> list[SlumpSample]:
    """時刻バケットごとに、各台の直近値を前進補完して平均する。"""
    populated = {
        key: sorted(samples, key=lambda sample: sample.sampled_at)
        for key, samples in series_by_machine.items()
        if samples
    }
    if not populated:
        return []

    all_ts = [
        sample.sampled_at
        for samples in populated.values()
        for sample in samples
    ]
    start = min(all_ts)
    aligned_minute = (start.minute // bucket_minutes) * bucket_minutes
    start = start.replace(minute=aligned_minute, second=0, microsecond=0)
    end = max(all_ts)
    step = timedelta(minutes=bucket_minutes)

    buckets: list[datetime] = []
    cursor = start
    while cursor <= end + step:
        buckets.append(cursor)
        cursor += step

    last: dict[object, int] = {}
    index_by_key = {key: 0 for key in populated}
    averaged: list[SlumpSample] = []

    for bucket in buckets:
        for key, samples in populated.items():
            index = index_by_key[key]
            while index < len(samples) and samples[index].sampled_at <= bucket:
                last[key] = samples[index].slump_value
                index += 1
            index_by_key[key] = index
        if len(last) >= min_machines:
            averaged.append(
                SlumpSample(
                    sampled_at=bucket,
                    slump_value=int(round(mean(last.values()))),
                )
            )

    return averaged
