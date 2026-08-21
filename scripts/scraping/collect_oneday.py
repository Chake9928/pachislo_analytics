"""指定日1日分の台詳細HTMLを収集する。

unit_mapping.csv の対象日配置に基づき、Playwrightで台データサイトから
HTMLを取得し data/raw/{store_id}/{model_id}/{YYYY-MM-DD}/{machine_id}.html に保存する。
model_id は Supabase の models テーブルから解決する。

実行:
    python scripts/scraping/collect_oneday.py YYYY-MM-DD

引数:
    date  取得対象日（YYYY-MM-DD）。必須。

オプション:
    なし。ヘッドレス等は config.py の HEADLESS / WAIT_SECONDS を参照。
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from playwright.sync_api import sync_playwright

from config import (
    HEADLESS,
    PROFILE_DIR,
    RAW_DIR,
    UNIT_MAPPING_CSV,
)
from collector_common import (
    AccessLimitError,
    ModelMismatchError,
    build_url,
    collect_assignment_html,
    save_html,
    wait_between_requests,
)
from machine_master import get_assignments_for_date, load_assignments
from model_lookup import load_model_id_map, resolve_model_id


def parse_args():
    parser = argparse.ArgumentParser(description="指定日1日分の台データを収集する")
    parser.add_argument(
        "date",
        help="取得対象日 YYYY-MM-DD",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        target_date = date.fromisoformat(args.date)
    except ValueError:
        raise SystemExit(
            f"日付の形式が不正です: {args.date}（YYYY-MM-DD で指定してください）"
        )

    master = load_assignments(UNIT_MAPPING_CSV)
    targets = get_assignments_for_date(master, target_date)
    model_ids = load_model_id_map()

    print("[MODE] 指定日1日分取得")
    print(f"[DATE] {target_date.isoformat()}")
    print(f"[TARGETS] {len(targets)}台")

    success = []
    failed = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=HEADLESS,
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            for index, assignment in enumerate(targets, start=1):
                print(f"\n[PROGRESS] {index}/{len(targets)}")

                try:
                    url = build_url(
                        assignment.store_id,
                        assignment.unit,
                        target_date,
                    )
                    html, _ = collect_assignment_html(
                        page=page,
                        url=url,
                        machine_id=assignment.machine_id,
                        store_id=assignment.store_id,
                        unit=assignment.unit,
                        target_date=target_date,
                        expected_model=assignment.model,
                    )
                    model_id = resolve_model_id(
                        assignment.source_system,
                        assignment.model,
                        model_ids,
                    )
                    save_html(assignment, target_date, html, RAW_DIR, model_id)
                    success.append(assignment.machine_id)

                except AccessLimitError as exc:
                    print(f"[ERROR] {exc}")
                    print("[STOP] アクセス制限を検出したため処理を終了します")
                    break

                except ModelMismatchError as exc:
                    # 台番号変更をマスタへ反映し忘れた可能性が高いため、保存しない。
                    print(f"[MODEL_MISMATCH] {exc}")
                    failed.append((assignment.machine_id, "MODEL_MISMATCH"))

                except RuntimeError as exc:
                    print(f"[ERROR] {exc}")
                    failed.append((assignment.machine_id, str(exc)))

                if index < len(targets):
                    wait_between_requests()

        finally:
            context.close()

    print("\n" + "=" * 60)
    print("[RESULT]")
    print(f"成功: {len(success)}台")
    print(f"失敗: {len(failed)}台")
    if failed:
        for machine_id, reason in failed:
            print(f"  {machine_id}: {reason}")


if __name__ == "__main__":
    main()
