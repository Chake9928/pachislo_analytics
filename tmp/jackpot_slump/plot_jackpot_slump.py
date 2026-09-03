"""jackpot_events から差枚スランプを再構成する試作。

通常時のコイン持ち 30G/50枚 を使い、各大当たりの
    消費枚数 = start_count * 50 / 30
    差枚     = payout - 消費枚数
を 1 点として累積し、公式 slump_points と比較する。

対象はお試しのため 1 台。成果物はすべてこのディレクトリ配下へ出力する。

実行:
    python tmp/jackpot_slump/plot_jackpot_slump.py
    python tmp/jackpot_slump/plot_jackpot_slump.py --machine-code M0001
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from machine_master import normalize_model
from slump_series import SlumpSample, chain_days, parse_timestamptz, to_jst
from supabase_client import create_supabase_client


try:
    JST = ZoneInfo("Asia/Tokyo")
except ZoneInfoNotFoundError:
    JST = timezone(timedelta(hours=9))


PAGE_SIZE = 1000
DEFAULT_SOURCE_STORE_ID = 100928
DEFAULT_MODEL = "L ToLOVEるﾀﾞｰｸﾈｽver.8.7"
DEFAULT_MACHINE_CODE = "M0001"
HOLD_GAMES = 30
HOLD_COINS = 50
COINS_PER_GAME = HOLD_COINS / HOLD_GAMES
LINE_COLOR = "#2F5D8A"
DERIVED_COLOR = "#C45C26"
OFFICIAL_COLOR = "#2F5D8A"
ZERO_COLOR = "#888888"

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "out"


def paginate(query):
    rows = []
    start = 0
    while True:
        batch = query.range(start, start + PAGE_SIZE - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE


def configure_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in ("Yu Gothic", "Yu Gothic UI", "Meiryo", "MS Gothic"):
        if name in available:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def parse_event_dt(ev, data_date: date):
    at = ev.get("event_at")
    if at:
        return parse_timestamptz(at) if isinstance(at, str) else to_jst(at)
    et = ev.get("event_time")
    if not et:
        return None
    if isinstance(et, time):
        t = et
    else:
        parts = str(et).split(":")
        t = time(int(parts[0]), int(parts[1]), int(float(parts[2])) if len(parts) > 2 else 0)
    d = date.fromisoformat(data_date) if isinstance(data_date, str) else data_date
    return datetime.combine(d, t, tzinfo=JST)


def write_csv(path: Path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def fetch_target(db, source_store_id: int, model_name: str, machine_code: str):
    stores = (
        db.table("stores")
        .select("store_id,source_store_id,store_name")
        .eq("source_store_id", source_store_id)
        .execute()
        .data
        or []
    )
    if not stores:
        raise SystemExit(f"店舗が見つかりません: source_store_id={source_store_id}")
    store = stores[0]

    models = db.table("models").select("model_id,source_model_name,model_name").execute().data or []
    wanted = normalize_model(model_name)
    model = next(
        (
            row
            for row in models
            if normalize_model(row["source_model_name"]) == wanted
            or normalize_model(row["model_name"]) == wanted
        ),
        None,
    )
    if model is None:
        raise SystemExit(f"機種が見つかりません: {model_name}")

    machines = (
        db.table("machines")
        .select("machine_id,machine_code,model_id")
        .eq("model_id", model["model_id"])
        .order("machine_code")
        .execute()
        .data
        or []
    )
    machine = next((row for row in machines if row["machine_code"] == machine_code), None)
    if machine is None:
        available = ", ".join(row["machine_code"] for row in machines[:20])
        raise SystemExit(f"実台が見つかりません: {machine_code}  例: {available}")

    placements = (
        db.table("machine_placements")
        .select("machine_id,unit_number")
        .eq("store_id", store["store_id"])
        .eq("machine_id", machine["machine_id"])
        .execute()
        .data
        or []
    )
    unit_number = placements[0]["unit_number"] if placements else None

    events = paginate(
        db.table("jackpot_events")
        .select(
            "event_id,machine_id,data_date,unit_number,event_seq,"
            "jackpot_no,start_count,payout,event_type,event_time,event_at"
        )
        .eq("store_id", store["store_id"])
        .eq("machine_id", machine["machine_id"])
        .order("data_date")
        .order("event_seq")
    )
    slump_rows = paginate(
        db.table("slump_points")
        .select("machine_id,data_date,unit_number,sampled_at,slump_value,point_seq")
        .eq("store_id", store["store_id"])
        .eq("machine_id", machine["machine_id"])
        .order("data_date")
        .order("sampled_at")
    )
    summaries = paginate(
        db.table("machine_daily_summaries")
        .select(
            "machine_id,data_date,unit_number,current_start,max_hold,"
            "total_start,bb_count,art_count,observed_at"
        )
        .eq("store_id", store["store_id"])
        .eq("machine_id", machine["machine_id"])
        .order("data_date")
    )
    return store, model, machine, unit_number, events, slump_rows, summaries


def _same_day(ts, data_date: date):
    return ts is not None and to_jst(ts).date() == data_date


def to_naive_jst(dt: datetime) -> datetime:
    return to_jst(dt).replace(tzinfo=None)


def build_day_series(events, summary, official_first_ts, official_last_ts):
    """1日分の差枚系列を作る。

    各大当たりについて
        consumption = start_count * 50 / 30
        delta       = payout - consumption
    を 1 slump_point とし、累積差枚を Y にする。

    折れ線を見やすくするため、同一時刻に
        消費後（大当たり直前）→ 払出後（大当たり直後）
    の2点を置く。閉店残スタートがあれば末尾に消費だけ足す。
    """
    ordered = sorted(events, key=lambda ev: (ev.get("event_seq") or 0, parse_event_dt(ev, ev["data_date"]) or datetime.min.replace(tzinfo=JST)))
    data_date = date.fromisoformat(ordered[0]["data_date"]) if ordered else None
    if data_date is None:
        return [], [], None

    origin_candidates = []
    if _same_day(official_first_ts, data_date):
        origin_candidates.append(to_jst(official_first_ts))
    first_dt = next((parse_event_dt(ev, data_date) for ev in ordered if parse_event_dt(ev, data_date)), None)
    if first_dt is not None:
        origin_candidates.append(first_dt)
    origin = min(origin_candidates) if origin_candidates else datetime.combine(data_date, time(10, 0), tzinfo=JST)

    saw = [
        {
            "kind": "origin",
            "event_seq": None,
            "event_type": None,
            "sampled_at": origin,
            "start_count": 0,
            "payout": 0,
            "consumption": 0.0,
            "delta": 0.0,
            "cum_games": 0,
            "slump_value": 0.0,
        }
    ]
    event_points = []
    cum = 0.0
    cum_games = 0

    for ev in ordered:
        start_count = ev.get("start_count")
        payout = ev.get("payout")
        if start_count is None and payout is None:
            continue
        start_count = int(start_count or 0)
        payout = int(payout or 0)
        consumption = start_count * COINS_PER_GAME
        delta = payout - consumption
        dt = parse_event_dt(ev, data_date) or origin
        cum_games += start_count
        pre = cum - consumption
        post = pre + payout
        saw.append(
            {
                "kind": "pre_payout",
                "event_seq": ev.get("event_seq"),
                "event_type": ev.get("event_type"),
                "sampled_at": dt,
                "start_count": start_count,
                "payout": payout,
                "consumption": consumption,
                "delta": delta,
                "cum_games": cum_games,
                "slump_value": pre,
            }
        )
        saw.append(
            {
                "kind": "post_payout",
                "event_seq": ev.get("event_seq"),
                "event_type": ev.get("event_type"),
                "sampled_at": dt,
                "start_count": start_count,
                "payout": payout,
                "consumption": consumption,
                "delta": delta,
                "cum_games": cum_games,
                "slump_value": post,
            }
        )
        event_points.append(
            {
                "kind": "event_end",
                "event_seq": ev.get("event_seq"),
                "event_type": ev.get("event_type"),
                "jackpot_no": ev.get("jackpot_no"),
                "sampled_at": dt,
                "start_count": start_count,
                "payout": payout,
                "consumption": consumption,
                "delta": delta,
                "cum_games": cum_games,
                "slump_value": post,
                "unit_number": ev.get("unit_number"),
            }
        )
        cum = post

    remaining_start = int(summary["current_start"]) if summary and summary.get("current_start") else 0
    if remaining_start > 0:
        remaining_cons = remaining_start * COINS_PER_GAME
        last_ts = event_points[-1]["sampled_at"] if event_points else origin
        end_candidates = [last_ts + timedelta(minutes=1)]
        if _same_day(official_last_ts, data_date) and official_last_ts > last_ts:
            end_candidates.append(to_jst(official_last_ts))
        day_end = datetime.combine(data_date, time(22, 59), tzinfo=JST)
        end_ts = min(max(end_candidates), day_end)
        if end_ts <= last_ts:
            end_ts = last_ts + timedelta(minutes=1)
        cum_games += remaining_start
        cum -= remaining_cons
        saw.append(
            {
                "kind": "eod_remaining",
                "event_seq": None,
                "event_type": None,
                "sampled_at": end_ts,
                "start_count": remaining_start,
                "payout": 0,
                "consumption": remaining_cons,
                "delta": -remaining_cons,
                "cum_games": cum_games,
                "slump_value": cum,
            }
        )

    return saw, event_points, data_date


def interpolate_at(series, ts):
    """series は sampled_at 昇順。ts 時点の直線補間値。範囲外は端点。"""
    if not series:
        return None
    if ts <= series[0]["sampled_at"]:
        return series[0]["slump_value"]
    if ts >= series[-1]["sampled_at"]:
        return series[-1]["slump_value"]
    for prev, nxt in zip(series, series[1:]):
        if prev["sampled_at"] <= ts <= nxt["sampled_at"]:
            span = (nxt["sampled_at"] - prev["sampled_at"]).total_seconds()
            if span <= 0:
                return nxt["slump_value"]
            ratio = (ts - prev["sampled_at"]).total_seconds() / span
            return prev["slump_value"] + ratio * (nxt["slump_value"] - prev["slump_value"])
    return series[-1]["slump_value"]


def pearson(xs, ys):
    if len(xs) < 3:
        return None
    mx = mean(xs)
    my = mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def compare_day(derived_saw, official):
    if not derived_saw or not official:
        return None
    paired = []
    for sample in official:
        est = interpolate_at(derived_saw, sample["sampled_at"])
        if est is None:
            continue
        paired.append((sample["slump_value"], est))
    if not paired:
        return None
    official_vals = [p[0] for p in paired]
    derived_vals = [p[1] for p in paired]
    errors = [d - o for o, d in paired]
    rmse = math.sqrt(mean(e * e for e in errors))
    return {
        "n_official": len(official),
        "n_derived_events": sum(1 for p in derived_saw if p["kind"] == "post_payout"),
        "n_derived_points": len(derived_saw),
        "official_final": official[-1]["slump_value"],
        "derived_final": derived_saw[-1]["slump_value"],
        "final_diff": derived_saw[-1]["slump_value"] - official[-1]["slump_value"],
        "mae": mean(abs(e) for e in errors),
        "rmse": rmse,
        "mean_error": mean(errors),
        "error_stdev": pstdev(errors) if len(errors) > 1 else 0.0,
        "corr": pearson(official_vals, derived_vals),
        "official_min": min(official_vals),
        "official_max": max(official_vals),
        "derived_min": min(p["slump_value"] for p in derived_saw),
        "derived_max": max(p["slump_value"] for p in derived_saw),
    }


def save_overlay(plt, path, derived, official, title):
    fig, ax = plt.subplots(figsize=(12, 5))
    if derived:
        xs = [to_naive_jst(p["sampled_at"]) for p in derived]
        ax.plot(
            xs,
            [p["slump_value"] for p in derived],
            color=DERIVED_COLOR,
            linewidth=1.4,
            label="jackpot差枚（コイン持ち推定）",
        )
        posts = [p for p in derived if p["kind"] == "post_payout"]
        ax.scatter(
            [to_naive_jst(p["sampled_at"]) for p in posts],
            [p["slump_value"] for p in posts],
            color=DERIVED_COLOR,
            s=12,
            zorder=3,
        )
    if official:
        ax.plot(
            [to_naive_jst(p["sampled_at"]) for p in official],
            [p["slump_value"] for p in official],
            color=OFFICIAL_COLOR,
            linewidth=1.6,
            marker="o",
            markersize=4,
            label="公式 slump_points",
        )
    ax.axhline(0, color=ZERO_COLOR, linewidth=0.8)
    ax.set_title(title)
    ax.set_xlabel("時刻（Asia/Tokyo）")
    ax.set_ylabel("差枚（枚）")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    from matplotlib.dates import DateFormatter

    ax.xaxis.set_major_formatter(DateFormatter("%H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def save_games_axis(plt, path, derived, title):
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        [p["cum_games"] for p in derived],
        [p["slump_value"] for p in derived],
        color=DERIVED_COLOR,
        linewidth=1.4,
    )
    ax.axhline(0, color=ZERO_COLOR, linewidth=0.8)
    ax.set_title(title)
    ax.set_xlabel("累計スタート（G）")
    ax.set_ylabel("差枚（枚）")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def save_chained(plt, path, chained, title):
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        [p.hours_from_origin for p in chained],
        [p.chained_value for p in chained],
        color=DERIVED_COLOR,
        linewidth=1.4,
    )
    ax.axhline(0, color=ZERO_COLOR, linewidth=0.8)
    y_top = max(p.chained_value for p in chained)
    y_bottom = min(p.chained_value for p in chained)
    label_y = y_top if y_top != y_bottom else y_top + 1
    for point in chained:
        if point.is_day_start:
            ax.axvline(point.hours_from_origin, color="#B0B0B0", linestyle="--", linewidth=0.8)
            ax.text(
                point.hours_from_origin,
                label_y,
                point.data_date.strftime("%m/%d"),
                fontsize=8,
                rotation=90,
                va="top",
                ha="right",
                color="#555555",
            )
    ax.set_title(title)
    ax.set_xlabel("連結時間（時間、日を跨いだ隙間は詰める）")
    ax.set_ylabel("連結差枚（枚）")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def save_final_compare(plt, path, rows):
    labels = [row["data_date"][5:] for row in rows]
    official = [row["official_final"] for row in rows]
    derived = [row["derived_final"] for row in rows]
    x = list(range(len(labels)))
    width = 0.4
    fig, ax = plt.subplots(figsize=(12, 4.8))
    ax.bar([i - width / 2 for i in x], official, width=width, color=OFFICIAL_COLOR, label="公式最終スランプ")
    ax.bar([i + width / 2 for i in x], derived, width=width, color=DERIVED_COLOR, label="jackpot差枚 最終")
    ax.axhline(0, color=ZERO_COLOR, linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_title("日次最終差枚の比較")
    ax.set_xlabel("遊技日")
    ax.set_ylabel("最終差枚（枚）")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def pick_zoom_window(derived):
    """同一時刻付近にイベントが集中した区間（AT連チャン想定）を探す。"""
    posts = [p for p in derived if p["kind"] == "post_payout"]
    if len(posts) < 6:
        return None
    best = None
    for i, start in enumerate(posts):
        j = i
        while j + 1 < len(posts) and (posts[j + 1]["sampled_at"] - start["sampled_at"]) <= timedelta(minutes=40):
            j += 1
        count = j - i + 1
        if best is None or count > best[0]:
            best = (count, i, j)
    if best is None or best[0] < 6:
        return None
    _, i, j = best
    t0 = posts[i]["sampled_at"] - timedelta(minutes=10)
    t1 = posts[j]["sampled_at"] + timedelta(minutes=10)
    return t0, t1


def main():
    parser = argparse.ArgumentParser(description="jackpot_events から1台の差枚スランプを試作する")
    parser.add_argument("--source-store-id", type=int, default=DEFAULT_SOURCE_STORE_ID)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--machine-code", default=DEFAULT_MACHINE_CODE)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    plt = configure_matplotlib()
    out_dir = Path(args.out)
    plots_dir = out_dir / "plots"
    series_dir = out_dir / "series"
    out_dir.mkdir(parents=True, exist_ok=True)

    db = create_supabase_client()
    store, model, machine, unit_number, events, slump_rows, summaries = fetch_target(
        db, args.source_store_id, args.model, args.machine_code
    )

    events_by_day = defaultdict(list)
    for ev in events:
        events_by_day[date.fromisoformat(ev["data_date"])].append(ev)
    official_by_day = defaultdict(list)
    for row in slump_rows:
        official_by_day[date.fromisoformat(row["data_date"])].append(
            {
                "sampled_at": parse_timestamptz(row["sampled_at"]),
                "slump_value": int(row["slump_value"]),
                "unit_number": row.get("unit_number"),
            }
        )
    for day in official_by_day:
        official_by_day[day].sort(key=lambda p: p["sampled_at"])
    summary_by_day = {date.fromisoformat(row["data_date"]): row for row in summaries}

    dates = sorted(events_by_day)
    if not dates:
        raise SystemExit("jackpot_events がありません")

    print(f"[STORE] {store['store_name']} source_store_id={store['source_store_id']}", flush=True)
    print(f"[MODEL] {model['source_model_name']} model_id={model['model_id']}", flush=True)
    print(f"[MACHINE] {machine['machine_code']} machine_id={machine['machine_id']} unit={unit_number}", flush=True)
    print(f"[DATES] {dates[0].isoformat()} .. {dates[-1].isoformat()} ({len(dates)}日)", flush=True)
    print(f"[EVENTS] {len(events)}  [OFFICIAL POINTS] {len(slump_rows)}", flush=True)
    print("[PLOT] 差枚スランプを出力しています...", flush=True)

    derived_rows = []
    event_rows = []
    compare_rows = []
    chained_pairs = []
    official_chained_pairs = []
    zoom_saved = False

    for data_date in dates:
        official = official_by_day.get(data_date, [])
        first_official = official[0]["sampled_at"] if official else None
        last_official = official[-1]["sampled_at"] if official else None
        saw, event_points, _ = build_day_series(
            events_by_day[data_date],
            summary_by_day.get(data_date),
            first_official,
            last_official,
        )
        if not saw:
            continue

        unit = event_points[0]["unit_number"] if event_points else (official[0]["unit_number"] if official else unit_number)
        date_label = data_date.isoformat()
        save_overlay(
            plt,
            plots_dir / "daily_overlay" / f"{machine['machine_code']}_{date_label}.png",
            saw,
            official,
            title=(
                f"{machine['machine_code']} / {unit}番  {date_label}  "
                "差枚スランプ（公式 vs jackpot推定）"
            ),
        )
        save_games_axis(
            plt,
            plots_dir / "daily_games" / f"{machine['machine_code']}_{date_label}.png",
            saw,
            title=f"{machine['machine_code']} / {unit}番  {date_label}  差枚スランプ（累計G）",
        )
        if not zoom_saved:
            window = pick_zoom_window(saw)
            if window:
                t0, t1 = window
                zoom_derived = [p for p in saw if t0 <= p["sampled_at"] <= t1]
                zoom_official = [p for p in official if t0 <= p["sampled_at"] <= t1]
                save_overlay(
                    plt,
                    plots_dir / f"zoom_at_burst_{machine['machine_code']}_{date_label}.png",
                    zoom_derived,
                    zoom_official,
                    title=f"{machine['machine_code']}  {date_label}  AT集中区間の拡大",
                )
                zoom_saved = True

        stats = compare_day(saw, official)
        if stats:
            compare_rows.append({"data_date": date_label, "unit_number": unit, **stats})

        chained_pairs.append(
            (
                data_date,
                [
                    SlumpSample(sampled_at=p["sampled_at"], slump_value=int(round(p["slump_value"])))
                    for p in saw
                ],
            )
        )
        if official:
            official_chained_pairs.append(
                (
                    data_date,
                    [
                        SlumpSample(sampled_at=p["sampled_at"], slump_value=p["slump_value"])
                        for p in official
                    ],
                )
            )

        for p in saw:
            derived_rows.append(
                [
                    machine["machine_code"],
                    unit,
                    date_label,
                    p["kind"],
                    p["event_seq"],
                    p["event_type"],
                    p["sampled_at"].isoformat(),
                    p["start_count"],
                    p["payout"],
                    f"{p['consumption']:.4f}",
                    f"{p['delta']:.4f}",
                    p["cum_games"],
                    f"{p['slump_value']:.4f}",
                ]
            )
        for p in event_points:
            event_rows.append(
                [
                    machine["machine_code"],
                    unit,
                    date_label,
                    p["event_seq"],
                    p["event_type"],
                    p.get("jackpot_no"),
                    p["sampled_at"].isoformat(),
                    p["start_count"],
                    p["payout"],
                    f"{p['consumption']:.4f}",
                    f"{p['delta']:.4f}",
                    p["cum_games"],
                    f"{p['slump_value']:.4f}",
                ]
            )

    chained = chain_days(chained_pairs)
    if chained:
        save_chained(
            plt,
            plots_dir / f"chained_{machine['machine_code']}.png",
            chained,
            title=(
                f"{machine['machine_code']} / {unit_number}番  "
                f"連続差枚（jackpot推定、{dates[0].strftime('%m/%d')}起点）"
            ),
        )
    official_chained = chain_days(official_chained_pairs)
    if official_chained:
        save_chained(
            plt,
            plots_dir / f"chained_official_{machine['machine_code']}.png",
            official_chained,
            title=(
                f"{machine['machine_code']} / {unit_number}番  "
                f"連続スランプ（公式、{dates[0].strftime('%m/%d')}起点）"
            ),
        )

    if compare_rows:
        save_final_compare(plt, plots_dir / "daily_final_compare.png", compare_rows)

    write_csv(
        series_dir / "derived_points.csv",
        [
            "machine_code",
            "unit_number",
            "data_date",
            "kind",
            "event_seq",
            "event_type",
            "sampled_at_jst",
            "start_count",
            "payout",
            "consumption",
            "delta",
            "cum_games",
            "slump_value",
        ],
        derived_rows,
    )
    write_csv(
        series_dir / "event_slump_points.csv",
        [
            "machine_code",
            "unit_number",
            "data_date",
            "event_seq",
            "event_type",
            "jackpot_no",
            "sampled_at_jst",
            "start_count",
            "payout",
            "consumption",
            "delta",
            "cum_games",
            "slump_value",
        ],
        event_rows,
    )
    write_csv(
        series_dir / "daily_comparison.csv",
        [
            "data_date",
            "unit_number",
            "n_official",
            "n_derived_events",
            "n_derived_points",
            "official_final",
            "derived_final",
            "final_diff",
            "mae",
            "rmse",
            "mean_error",
            "error_stdev",
            "corr",
            "official_min",
            "official_max",
            "derived_min",
            "derived_max",
        ],
        [
            [
                row["data_date"],
                row["unit_number"],
                row["n_official"],
                row["n_derived_events"],
                row["n_derived_points"],
                f"{row['official_final']:.1f}",
                f"{row['derived_final']:.1f}",
                f"{row['final_diff']:.1f}",
                f"{row['mae']:.1f}",
                f"{row['rmse']:.1f}",
                f"{row['mean_error']:.1f}",
                f"{row['error_stdev']:.1f}",
                "" if row["corr"] is None else f"{row['corr']:.4f}",
                f"{row['official_min']:.1f}",
                f"{row['official_max']:.1f}",
                f"{row['derived_min']:.1f}",
                f"{row['derived_max']:.1f}",
            ]
            for row in compare_rows
        ],
    )

    corr_vals = [row["corr"] for row in compare_rows if row["corr"] is not None]
    summary = {
        "source_store_id": store["source_store_id"],
        "store_name": store["store_name"],
        "model_name": model["source_model_name"],
        "model_id": model["model_id"],
        "machine_code": machine["machine_code"],
        "machine_id": machine["machine_id"],
        "unit_number": unit_number,
        "hold": {"games": HOLD_GAMES, "coins": HOLD_COINS, "coins_per_game": COINS_PER_GAME},
        "formula": "delta = payout - start_count * 50 / 30 ; slump = cumsum(delta)",
        "date_from": dates[0].isoformat(),
        "date_to": dates[-1].isoformat(),
        "n_days": len(dates),
        "n_events": len(events),
        "n_official_points": len(slump_rows),
        "mean_corr": None if not corr_vals else round(mean(corr_vals), 4),
        "mean_final_diff": None if not compare_rows else round(mean(row["final_diff"] for row in compare_rows), 1),
        "mean_rmse": None if not compare_rows else round(mean(row["rmse"] for row in compare_rows), 1),
        "mean_n_official": None if not compare_rows else round(mean(row["n_official"] for row in compare_rows), 1),
        "mean_n_derived_events": None if not compare_rows else round(mean(row["n_derived_events"] for row in compare_rows), 1),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"[OUT] {out_dir}", flush=True)


if __name__ == "__main__":
    main()
