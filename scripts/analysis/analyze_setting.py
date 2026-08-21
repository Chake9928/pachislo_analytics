"""raw HTML の大当たり履歴から設定判別用カウントを CSV 出力する。

店舗×機種ディレクトリへ、台別日次・台別期間合計・店舗日次・店舗期間合計と
疑似ボーナス明細を書き出す。判別条件は機種ごとに setting_detect.py で定義する。
現在対応: model_id=1（L ToLOVEるﾀﾞｰｸﾈｽver.8.7）

出力:
    data/setting/{store_id}/{model_id}/machine_daily.csv
    data/setting/{store_id}/{model_id}/machine_total.csv
    data/setting/{store_id}/{model_id}/store_daily.csv
    data/setting/{store_id}/{model_id}/store_total.csv
    data/setting/{store_id}/{model_id}/pseudo_bonus_events.csv
    data/setting/{store_id}/{model_id}/summary.html

実行:
    python scripts/analysis/analyze_setting.py
    python scripts/analysis/analyze_setting.py --store-id 100928 --model-id 1
    python scripts/analysis/analyze_setting.py --store-id 100928 --model "L ToLOVEるﾀﾞｰｸﾈｽver.8.7"
    python scripts/analysis/analyze_setting.py --raw data/raw --out data/setting
    python scripts/analysis/summarize_setting.py data/setting/100928/1

オプション:
    --store-id  店舗ID。省略時は raw 配下の全店舗
    --model-id  機種ID。省略時は定義がある機種のみ
    --model     機種名（unit_mapping.csv の model）。省略時は全機種
    --raw       入力 raw ディレクトリ。省略時 data/raw
    --out       出力ディレクトリ。省略時 data/setting
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import RAW_DIR, SETTING_DIR, UNIT_MAPPING_CSV
from html_parser import parse_html_file
from machine_master import load_assignments, normalize_model
from setting_detect import (
    COUNT_KEYS,
    get_spec,
    resolve_known_model_id,
)
from setting_summary import write_setting_summary
from storage_paths import parse_raw_html_path, setting_store_model_dir


MACHINE_DAILY_FIELDS = (
    "store_id",
    "model_id",
    "machine_id",
    "unit_number",
    "data_date",
    *COUNT_KEYS,
)
MACHINE_TOTAL_FIELDS = (
    "store_id",
    "model_id",
    "machine_id",
    "unit_number",
    "date_from",
    "date_to",
    *COUNT_KEYS,
)
STORE_DAILY_FIELDS = (
    "store_id",
    "model_id",
    "data_date",
    "machine_count",
    *COUNT_KEYS,
)
STORE_TOTAL_FIELDS = (
    "store_id",
    "model_id",
    "machine_count",
    "date_from",
    "date_to",
    *COUNT_KEYS,
)
EVENT_FIELDS = (
    "store_id",
    "model_id",
    "machine_id",
    "unit_number",
    "data_date",
    "start_count",
    "zone",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="設定判別用カウントをCSVへ出力する"
    )
    parser.add_argument("--store-id", help="店舗ID。省略時は全店舗")
    parser.add_argument("--model-id", help="機種ID。省略時は定義がある機種")
    parser.add_argument(
        "--model",
        help="機種名（unit_mapping.csv の model）。省略時は全機種",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=RAW_DIR,
        help="入力 raw ディレクトリ。省略時 data/raw",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=SETTING_DIR,
        help="出力ディレクトリ。省略時 data/setting",
    )
    return parser.parse_args()


def list_html_files(raw_dir: Path):
    if raw_dir.is_file():
        return [raw_dir]
    return sorted(Path(raw_dir).rglob("*.html"))


def write_csv(path: Path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"[SAVE] {path} ({len(rows)}行)")


def empty_counts():
    return {key: 0 for key in COUNT_KEYS}


def add_counts(left, right):
    return {key: left[key] + right[key] for key in COUNT_KEYS}


def analyze_file(html_path: Path, master, store_id_filter, model_id_filter, model_name_filter):
    loc = parse_raw_html_path(html_path)
    if loc.data_date is None:
        return None
    if store_id_filter and loc.store_id and loc.store_id != store_id_filter:
        return None

    loc_model_id = None
    if loc.model_id and str(loc.model_id).isdigit():
        loc_model_id = int(loc.model_id)
    if model_id_filter is not None and loc_model_id is not None:
        if loc_model_id != model_id_filter:
            return None

    page = parse_html_file(html_path, master)
    if store_id_filter and str(page.source_store_id) != store_id_filter:
        return None
    if model_name_filter and normalize_model(page.source_model_name) != model_name_filter:
        return None

    model_id = loc_model_id or resolve_known_model_id(page.source_model_name)
    if model_id is None:
        return None
    if model_id_filter is not None and model_id != model_id_filter:
        return None

    spec = get_spec(model_id)
    if spec is None:
        return None

    result = spec.analyze_events(page.jackpot_events)
    return {
        "store_id": str(page.source_store_id),
        "model_id": model_id,
        "machine_id": page.machine_code,
        "unit_number": page.unit_number,
        "data_date": page.requested_data_date,
        "counts": result.as_dict(),
        "pseudo_bonuses": result.pseudo_bonuses,
    }


def build_outputs(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["store_id"], row["model_id"])].append(row)

    outputs = {}
    for key, items in grouped.items():
        items.sort(key=lambda r: (r["machine_id"], r["data_date"]))
        machine_daily = []
        events = []
        for item in items:
            machine_daily.append(
                {
                    "store_id": item["store_id"],
                    "model_id": item["model_id"],
                    "machine_id": item["machine_id"],
                    "unit_number": item["unit_number"],
                    "data_date": item["data_date"].isoformat(),
                    **item["counts"],
                }
            )
            for bonus in item["pseudo_bonuses"]:
                events.append(
                    {
                        "store_id": item["store_id"],
                        "model_id": item["model_id"],
                        "machine_id": item["machine_id"],
                        "unit_number": item["unit_number"],
                        "data_date": item["data_date"].isoformat(),
                        "start_count": bonus.start_count,
                        "zone": bonus.zone,
                    }
                )

        by_machine = defaultdict(list)
        for item in items:
            by_machine[item["machine_id"]].append(item)

        machine_total = []
        for machine_id, days in sorted(by_machine.items()):
            days.sort(key=lambda r: r["data_date"])
            total = empty_counts()
            for day in days:
                total = add_counts(total, day["counts"])
            latest = days[-1]
            machine_total.append(
                {
                    "store_id": latest["store_id"],
                    "model_id": latest["model_id"],
                    "machine_id": machine_id,
                    "unit_number": latest["unit_number"],
                    "date_from": days[0]["data_date"].isoformat(),
                    "date_to": latest["data_date"].isoformat(),
                    **total,
                }
            )

        by_date = defaultdict(list)
        for item in items:
            by_date[item["data_date"]].append(item)

        store_daily = []
        store_id, model_id = key
        for data_date, days in sorted(by_date.items()):
            total = empty_counts()
            for day in days:
                total = add_counts(total, day["counts"])
            store_daily.append(
                {
                    "store_id": store_id,
                    "model_id": model_id,
                    "data_date": data_date.isoformat(),
                    "machine_count": len({d["machine_id"] for d in days}),
                    **total,
                }
            )

        period_total = empty_counts()
        for day in store_daily:
            period_total = add_counts(period_total, {k: day[k] for k in COUNT_KEYS})
        dates = sorted(by_date)
        store_total = [
            {
                "store_id": store_id,
                "model_id": model_id,
                "machine_count": len(by_machine),
                "date_from": dates[0].isoformat(),
                "date_to": dates[-1].isoformat(),
                **period_total,
            }
        ]

        outputs[key] = {
            "machine_daily": machine_daily,
            "machine_total": machine_total,
            "store_daily": store_daily,
            "store_total": store_total,
            "pseudo_bonus_events": events,
        }
    return outputs


def main():
    args = parse_args()
    store_id_filter = str(args.store_id).strip() if args.store_id else ""
    model_id_filter = None
    if args.model_id:
        try:
            model_id_filter = int(args.model_id)
        except ValueError:
            raise SystemExit(f"model_id が不正です: {args.model_id}")
        if get_spec(model_id_filter) is None:
            raise SystemExit(
                f"model_id={model_id_filter} の設定判別定義がありません"
            )

    model_name_filter = ""
    if args.model:
        model_name_filter = normalize_model(args.model)
        known = resolve_known_model_id(args.model)
        if known is None:
            raise SystemExit(
                f"機種 {args.model!r} の設定判別定義がありません"
            )
        if model_id_filter is None:
            model_id_filter = known
        elif model_id_filter != known:
            raise SystemExit(
                f"--model と --model-id が一致しません: "
                f"model_id={model_id_filter} name={args.model!r}"
            )

    master = load_assignments(UNIT_MAPPING_CSV)
    files = list_html_files(args.raw)
    print(f"[MODE] 設定判別集計")
    print(f"[RAW]  {args.raw}")
    print(f"[OUT]  {args.out}")
    print(f"[HTML] {len(files)}件")

    rows = []
    skipped_no_spec = set()
    for html_path in files:
        loc = parse_raw_html_path(html_path)
        loc_model_id = None
        if loc.model_id and str(loc.model_id).isdigit():
            loc_model_id = int(loc.model_id)
            if model_id_filter is not None and loc_model_id != model_id_filter:
                continue
            if get_spec(loc_model_id) is None:
                skipped_no_spec.add(loc_model_id)
                continue
        try:
            row = analyze_file(
                html_path,
                master,
                store_id_filter,
                model_id_filter,
                model_name_filter,
            )
        except Exception as exc:
            print(f"[ERROR] {html_path}: {exc}")
            continue
        if row:
            rows.append(row)

    if skipped_no_spec:
        skipped = ", ".join(str(x) for x in sorted(skipped_no_spec))
        print(f"[SKIP] 設定判別定義なし model_id={skipped}")

    if not rows:
        raise SystemExit("集計対象のHTMLがありません")

    outputs = build_outputs(rows)
    for (store_id, model_id), tables in sorted(outputs.items()):
        out_dir = setting_store_model_dir(args.out, store_id, model_id)
        write_csv(out_dir / "machine_daily.csv", MACHINE_DAILY_FIELDS, tables["machine_daily"])
        write_csv(out_dir / "machine_total.csv", MACHINE_TOTAL_FIELDS, tables["machine_total"])
        write_csv(out_dir / "store_daily.csv", STORE_DAILY_FIELDS, tables["store_daily"])
        write_csv(out_dir / "store_total.csv", STORE_TOTAL_FIELDS, tables["store_total"])
        write_csv(
            out_dir / "pseudo_bonus_events.csv",
            EVENT_FIELDS,
            tables["pseudo_bonus_events"],
        )
        html_path = write_setting_summary(out_dir)
        print(f"[SAVE] {html_path}")


if __name__ == "__main__":
    main()
