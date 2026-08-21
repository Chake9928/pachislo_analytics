"""raw HTMLから対象日のスランプ時系列をCSVへ出力する（ローカル確認用）。

data/raw 配下を走査し、machine_id + 日付 + 時刻で重複排除したうえで
data/processed/slump_timeseries.csv を書き出す。Supabaseには投入しない。

実行:
    python scripts/analysis/parse_timeseries.py

オプション:
    なし。入力は config.py の RAW_DIR、出力は PROCESSED_DIR を参照。
"""

import csv
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bs4 import BeautifulSoup

from config import PROCESSED_DIR, RAW_DIR, UNIT_MAPPING_CSV
from machine_master import (
    load_assignments,
    normalize_model,
    resolve_assignment,
)


OUTPUT_CSV = PROCESSED_DIR / "slump_timeseries.csv"

POINT_PATTERN = re.compile(
    r'\["(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",\s*(-?\d+)\]'
)
STORE_ID_PATTERN = re.compile(r"daidata\.goraggio\.com/(\d+)/")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def detect_store_id(html_path: Path, html: str):
    """
    新形式: data/raw/{store_id}/{date}/{unit}.html
    旧形式: data/raw/{date}/{unit}.html

    旧形式はHTML内URLからstore_idを推定し、既存データも再利用できるようにする。
    """
    parent = html_path.parent
    grandparent = parent.parent

    if DATE_PATTERN.match(parent.name) and grandparent.name.isdigit():
        return grandparent.name

    match = STORE_ID_PATTERN.search(html)
    return match.group(1) if match else None


def parse_one_file(html_path: Path, master):
    target_date_str = html_path.parent.name
    if not DATE_PATTERN.match(target_date_str):
        print(f"[SKIP] 日付フォルダではありません: {html_path}")
        return []

    target_date = date.fromisoformat(target_date_str)

    try:
        unit = int(html_path.stem)
    except ValueError:
        print(f"[SKIP] 台番号として解釈できません: {html_path}")
        return []

    html = html_path.read_text(encoding="utf-8")
    store_id = detect_store_id(html_path, html)
    if not store_id:
        print(f"[WARN] store_idを特定できません: {html_path}")
        return []

    assignment = resolve_assignment(master, store_id, unit, target_date)
    if assignment is None:
        print(
            f"[WARN] 台マスタに該当なし: "
            f"{target_date_str} store_id={store_id} unit={unit}"
        )
        return []

    soup = BeautifulSoup(html, "html.parser")

    model_node = soup.select_one("#pachinkoTi strong")
    actual_model = model_node.get_text(" ", strip=True) if model_node else ""

    if normalize_model(actual_model) != normalize_model(assignment.model):
        print(
            f"[WARN] 機種名不一致のためSKIP: {html_path} "
            f"expected={assignment.model!r}, actual={actual_model!r}"
        )
        return []

    store_node = soup.select_one("#shopInfo dt")
    store_name = store_node.get_text(" ", strip=True) if store_node else ""
    # 「（店舗情報はこちら）」などを後段で分析しやすいよう簡易除去
    store_name = re.sub(r"\s*（.*$", "", store_name).strip()

    graph = soup.select_one(
        f'[data-slamp-graph-date="{target_date_str}"]'
    )
    if graph is None:
        print(f"[WARN] {html_path}: {target_date_str} のグラフが見つかりません")
        return []

    script = graph.find("script", attrs={"data-plot-graph-script": True})
    if script is None:
        print(f"[WARN] {html_path}: グラフ描画scriptが見つかりません")
        return []

    points = POINT_PATTERN.findall(script.get_text())

    rows = []
    for timestamp, difference in points:
        if not timestamp.startswith(target_date_str):
            continue

        rows.append(
            {
                "machine_id": assignment.machine_id,
                "store_id": store_id,
                "store_name": store_name,
                "model": assignment.model,
                "unit": unit,
                "date": target_date_str,
                "timestamp": timestamp,
                "difference": int(difference),
                "source_file": str(html_path),
            }
        )

    return rows


def main():
    master = load_assignments(UNIT_MAPPING_CSV)
    html_files = sorted(RAW_DIR.rglob("*.html"))

    if not html_files:
        print(f"[ERROR] HTMLが見つかりません: {RAW_DIR}")
        return

    print(f"[INFO] HTMLファイル: {len(html_files)}件")

    dedup = {}

    for index, html_path in enumerate(html_files, start=1):
        print(f"[PARSE] {index}/{len(html_files)} {html_path}")

        for row in parse_one_file(html_path, master):
            # 台番号ではなくmachine_idを論理的な個体識別子として重複排除する。
            key = (
                row["machine_id"],
                row["date"],
                row["timestamp"],
            )
            dedup[key] = row

    rows = sorted(
        dedup.values(),
        key=lambda r: (
            r["store_id"],
            r["machine_id"],
            r["date"],
            r["timestamp"],
        ),
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "machine_id",
        "store_id",
        "store_name",
        "model",
        "unit",
        "date",
        "timestamp",
        "difference",
        "source_file",
    ]

    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\n" + "=" * 60)
    print(f"[OUTPUT] {OUTPUT_CSV}")
    print(f"[ROWS] {len(rows):,}行")


if __name__ == "__main__":
    main()
