"""保存済みHTMLを解析し、Supabaseへ INSERT / UPSERT する。

data/raw 配下（または指定パス）のHTMLを html_parser で構造化し、
日次サマリ・大当たり・スランプ等をDBへ投入する。--dry-run では書き込まない。

実行:
    python scripts/db/ingest_html.py
    python scripts/db/ingest_html.py --dry-run
    python scripts/db/ingest_html.py C:/path/to/3075.html --data-date 2026-08-12
    python scripts/db/ingest_html.py C:/path/to/3075.html --data-date 2026-08-12 --dry-run
    python scripts/db/ingest_html.py C:/path/to/3075.html --data-date 2026-08-12 --dry-run --debug-json data/processed/3075_debug.json

引数:
    path            HTMLファイルまたはrawディレクトリ。省略時 data/raw

オプション:
    --data-date     日付フォルダ外の単体HTMLを解析するときの対象日 YYYY-MM-DD
    --dry-run       DBへ書き込まず解析結果だけ表示する
    --debug-json    dry-run時に解析結果JSONを保存するパス（単体HTML向け）
"""

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import PARSER_VERSION, RAW_DIR, UNIT_MAPPING_CSV
from html_parser import parse_html_file
from machine_master import load_assignments
from supabase_client import create_supabase_client
from supabase_writer import SupabaseWriter


def list_html_files(path: Path):
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.html"))


def create_run(db, files):
    payload = {
        "mode": "manual",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "collector_version": "offline-html-import",
        "target_store_count": 0,
        "target_machine_count": len(files),
        "success_count": 0,
        "failure_count": 0,
        "status": "running",
    }
    response = db.table("collection_runs").insert(payload).execute()
    return response.data[0]["run_id"]


def finish_run(db, run_id, success, failure, target_store_count):
    if failure == 0:
        status = "success"
    elif success > 0:
        status = "partial"
    else:
        status = "error"
    db.table("collection_runs").update(
        {
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "success_count": success,
            "failure_count": failure,
            "target_store_count": target_store_count,
            "status": status,
        }
    ).eq("run_id", run_id).execute()


def main():
    parser = argparse.ArgumentParser(description="保存HTMLを解析しSupabaseへINSERT/UPSERT")
    parser.add_argument(
        "path",
        nargs="?",
        default=str(RAW_DIR),
        help="HTMLファイルまたはrawディレクトリ。省略時 data/raw",
    )
    parser.add_argument(
        "--data-date",
        help="日付フォルダ外の単体HTMLを解析するときの対象日 YYYY-MM-DD",
    )
    parser.add_argument("--dry-run", action="store_true", help="DBへ書き込まず解析結果だけ表示")
    parser.add_argument(
        "--debug-json",
        help="dry-run時に解析結果JSONを保存するパス（単体HTML向け）",
    )
    args = parser.parse_args()

    input_path = Path(args.path)
    files = list_html_files(input_path)
    if not files:
        raise SystemExit(f"HTMLが見つかりません: {input_path}")

    override_date = date.fromisoformat(args.data_date) if args.data_date else None
    if override_date and len(files) > 1:
        raise SystemExit("--data-date は単体HTMLの解析時だけ使用してください")

    master = load_assignments(UNIT_MAPPING_CSV)
    print(f"[INFO] HTML files={len(files)} master rows={len(master)} parser={PARSER_VERSION}")

    db = None if args.dry_run else create_supabase_client()
    run_id = None if args.dry_run else create_run(db, files)
    writer = None if args.dry_run else SupabaseWriter(db, run_id=run_id)

    success = 0
    failure = 0
    last_page = None
    observed_stores = set()

    try:
        for i, path in enumerate(files, start=1):
            print(f"\n[PARSE] {i}/{len(files)} {path}")
            try:
                page = parse_html_file(
                    path,
                    master,
                    requested_data_date=override_date,
                )
                last_page = page
                observed_stores.add((page.source_system, page.source_store_id))
                print(
                    f"[OK] {page.machine_code} store={page.source_store_id} unit={page.unit_number} "
                    f"date={page.requested_data_date} summaries={1 + len(page.related_summaries)} "
                    f"events={len(page.jackpot_events)} slump={len(page.slump_points)}"
                )
                if writer:
                    source_page_id = writer.write_page(page, path)
                    print(f"[DB] source_page_id={source_page_id}")
                success += 1
            except Exception as exc:
                failure += 1
                print(f"[ERROR] {path}: {exc}")

        if args.dry_run and args.debug_json and last_page and len(files) == 1:
            out = Path(args.debug_json)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(last_page.debug_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[DEBUG JSON] {out}")
    finally:
        if db and run_id:
            finish_run(db, run_id, success, failure, len(observed_stores))

    print("\n" + "=" * 60)
    print(f"SUCCESS={success} FAILURE={failure}")
    if failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
