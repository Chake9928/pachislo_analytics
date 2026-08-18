from pathlib import Path
from time import sleep

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from config import NAVIGATION_TIMEOUT_MS, WAIT_SECONDS
from machine_master import UnitAssignment, normalize_model


class AccessLimitError(RuntimeError):
    pass


class ModelMismatchError(RuntimeError):
    pass


def build_url(store_id: str, unit: int, target_date) -> str:
    return (
        f"https://daidata.goraggio.com/{store_id}/detail"
        f"?unit={unit}&target_date={target_date.isoformat()}"
    )


def accept_terms_if_needed(page, store_id: str) -> None:
    """利用規約画面に遷移した場合だけ、通常の画面操作で同意する。"""
    if f"/{store_id}/accept" not in page.url:
        return

    print(f"[INFO] store_id={store_id}: 利用規約画面を検出しました")
    button = page.locator(".accept_btn button")

    try:
        button.wait_for(state="visible", timeout=10_000)
        button.click()
        page.wait_for_url(
            lambda url: f"/{store_id}/accept" not in str(url),
            timeout=NAVIGATION_TIMEOUT_MS,
        )
        print("[INFO] 利用規約への同意が完了しました")
    except PlaywrightTimeoutError as exc:
        raise RuntimeError("利用規約への同意処理に失敗しました") from exc


def check_response(response) -> None:
    if response is None:
        return

    print(f"[STATUS] {response.status}")

    # アクセス制限を検知した場合は、回避・再試行せず停止する。
    if response.status in (403, 429):
        raise AccessLimitError(f"HTTP {response.status} が返されました")


def collect_assignment_html(page, assignment: UnitAssignment, target_date):
    url = build_url(assignment.store_id, assignment.unit, target_date)

    print("-" * 60)
    print(f"[MACHINE_ID] {assignment.machine_id}")
    print(f"[STORE]      {assignment.store_id}")
    print(f"[UNIT]       {assignment.unit}")
    print(f"[DATE]       {target_date.isoformat()}")
    print(f"[EXPECTED]   {assignment.model}")
    print(f"[GET]        {url}")

    response = page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT_MS,
    )
    check_response(response)

    accept_terms_if_needed(page, assignment.store_id)

    expected_unit = f"unit={assignment.unit}"
    expected_date = f"target_date={target_date.isoformat()}"
    if expected_unit not in page.url or expected_date not in page.url:
        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=NAVIGATION_TIMEOUT_MS,
        )
        check_response(response)

    try:
        page.locator("#pachinkoTi").wait_for(
            state="visible",
            timeout=NAVIGATION_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            f"{assignment.store_id}/{assignment.unit}番台 "
            f"{target_date.isoformat()} の詳細ページを確認できませんでした"
        ) from exc

    actual_model = (
        page.locator("#pachinkoTi strong").first.text_content() or ""
    ).strip()

    # staleな台番号マスタで別機種を誤取得することを防ぐ。
    if normalize_model(actual_model) != normalize_model(assignment.model):
        raise ModelMismatchError(
            "機種名が台マスタと一致しません。"
            f" machine_id={assignment.machine_id}, unit={assignment.unit}, "
            f"expected={assignment.model!r}, actual={actual_model!r}"
        )

    print(f"[ACTUAL]     {actual_model}")
    print(f"[TITLE]      {page.title()}")
    print(
        "[GRAPH SCRIPT] "
        f"{page.locator('script[data-plot-graph-script]').count()} 件"
    )

    return page.content(), actual_model


def save_html(
    assignment: UnitAssignment,
    target_date,
    html: str,
    raw_dir: Path,
) -> Path:
    # 複数店舗で台番号が重複しても衝突しないよう store_id を階層に含める。
    output_dir = raw_dir / assignment.store_id / target_date.isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{assignment.unit}.html"
    output_path.write_text(html, encoding="utf-8")

    print(f"[SAVE] {output_path}")
    print(f"[SIZE] {len(html):,} characters")

    return output_path


def wait_between_requests() -> None:
    sleep(WAIT_SECONDS)
