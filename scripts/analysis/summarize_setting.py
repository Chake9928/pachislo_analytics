"""設定判別CSVから summary.html を生成する。

analyze_setting.py が出力した店舗×機種ディレクトリを読み、
カウント表・ヒートマップ・考察を1枚のHTMLにまとめる。

実行:
    python scripts/analysis/summarize_setting.py
    python scripts/analysis/summarize_setting.py data/setting/100928/1
    python scripts/analysis/summarize_setting.py --store-id 100928 --model-id 1

引数:
    path  設定CSVディレクトリ。省略時は data/setting 配下を走査

オプション:
    --store-id  店舗ID。path未指定時の絞り込み
    --model-id  機種ID。path未指定時の絞り込み
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import SETTING_DIR
from setting_summary import CSV_FILES, write_setting_summary


def parse_args():
    parser = argparse.ArgumentParser(description="設定判別CSVからHTMLサマリを生成する")
    parser.add_argument(
        "path",
        nargs="?",
        help="設定CSVディレクトリ。省略時は data/setting 配下",
    )
    parser.add_argument("--store-id", help="店舗ID")
    parser.add_argument("--model-id", help="機種ID")
    return parser.parse_args()


def iter_setting_dirs(root: Path, store_id=None, model_id=None):
    root = Path(root)
    if (root / "store_total.csv").exists():
        yield root
        return
    for store_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if store_id and store_dir.name != str(store_id):
            continue
        for model_dir in sorted(p for p in store_dir.iterdir() if p.is_dir()):
            if model_id and model_dir.name != str(model_id):
                continue
            if all((model_dir / name).exists() for name in CSV_FILES):
                yield model_dir


def main():
    args = parse_args()
    root = Path(args.path) if args.path else SETTING_DIR
    dirs = list(iter_setting_dirs(root, args.store_id, args.model_id))
    if not dirs:
        raise SystemExit(f"設定CSVディレクトリが見つかりません: {root}")

    print("[MODE] 設定判別HTMLサマリ")
    for setting_dir in dirs:
        path = write_setting_summary(setting_dir)
        print(f"[SAVE] {path}")


if __name__ == "__main__":
    main()
