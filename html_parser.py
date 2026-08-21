"""台詳細HTMLから日次サマリ・大当たり・スランプ等を抽出する（DB非依存）。

parse_html_file() が入口。unit_mapping.csv で machine_id を解決し、
scripts/db/ingest_html.py がこの結果を Supabase へ投入する。

実行:
    単体では実行しない。解析・投入は python scripts/db/ingest_html.py
    ローカル確認は python scripts/db/ingest_html.py --dry-run
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from machine_master import normalize_model, resolve_assignment


JST = ZoneInfo("Asia/Tokyo")
DATE_DIR_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STORE_ID_PATTERN = re.compile(r"daidata\.goraggio\.com/(\d+)/")
UNIT_PATTERN = re.compile(r"(\d+)番台")
PLAY_RATE_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)円")
FULL_DATETIME_PATTERN = re.compile(r"(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2})")
MONTH_DAY_PATTERN = re.compile(r"(\d{1,2})月(\d{1,2})日")
POINT_PATTERN = re.compile(
    r'\["(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",\s*(-?\d+)\]'
)


@dataclass
class DailySummary:
    data_date: date
    bb_count: Optional[int] = None
    rb_count: Optional[int] = None
    art_count: Optional[int] = None
    current_start: Optional[int] = None
    max_hold: Optional[int] = None
    total_start: Optional[int] = None
    prev_day_final_start: Optional[int] = None
    combined_prob_denominator: Optional[float] = None
    bb_prob_denominator: Optional[float] = None
    rb_prob_denominator: Optional[float] = None
    art_prob_denominator: Optional[float] = None
    source_updated_at: Optional[datetime] = None
    source_kind: str = "primary"


@dataclass
class JackpotEvent:
    data_date: date
    event_seq: int
    source_row_order: int
    jackpot_no: Optional[int]
    start_count: Optional[int]
    payout: Optional[int]
    event_type: str
    event_time: Optional[time]
    event_at: Optional[datetime]


@dataclass
class SlumpPoint:
    data_date: date
    point_seq: int
    sampled_at: datetime
    slump_value: int


@dataclass
class StoreSnapshot:
    snapshot_date: date
    pachinko_count: Optional[int]
    slot_count: Optional[int]
    observed_at: datetime


@dataclass
class ParsedPage:
    source_system: str
    source_store_id: str
    store_name: str
    machine_code: str
    source_model_name: str
    machine_type: str
    unit_number: int
    play_rate_yen: Optional[float]
    guide_url: Optional[str]
    requested_data_date: date
    source_url: str
    fetched_at: datetime
    source_updated_at: Optional[datetime]
    content_hash: str
    primary_summary: DailySummary
    related_summaries: list[DailySummary] = field(default_factory=list)
    jackpot_events: list[JackpotEvent] = field(default_factory=list)
    slump_points: list[SlumpPoint] = field(default_factory=list)
    store_snapshot: Optional[StoreSnapshot] = None

    def debug_dict(self) -> dict[str, Any]:
        def normalize(v):
            if isinstance(v, (date, datetime, time)):
                return v.isoformat()
            if isinstance(v, list):
                return [normalize(x) for x in v]
            if hasattr(v, "__dataclass_fields__"):
                return {k: normalize(val) for k, val in asdict(v).items()}
            return v

        return {k: normalize(v) for k, v in self.__dict__.items()}


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _int_or_none(value: str):
    value = (value or "").strip().replace(",", "")
    if not value or value in {"-", "--"}:
        return None
    try:
        return int(value)
    except ValueError:
        try:
            return int(float(value))
        except ValueError:
            return None


def _float_or_none(value: str):
    value = (value or "").strip().replace(",", "")
    if not value or value in {"-", "--"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_full_datetime(value: str) -> Optional[datetime]:
    match = FULL_DATETIME_PATTERN.search(value or "")
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y.%m.%d %H:%M").replace(tzinfo=JST)


def _date_from_month_day(month: int, day: int, reference: date) -> date:
    year = reference.year
    # 年跨ぎ: 1月のページに12月データが出ている場合。
    if reference.month == 1 and month == 12:
        year -= 1
    return date(year, month, day)


def _detect_requested_date(path: Path, soup: BeautifulSoup, html: str, override: Optional[date], source_updated_at):
    if override:
        return override

    if DATE_DIR_PATTERN.match(path.parent.name):
        return date.fromisoformat(path.parent.name)

    heading = None
    for h3 in soup.select("h3.detailTi"):
        text = _text(h3)
        if "大当たり履歴詳細" in text:
            heading = text
            break
    if heading:
        md = MONTH_DAY_PATTERN.search(heading)
        if md:
            reference = source_updated_at.date() if source_updated_at else datetime.now(JST).date()
            return _date_from_month_day(int(md.group(1)), int(md.group(2)), reference)

    decoded = unquote(html)
    candidates = re.findall(r"target_date=(\d{4}-\d{2}-\d{2})", decoded)
    if candidates:
        # current target is typically the latest date present in the page URL/ads.
        return max(date.fromisoformat(x) for x in candidates)

    raise ValueError(
        f"対象日を特定できません: {path}. raw日付フォルダに置くか --data-date を指定してください。"
    )


def _detect_store_id(path: Path, html: str) -> str:
    # data/raw/{source_store_id}/{date}/{unit}.html
    if DATE_DIR_PATTERN.match(path.parent.name) and path.parent.parent.name.isdigit():
        return path.parent.parent.name
    match = STORE_ID_PATTERN.search(html)
    if not match:
        raise ValueError(f"store_idを特定できません: {path}")
    return match.group(1)


def _detect_unit(path: Path, soup: BeautifulSoup) -> int:
    if path.stem.isdigit():
        return int(path.stem)
    title = _text(soup.select_one("#pachinkoTi"))
    match = UNIT_PATTERN.search(title)
    if not match:
        raise ValueError(f"台番号を特定できません: {path}")
    return int(match.group(1))


def _parse_play_rate(soup: BeautifulSoup) -> Optional[float]:
    title = _text(soup.select_one("#pachinkoTi"))
    match = PLAY_RATE_PATTERN.search(title)
    return float(match.group(1)) if match else None


def _parse_overview(scope, data_date: date, source_updated_at=None, source_kind="primary") -> DailySummary:
    summary = DailySummary(
        data_date=data_date,
        source_updated_at=source_updated_at,
        source_kind=source_kind,
    )

    table = scope.select_one("table.overviewTable, table.overviewTable2")
    if table:
        headers = [_text(x) for x in table.select("tr:first-child th")]
        rows = table.select("tr")
        values = [_text(x) for x in rows[1].select("td")] if len(rows) >= 2 else []
        for key, value in zip(headers, values):
            if key == "BB":
                summary.bb_count = _int_or_none(value)
            elif key == "RB":
                summary.rb_count = _int_or_none(value)
            elif key == "ART":
                summary.art_count = _int_or_none(value)
            elif key == "スタート回数":
                summary.current_start = _int_or_none(value)

    table3 = scope.select_one("table.overviewTable3")
    if table3:
        for tr in table3.select("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            i = 0
            while i + 1 < len(cells):
                if cells[i].name == "th" and cells[i + 1].name == "td":
                    key = _text(cells[i])
                    value = _text(cells[i + 1])
                    if key == "最大持ち玉":
                        summary.max_hold = _int_or_none(value)
                    elif key == "累計スタート":
                        summary.total_start = _int_or_none(value)
                    elif key == "前日最終スタート":
                        summary.prev_day_final_start = _int_or_none(value)
                    elif key == "合成確率":
                        summary.combined_prob_denominator = _float_or_none(value)
                    elif key == "BB確率":
                        summary.bb_prob_denominator = _float_or_none(value)
                    elif key == "RB確率":
                        summary.rb_prob_denominator = _float_or_none(value)
                    elif key == "ART確率":
                        summary.art_prob_denominator = _float_or_none(value)
                    i += 2
                else:
                    i += 1
    return summary


def _parse_related_summaries(soup: BeautifulSoup, requested_date: date) -> list[DailySummary]:
    result = []
    for item in soup.select(".unit-item"):
        h4 = item.select_one("h4")
        h4_text = _text(h4)
        md = MONTH_DAY_PATTERN.search(h4_text)
        if not md:
            continue
        updated = _parse_full_datetime(h4_text)
        reference = updated.date() if updated else requested_date
        data_date = _date_from_month_day(int(md.group(1)), int(md.group(2)), reference)
        result.append(
            _parse_overview(
                item,
                data_date=data_date,
                source_updated_at=updated,
                source_kind="history_card",
            )
        )
    return result


def _parse_jackpot_events(soup: BeautifulSoup, data_date: date) -> list[JackpotEvent]:
    table = None
    for section in soup.select("section.numericValue"):
        if "大当たり履歴詳細" in _text(section.select_one("h3.detailTi")):
            table = section.select_one("table.numericValueTable")
            break
    if not table:
        return []

    raw_rows = []
    rows = table.select("tr")
    for source_row_order, tr in enumerate(rows[1:], start=1):
        tds = tr.select("td")
        if len(tds) < 5:
            continue
        event_time = None
        try:
            event_time = datetime.strptime(_text(tds[4]), "%H:%M").time()
        except ValueError:
            pass
        raw_rows.append(
            {
                "source_row_order": source_row_order,
                "jackpot_no": _int_or_none(_text(tds[0])),
                "start_count": _int_or_none(_text(tds[1])),
                "payout": _int_or_none(_text(tds[2])),
                "event_type": _text(tds[3]),
                "event_time": event_time,
            }
        )

    # HTMLは新しいイベントが上。古い順に採番してevent_seqをリアルタイム更新でも安定させる。
    events = []
    for seq, row in enumerate(reversed(raw_rows), start=1):
        event_at = None
        if row["event_time"]:
            event_at = datetime.combine(data_date, row["event_time"], tzinfo=JST)
        events.append(
            JackpotEvent(
                data_date=data_date,
                event_seq=seq,
                source_row_order=row["source_row_order"],
                jackpot_no=row["jackpot_no"],
                start_count=row["start_count"],
                payout=row["payout"],
                event_type=row["event_type"],
                event_time=row["event_time"],
                event_at=event_at,
            )
        )
    return events


def _parse_slump_points(soup: BeautifulSoup) -> list[SlumpPoint]:
    points = []
    for graph in soup.select('[data-slamp-graph-date]'):
        date_str = graph.get("data-slamp-graph-date")
        try:
            data_date = date.fromisoformat(date_str)
        except (TypeError, ValueError):
            continue
        script = graph.find("script", attrs={"data-plot-graph-script": True})
        if not script:
            continue
        pairs = POINT_PATTERN.findall(script.get_text())
        seq = 0
        for ts, value in pairs:
            sampled_at = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
            if sampled_at.date() != data_date:
                continue
            seq += 1
            points.append(
                SlumpPoint(
                    data_date=data_date,
                    point_seq=seq,
                    sampled_at=sampled_at,
                    slump_value=int(value),
                )
            )
    return points


def _parse_store_snapshot(soup: BeautifulSoup, observed_at: datetime) -> StoreSnapshot:
    def count(selector):
        text = _text(soup.select_one(selector))
        m = re.search(r"\|\s*([0-9,]+)台", text)
        return int(m.group(1).replace(",", "")) if m else None

    return StoreSnapshot(
        snapshot_date=observed_at.astimezone(JST).date(),
        pachinko_count=count("nav.pachinko h2"),
        slot_count=count("nav.slot h2"),
        observed_at=observed_at,
    )


def parse_html_file(
    html_path: Path,
    assignments,
    requested_data_date: Optional[date] = None,
    source_system="daidata",
) -> ParsedPage:
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

    source_updated_at = _parse_full_datetime(_text(soup.select_one("#contentsHeader .supple time")))
    requested_data_date = _detect_requested_date(
        html_path, soup, html, requested_data_date, source_updated_at
    )
    source_store_id = _detect_store_id(html_path, html)
    unit = _detect_unit(html_path, soup)

    assignment = resolve_assignment(
        assignments,
        source_store_id,
        unit,
        requested_data_date,
        source_system=source_system,
    )
    if assignment is None:
        raise ValueError(
            f"台マスタに該当なし: {requested_data_date} store={source_store_id} unit={unit}"
        )

    source_model_name = _text(soup.select_one("#pachinkoTi strong"))
    if normalize_model(source_model_name) != normalize_model(assignment.model):
        raise ValueError(
            f"機種名不一致: machine={assignment.machine_id}, unit={unit}, "
            f"expected={assignment.model!r}, actual={source_model_name!r}"
        )

    store_name = re.sub(r"\s*（.*$", "", _text(soup.select_one("#shopInfo dt"))).strip()
    machine_type = _text(soup.select_one("#contentsHeader .type")).lower() or assignment.machine_type
    guide = soup.select_one("#pachinkoTi a[href]")
    guide_url = guide.get("href") if guide else None
    play_rate_yen = _parse_play_rate(soup)

    # rawファイルのmtimeを取得時刻のフォールバックとして使用する。
    fetched_at = datetime.fromtimestamp(html_path.stat().st_mtime, tz=timezone.utc)

    source_url = (
        f"https://daidata.goraggio.com/{source_store_id}/detail"
        f"?unit={unit}&target_date={requested_data_date.isoformat()}"
    )

    overview = soup.select_one("section.overview")
    if not overview:
        raise ValueError(f"日次サマリ section.overview がありません: {html_path}")
    primary_summary = _parse_overview(
        overview,
        data_date=requested_data_date,
        source_updated_at=source_updated_at,
        source_kind="primary",
    )

    related_summaries = _parse_related_summaries(soup, requested_data_date)
    jackpot_events = _parse_jackpot_events(soup, requested_data_date)

    # グラフはHTML内に複数日含まれる。台マスタ上で同じ実台が同じunitにいた日だけ採用する。
    slump_points = []
    for point in _parse_slump_points(soup):
        related_assignment = resolve_assignment(
            assignments,
            source_store_id,
            unit,
            point.data_date,
            source_system=source_system,
        )
        if related_assignment and related_assignment.machine_id == assignment.machine_id:
            slump_points.append(point)

    filtered_related = []
    for summary in related_summaries:
        related_assignment = resolve_assignment(
            assignments,
            source_store_id,
            unit,
            summary.data_date,
            source_system=source_system,
        )
        if related_assignment and related_assignment.machine_id == assignment.machine_id:
            filtered_related.append(summary)

    observed_at = source_updated_at or fetched_at.astimezone(JST)
    store_snapshot = _parse_store_snapshot(soup, observed_at)

    return ParsedPage(
        source_system=source_system,
        source_store_id=source_store_id,
        store_name=store_name,
        machine_code=assignment.machine_id,
        source_model_name=source_model_name,
        machine_type=machine_type,
        unit_number=unit,
        play_rate_yen=play_rate_yen,
        guide_url=guide_url,
        requested_data_date=requested_data_date,
        source_url=source_url,
        fetched_at=fetched_at,
        source_updated_at=source_updated_at,
        content_hash=content_hash,
        primary_summary=primary_summary,
        related_summaries=filtered_related,
        jackpot_events=jackpot_events,
        slump_points=slump_points,
        store_snapshot=store_snapshot,
    )
