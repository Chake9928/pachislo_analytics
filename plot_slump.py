from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

from config import SLUMP_DIR
from machine_master import normalize_model
from slump_series import (
    JST,
    SlumpSample,
    average_series,
    chain_days,
    parse_timestamptz,
)
from supabase_client import create_supabase_client


PAGE_SIZE = 1000
DEFAULT_SOURCE_STORE_ID = 100928
DEFAULT_MODEL = "L ToLOVEるﾀﾞｰｸﾈｽver.8.7"
LINE_COLOR = "#2F5D8A"
AVG_COLOR = "#2B6B5A"
ZERO_COLOR = "#888888"


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


def ensure_dirs(root: Path):
    paths = {
        "daily": root / "01_daily_by_machine",
        "chained": root / "02_chained_by_machine",
        "daily_avg": root / "03_daily_average",
        "chained_avg": root / "04_chained_average",
        "series": root / "series",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def fetch_target(db, source_store_id: int, model_name: str):
    store_resp = (
        db.table("stores")
        .select("store_id,source_store_id,store_name")
        .eq("source_store_id", source_store_id)
        .execute()
    )
    stores = store_resp.data or []
    if not stores:
        raise SystemExit(f"店舗が見つかりません: source_store_id={source_store_id}")
    store = stores[0]

    models = db.table("models").select(
        "model_id,source_model_name,model_name"
    ).execute().data or []
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
    placements = (
        db.table("machine_placements")
        .select("machine_id,unit_number")
        .eq("store_id", store["store_id"])
        .execute()
        .data
        or []
    )
    unit_by_machine = {
        row["machine_id"]: row["unit_number"] for row in placements
    }
    machine_ids = [
        row["machine_id"]
        for row in machines
        if row["machine_id"] in unit_by_machine
    ]
    if not machine_ids:
        raise SystemExit("対象店舗に配置された実台がありません")

    slump_rows = paginate(
        db.table("slump_points")
        .select("machine_id,data_date,unit_number,sampled_at,slump_value")
        .eq("store_id", store["store_id"])
        .in_("machine_id", machine_ids)
        .order("machine_id")
        .order("data_date")
        .order("sampled_at")
    )
    return store, model, machines, unit_by_machine, slump_rows


def group_samples(slump_rows):
    grouped = defaultdict(lambda: defaultdict(list))
    unit_by_day = defaultdict(dict)
    for row in slump_rows:
        machine_id = row["machine_id"]
        data_date = date.fromisoformat(row["data_date"])
        grouped[machine_id][data_date].append(
            SlumpSample(
                sampled_at=parse_timestamptz(row["sampled_at"]),
                slump_value=int(row["slump_value"]),
            )
        )
        unit_by_day[machine_id][data_date] = int(row["unit_number"])
    return grouped, unit_by_day


def save_line(
    plt,
    path: Path,
    xs,
    ys,
    title: str,
    xlabel: str,
    ylabel: str,
    color=LINE_COLOR,
    vlines=None,
    time_axis=False,
):
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(xs, ys, color=color, linewidth=1.5)
    ax.axhline(0, color=ZERO_COLOR, linewidth=0.8)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    if time_axis:
        from matplotlib.dates import DateFormatter

        ax.xaxis.set_major_formatter(DateFormatter("%H:%M", tz=JST))
        fig.autofmt_xdate()
    if vlines:
        y_top = max(ys) if ys else 0
        y_bottom = min(ys) if ys else 0
        label_y = y_top if y_top != y_bottom else y_top + 1
        for x, label in vlines:
            ax.axvline(x, color="#B0B0B0", linestyle="--", linewidth=0.8)
            ax.text(
                x,
                label_y,
                label,
                fontsize=8,
                rotation=90,
                va="top",
                ha="right",
                color="#555555",
            )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def save_daily_overview(plt, path: Path, machine_rows, date_label: str):
    count = len(machine_rows)
    cols = 6
    rows = (count + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(18, 2.4 * rows), sharex=False)
    flat = axes.flatten() if count > 1 else [axes]
    for index, axis in enumerate(flat):
        if index >= count:
            axis.axis("off")
            continue
        meta, samples = machine_rows[index]
        xs = [sample.sampled_at for sample in samples]
        ys = [sample.slump_value for sample in samples]
        axis.plot(xs, ys, color=LINE_COLOR, linewidth=1.0)
        axis.axhline(0, color=ZERO_COLOR, linewidth=0.6)
        axis.set_title(f"{meta['code']} / {meta['unit']}番", fontsize=9)
        axis.grid(True, alpha=0.25)
        axis.tick_params(labelsize=7)
    fig.suptitle(f"{date_label} 台別スランプ（差枚相当）", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def write_csv(path: Path, headers, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def plot_all(out_dir: Path, source_store_id: int, model_name: str):
    plt = configure_matplotlib()
    dirs = ensure_dirs(out_dir)
    db = create_supabase_client()
    store, model, machines, unit_by_machine, slump_rows = fetch_target(
        db, source_store_id, model_name
    )
    grouped, unit_by_day = group_samples(slump_rows)
    dates = sorted({date.fromisoformat(row["data_date"]) for row in slump_rows})
    if not dates:
        raise SystemExit("slump_points がありません")

    machine_meta = [
        {
            "id": row["machine_id"],
            "code": row["machine_code"],
            "unit": unit_by_machine[row["machine_id"]],
        }
        for row in machines
        if row["machine_id"] in grouped
    ]

    print(f"[STORE] {store['store_name']} source_store_id={store['source_store_id']}", flush=True)
    print(f"[MODEL] {model['source_model_name']}", flush=True)
    print(f"[DATES] {dates[0].isoformat()} .. {dates[-1].isoformat()}", flush=True)
    print(f"[MACHINES] {len(machine_meta)}", flush=True)
    print(f"[POINTS] {len(slump_rows)}", flush=True)
    print("[PLOT] グラフを出力しています...", flush=True)

    daily_csv = []
    chained_csv = []
    daily_avg_csv = []
    chained_avg_csv = []
    daily_final_rows = []
    avg_day_series = []

    for data_date in dates:
        overview_rows = []
        day_dir = dirs["daily"] / data_date.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        finals = []

        for meta in machine_meta:
            samples = grouped[meta["id"]].get(data_date, [])
            if not samples:
                continue
            samples = sorted(samples, key=lambda sample: sample.sampled_at)
            unit = unit_by_day[meta["id"]].get(data_date, meta["unit"])
            title = (
                f"{meta['code']} / {unit}番  {data_date.isoformat()}  "
                "スランプ（差枚相当）"
            )
            save_line(
                plt,
                day_dir / f"{meta['code']}_unit{unit}.png",
                [sample.sampled_at for sample in samples],
                [sample.slump_value for sample in samples],
                title=title,
                xlabel="時刻（Asia/Tokyo）",
                ylabel="差枚相当（枚）",
                time_axis=True,
            )
            overview_rows.append(({"code": meta["code"], "unit": unit}, samples))
            finals.append(samples[-1].slump_value)
            for sample in samples:
                daily_csv.append(
                    [
                        meta["code"],
                        unit,
                        data_date.isoformat(),
                        sample.sampled_at.isoformat(),
                        sample.slump_value,
                    ]
                )

        if overview_rows:
            save_daily_overview(
                plt,
                day_dir / "_overview.png",
                overview_rows,
                data_date.isoformat(),
            )

        by_machine = {
            meta["id"]: grouped[meta["id"]].get(data_date, [])
            for meta in machine_meta
        }
        averaged = average_series(by_machine)
        if averaged:
            save_line(
                plt,
                dirs["daily_avg"] / f"{data_date.isoformat()}.png",
                [sample.sampled_at for sample in averaged],
                [sample.slump_value for sample in averaged],
                title=f"{len(machine_meta)}台平均  {data_date.isoformat()}  差枚相当",
                xlabel="時刻（Asia/Tokyo）",
                ylabel="平均差枚相当（枚）",
                color=AVG_COLOR,
                time_axis=True,
            )
            avg_day_series.append((data_date, averaged))
            for sample in averaged:
                daily_avg_csv.append(
                    [
                        data_date.isoformat(),
                        sample.sampled_at.isoformat(),
                        sample.slump_value,
                        len(by_machine),
                    ]
                )

        if finals:
            daily_final_rows.append(
                [
                    data_date.isoformat(),
                    int(round(sum(finals) / len(finals))),
                    len(finals),
                    sum(1 for value in finals if value > 0),
                    sum(1 for value in finals if value < 0),
                ]
            )

    if daily_final_rows:
        fig, ax = plt.subplots(figsize=(10, 4.5))
        labels = [row[0][5:] for row in daily_final_rows]
        values = [row[1] for row in daily_final_rows]
        colors = ["#3B7D6A" if value >= 0 else "#A65B5B" for value in values]
        ax.bar(labels, values, color=colors)
        ax.axhline(0, color=ZERO_COLOR, linewidth=0.8)
        ax.set_title("日次の平均最終差枚（各日の終点）")
        ax.set_xlabel("遊技日")
        ax.set_ylabel("平均最終差枚相当（枚）")
        ax.grid(True, axis="y", alpha=0.3)
        fig.tight_layout()
        fig.savefig(
            dirs["daily_avg"] / "_daily_final_mean.png",
            dpi=130,
            bbox_inches="tight",
        )
        plt.close(fig)

    for meta in machine_meta:
        day_pairs = [
            (data_date, grouped[meta["id"]].get(data_date, []))
            for data_date in dates
        ]
        chained = chain_days(day_pairs)
        if not chained:
            continue
        vlines = [
            (point.hours_from_origin, point.data_date.strftime("%m/%d"))
            for point in chained
            if point.is_day_start
        ]
        save_line(
            plt,
            dirs["chained"] / f"{meta['code']}_unit{meta['unit']}.png",
            [point.hours_from_origin for point in chained],
            [point.chained_value for point in chained],
            title=(
                f"{meta['code']} / {meta['unit']}番  連続スランプ"
                f"（{dates[0].strftime('%m/%d')}起点）"
            ),
            xlabel="連結時間（時間、日を跨いだ隙間は詰める）",
            ylabel="連結差枚相当（枚）",
            vlines=vlines,
        )
        for point in chained:
            unit = unit_by_day[meta["id"]].get(point.data_date, meta["unit"])
            chained_csv.append(
                [
                    meta["code"],
                    unit,
                    point.data_date.isoformat(),
                    point.sampled_at.isoformat(),
                    point.original_value,
                    point.chained_value,
                    f"{point.hours_from_origin:.4f}",
                    int(point.is_day_start),
                ]
            )

    chained_avg = chain_days(avg_day_series)
    if chained_avg:
        vlines = [
            (point.hours_from_origin, point.data_date.strftime("%m/%d"))
            for point in chained_avg
            if point.is_day_start
        ]
        save_line(
            plt,
            dirs["chained_avg"] / "chained_average.png",
            [point.hours_from_origin for point in chained_avg],
            [point.chained_value for point in chained_avg],
            title=(
                f"{len(machine_meta)}台平均  連続差枚相当"
                f"（{dates[0].strftime('%m/%d')}起点）"
            ),
            xlabel="連結時間（時間、日を跨いだ隙間は詰める）",
            ylabel="平均連結差枚相当（枚）",
            color=AVG_COLOR,
            vlines=vlines,
        )
        for point in chained_avg:
            chained_avg_csv.append(
                [
                    point.data_date.isoformat(),
                    point.sampled_at.isoformat(),
                    point.original_value,
                    point.chained_value,
                    f"{point.hours_from_origin:.4f}",
                    int(point.is_day_start),
                ]
            )

    write_csv(
        dirs["series"] / "daily.csv",
        ["machine_code", "unit_number", "data_date", "sampled_at_jst", "slump_value"],
        daily_csv,
    )
    write_csv(
        dirs["series"] / "chained.csv",
        [
            "machine_code",
            "unit_number",
            "data_date",
            "sampled_at_jst",
            "original_slump_value",
            "chained_slump_value",
            "hours_from_origin",
            "is_day_start",
        ],
        chained_csv,
    )
    write_csv(
        dirs["series"] / "daily_avg.csv",
        ["data_date", "sampled_at_jst", "avg_slump_value", "machine_count"],
        daily_avg_csv,
    )
    write_csv(
        dirs["series"] / "chained_avg.csv",
        [
            "data_date",
            "sampled_at_jst",
            "original_avg_slump_value",
            "chained_avg_slump_value",
            "hours_from_origin",
            "is_day_start",
        ],
        chained_avg_csv,
    )
    write_csv(
        dirs["series"] / "daily_final_mean.csv",
        ["data_date", "avg_final_slump", "machine_count", "plus_count", "minus_count"],
        daily_final_rows,
    )

    print(f"[OUT] {out_dir.resolve()}", flush=True)
    print("[NOTE] Y値は slump_points.slump_value（サイトグラフ値）。閉店時最終差枚とは限りません。", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="slump_points から台別・平均のスランプグラフを生成する"
    )
    parser.add_argument(
        "--source-store-id",
        type=int,
        default=DEFAULT_SOURCE_STORE_ID,
        help="取得元店舗ID。省略時 100928",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="取得元機種名。省略時 ToLOVEるダークネス",
    )
    parser.add_argument(
        "--out",
        default=str(SLUMP_DIR),
        help="出力先ディレクトリ。省略時 data/slump",
    )
    args = parser.parse_args()
    plot_all(Path(args.out), args.source_store_id, args.model)


if __name__ == "__main__":
    main()
