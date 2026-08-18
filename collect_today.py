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
    collect_assignment_html,
    save_html,
    wait_between_requests,
)
from machine_master import get_assignments_for_date, load_assignments


def main():
    target_date = BASE_DATE
    master = load_assignments(UNIT_MAPPING_CSV)
    targets = get_assignments_for_date(master, target_date)

    print("[MODE] 当日1日分取得")
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
                    html, _ = collect_assignment_html(
                        page, assignment, target_date
                    )
                    save_html(assignment, target_date, html, RAW_DIR)
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
