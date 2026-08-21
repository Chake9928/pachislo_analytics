"""当日を含む直近7日分の台詳細HTMLを収集する。

config.py の BASE_DATE を終点とし、BASE_DATE-6日〜BASE_DATE の7日間を
unit_mapping.csv の配置に従って取得する。保存先は collect_oneday.py と同じ。

実行:
    python scripts/scraping/collect_7days.py

オプション:
    なし。対象期間は config.py の BASE_DATE、待機間隔は WAIT_SECONDS を参照。
"""

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from playwright.sync_api import sync_playwright

from config import (
    BASE_DATE,
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


DAYS = 7


def build_target_dates():
    # BASE_DATEを含めて BASE_DATE-6日 ～ BASE_DATE の7日間。
    return [
        BASE_DATE - timedelta(days=offset)
        for offset in range(DAYS - 1, -1, -1)
    ]


def main():
    master = load_assignments(UNIT_MAPPING_CSV)
    target_dates = build_target_dates()

    targets_by_date = {
        target_date: get_assignments_for_date(master, target_date)
        for target_date in target_dates
    }
    total = sum(len(rows) for rows in targets_by_date.values())

    print("[MODE] 当日を含む直近7日分取得")
    print(
        f"[RANGE] {target_dates[0].isoformat()} "
        f"～ {target_dates[-1].isoformat()}"
    )
    print(f"[TOTAL] {total}ページ")

    success = []
    failed = []
    current = 0
    stop_requested = False

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=HEADLESS,
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            for target_date in target_dates:
                targets = targets_by_date[target_date]
                print("\n" + "=" * 60)
                print(
                    f"[DATE] {target_date.isoformat()} / {len(targets)}台"
                )

                for assignment in targets:
                    current += 1
                    print(f"\n[PROGRESS] {current}/{total}")

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
                        save_html(assignment, target_date, html, RAW_DIR)
                        success.append(
                            (
                                target_date.isoformat(),
                                assignment.machine_id,
                                assignment.unit,
                            )
                        )

                    except AccessLimitError as exc:
                        print(f"[ERROR] {exc}")
                        print("[STOP] アクセス制限を検出したため処理を終了します")
                        stop_requested = True
                        break

                    except ModelMismatchError as exc:
                        print(f"[MODEL_MISMATCH] {exc}")
                        failed.append(
                            (
                                target_date.isoformat(),
                                assignment.machine_id,
                                assignment.unit,
                                "MODEL_MISMATCH",
                            )
                        )

                    except RuntimeError as exc:
                        print(f"[ERROR] {exc}")
                        failed.append(
                            (
                                target_date.isoformat(),
                                assignment.machine_id,
                                assignment.unit,
                                str(exc),
                            )
                        )

                    if current < total:
                        wait_between_requests()

                if stop_requested:
                    break

        finally:
            context.close()

    print("\n" + "=" * 60)
    print("[RESULT]")
    print(f"成功: {len(success)}ページ")
    print(f"失敗: {len(failed)}ページ")
    if failed:
        print("失敗一覧:")
        for target_date, machine_id, unit, reason in failed:
            print(f"  {target_date} / {machine_id} / {unit}: {reason}")


if __name__ == "__main__":
    main()
