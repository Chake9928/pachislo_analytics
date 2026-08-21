"""既存の raw HTML / スランプ出力を統一パスへ移す。

raw:
    data/raw/{store_id}/{model_id}/{YYYY-MM-DD}/{machine_id}.html

slump:
    data/slump/{store_id}/{model_id}/01_daily_by_machine/{YYYY-MM-DD}/
    data/slump/{store_id}/{model_id}/02_chained_by_machine/
    data/slump/{store_id}/{model_id}/03_daily_average/
    data/slump/{store_id}/{model_id}/04_chained_average/
    data/slump/{store_id}/{model_id}/series/

スランプの最旧パス（分析種別が先頭で店舗・機種がないもの）は
--source-store-id と --model で補完する。

実行:
    python scripts/db/reorganize_storage.py --dry-run
    python scripts/db/reorganize_storage.py

オプション:
    --dry-run            移動せず、予定だけ表示する
    --source-store-id    最旧スランプ整理に使う取得元店舗ID。省略時 100928
    --model              最旧スランプ整理に使う機種名。省略時 ToLOVEるダークネス
"""

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import RAW_DIR, SLUMP_DIR, UNIT_MAPPING_CSV
from machine_master import (
    load_assignments,
    resolve_assignment,
    resolve_assignment_by_machine_id,
)
from model_lookup import load_model_id_map, resolve_model_id
from storage_paths import (
    DATE_DIR_PATTERN,
    parse_raw_html_path,
    raw_html_path,
    slump_chained_average_dir,
    slump_chained_machine_dir,
    slump_daily_average_dir,
    slump_daily_machine_dir,
    slump_series_dir,
)


def move_file(src: Path, dest: Path, dry_run: bool):
    if src.resolve() == dest.resolve():
        return "skip"
    if dest.exists():
        print(f"[EXISTS] {dest}  (src={src})")
        return "exists"
    print(f"[MOVE] {src} -> {dest}")
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    return "moved"


def remove_empty_dirs(root: Path, dry_run: bool):
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            print(f"[RMDIR] {path}")
            if not dry_run:
                path.rmdir()


def reorganize_raw(dry_run: bool):
    master = load_assignments(UNIT_MAPPING_CSV)
    model_ids = load_model_id_map()
    files = sorted(RAW_DIR.rglob("*.html"))
    print(f"[RAW] files={len(files)}")
    counts = {"moved": 0, "skip": 0, "exists": 0, "error": 0}

    for path in files:
        loc = parse_raw_html_path(path)
        try:
            if loc.machine_code and loc.model_id and loc.store_id and loc.data_date:
                dest = raw_html_path(
                    RAW_DIR,
                    loc.store_id,
                    loc.model_id,
                    loc.data_date,
                    loc.machine_code,
                )
                if path.resolve() == dest.resolve():
                    counts["skip"] += 1
                    continue

            data_date = loc.data_date
            if data_date is None:
                raise ValueError("日付フォルダではありません")

            if loc.machine_code:
                assignment = resolve_assignment_by_machine_id(
                    master, loc.machine_code, data_date
                )
            elif loc.unit is not None and loc.store_id:
                assignment = resolve_assignment(
                    master, loc.store_id, loc.unit, data_date
                )
            else:
                raise ValueError("store_id / unit / machine_id を特定できません")

            if assignment is None:
                raise ValueError("台マスタに該当なし")

            model_id = resolve_model_id(
                assignment.source_system, assignment.model, model_ids
            )
            dest = raw_html_path(
                RAW_DIR,
                assignment.store_id,
                model_id,
                data_date,
                assignment.machine_id,
            )
            result = move_file(path, dest, dry_run)
            counts[result] += 1
        except Exception as exc:
            counts["error"] += 1
            print(f"[ERROR] {path}: {exc}")

    remove_empty_dirs(RAW_DIR, dry_run)
    print(
        f"[RAW DONE] moved={counts['moved']} skip={counts['skip']} "
        f"exists={counts['exists']} error={counts['error']}"
    )
    return counts["error"]


KIND_DIRS = {
    "01_daily_by_machine",
    "02_chained_by_machine",
    "03_daily_average",
    "04_chained_average",
    "series",
}


def slump_dest_for_file(path: Path, fallback_store, fallback_model) -> Path:
    """現行・旧・最旧のスランプパスを統一先へ写す。"""
    rel = path.relative_to(SLUMP_DIR)
    parts = rel.parts
    name = parts[-1]

    # 新: {store}/{model}/01_daily_by_machine/{date}/file
    if (
        len(parts) == 5
        and parts[0].isdigit()
        and parts[1].isdigit()
        and parts[2] == "01_daily_by_machine"
        and DATE_DIR_PATTERN.match(parts[3])
    ):
        return path

    # 中間: 01_daily_by_machine/{date}/{store}/{model}/file
    if (
        len(parts) == 5
        and parts[0] == "01_daily_by_machine"
        and DATE_DIR_PATTERN.match(parts[1])
        and parts[2].isdigit()
        and parts[3].isdigit()
    ):
        return (
            slump_daily_machine_dir(
                SLUMP_DIR,
                date.fromisoformat(parts[1]),
                parts[2],
                parts[3],
            )
            / name
        )

    # 最旧: 01_daily_by_machine/{date}/file
    if (
        len(parts) == 3
        and parts[0] == "01_daily_by_machine"
        and DATE_DIR_PATTERN.match(parts[1])
    ):
        return (
            slump_daily_machine_dir(
                SLUMP_DIR,
                date.fromisoformat(parts[1]),
                fallback_store,
                fallback_model,
            )
            / name
        )

    kind_at_2 = len(parts) == 4 and parts[2] in KIND_DIRS - {"01_daily_by_machine"}
    # 新: {store}/{model}/{kind}/file  （日付なし種別）
    if (
        kind_at_2
        and parts[0].isdigit()
        and parts[1].isdigit()
    ):
        return path

    kind_at_0 = len(parts) == 4 and parts[0] in KIND_DIRS - {"01_daily_by_machine"}
    # 中間: {kind}/{store}/{model}/file
    if kind_at_0 and parts[1].isdigit() and parts[2].isdigit():
        kind = parts[0]
        store_id, model_id = parts[1], parts[2]
        dest_dir = {
            "02_chained_by_machine": slump_chained_machine_dir,
            "03_daily_average": slump_daily_average_dir,
            "04_chained_average": slump_chained_average_dir,
            "series": slump_series_dir,
        }[kind](SLUMP_DIR, store_id, model_id)
        return dest_dir / name

    # 最旧: {kind}/file
    if len(parts) == 2 and parts[0] in KIND_DIRS - {"01_daily_by_machine"}:
        kind = parts[0]
        dest_dir = {
            "02_chained_by_machine": slump_chained_machine_dir,
            "03_daily_average": slump_daily_average_dir,
            "04_chained_average": slump_chained_average_dir,
            "series": slump_series_dir,
        }[kind](SLUMP_DIR, fallback_store, fallback_model)
        return dest_dir / name

    raise ValueError(f"スランプパスを解釈できません: {path}")


def reorganize_slump(source_store_id: int, model_name: str, dry_run: bool):
    model_ids = load_model_id_map()
    model_id = resolve_model_id("daidata", model_name, model_ids)
    store_id = str(source_store_id)
    print(f"[SLUMP] fallback store_id={store_id} model_id={model_id}")

    files = [
        path
        for path in sorted(SLUMP_DIR.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".png", ".csv"}
    ]
    print(f"[SLUMP] files={len(files)}")
    counts = {"moved": 0, "skip": 0, "exists": 0, "error": 0}

    for path in files:
        try:
            dest = slump_dest_for_file(path, store_id, model_id)
            result = move_file(path, dest, dry_run)
            counts[result] += 1
        except Exception as exc:
            counts["error"] += 1
            print(f"[ERROR] {path}: {exc}")

    remove_empty_dirs(SLUMP_DIR, dry_run)
    print(
        f"[SLUMP DONE] moved={counts['moved']} skip={counts['skip']} "
        f"exists={counts['exists']} error={counts['error']}"
    )
    return counts["error"]


def main():
    parser = argparse.ArgumentParser(
        description="raw HTML とスランプ出力を {store_id}/{model_id}/... へ移す"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="移動せず、予定だけ表示する",
    )
    parser.add_argument(
        "--source-store-id",
        type=int,
        default=100928,
        help="最旧スランプ整理に使う取得元店舗ID。省略時 100928",
    )
    parser.add_argument(
        "--model",
        default="L ToLOVEるﾀﾞｰｸﾈｽver.8.7",
        help="最旧スランプ整理に使う機種名。省略時 ToLOVEるダークネス",
    )
    args = parser.parse_args()

    print(f"[MODE] {'dry-run' if args.dry_run else 'move'}")
    raw_errors = reorganize_raw(args.dry_run)
    slump_errors = reorganize_slump(args.source_store_id, args.model, args.dry_run)
    if raw_errors or slump_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
