"""Playwrightによる台詳細HTML収集の共通処理。

URL組み立て、利用規約同意、機種名照合、HTML保存を提供する。
scripts/scraping の収集スクリプトから import して使う。

実行:
    単体では実行しない。収集は以下のいずれか。
        python scripts/scraping/collect_oneday.py YYYY-MM-DD
        python scripts/scraping/collect_7days.py
"""

from pathlib import Path
from time import sleep

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

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


def collect_assignment_html(
    page,
    url,
    machine_id,
    store_id,
    unit,
    target_date,
    expected_model,
):
    print(f"[MACHINE_ID] {machine_id}")
    print(f"[STORE]      {store_id}")
    print(f"[UNIT]       {unit}")
    print(f"[DATE]       {target_date}")
    print(f"[EXPECTED]   {expected_model}")
    print(f"[GET]        {url}")

    # --------------------------------------------------
    # 1. ナビゲーション
    #
    # DOMContentLoaded 全体を待たず、
    # document の読み込み開始までで goto を完了させる
    # --------------------------------------------------
    try:
        response = page.goto(
            url,
            wait_until="commit",
            timeout=NAVIGATION_TIMEOUT_MS,
        )

    except PlaywrightTimeoutError as e:
        raise RuntimeError(
            f"ページへの接続自体がタイムアウトしました: "
            f"unit={unit}, date={target_date}"
        ) from e

    # --------------------------------------------------
    # 2. HTTPステータス確認
    # --------------------------------------------------
    check_response(response)

    # --------------------------------------------------
    # 3. 利用規約ページまたは台詳細のDOMが
    #    出現するまで待つ
    # --------------------------------------------------
    try:
        page.locator(
            "#pachinkoTi, .accept_btn button"
        ).first.wait_for(
            state="visible",
            timeout=NAVIGATION_TIMEOUT_MS,
        )

    except PlaywrightTimeoutError as e:
        raise RuntimeError(
            f"台詳細ページの主要要素が表示されませんでした: "
            f"unit={unit}, date={target_date}, url={page.url}"
        ) from e

    # --------------------------------------------------
    # 4. 利用規約
    # --------------------------------------------------
    accept_terms_if_needed(page, store_id)

    # --------------------------------------------------
    # 5. 台詳細が表示されたことを明示的に確認
    # --------------------------------------------------
    try:
        page.locator("#pachinkoTi").wait_for(
            state="visible",
            timeout=NAVIGATION_TIMEOUT_MS,
        )

    except PlaywrightTimeoutError as e:
        raise RuntimeError(
            f"台詳細ページが表示されませんでした: "
            f"unit={unit}, date={target_date}"
        ) from e

    # --------------------------------------------------
    # 6. 機種名確認
    # --------------------------------------------------
    actual_model = (
        page.locator("#pachinkoTi strong").first.inner_text().strip()
    )

    print(f"[ACTUAL]     {actual_model}")

    if normalize_model(actual_model) != normalize_model(expected_model):
        raise ModelMismatchError(
            "機種名が台マスタと一致しません。"
            f" machine_id={machine_id}, unit={unit}, "
            f"expected={expected_model!r}, actual={actual_model!r}"
        )

    # --------------------------------------------------
    # 7. JavaScript入りDOMを取得
    # --------------------------------------------------
    html = page.content()

    return html, actual_model


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
