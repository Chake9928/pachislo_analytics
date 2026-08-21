"""解析済みページを Supabase 各テーブルへ INSERT / UPSERT する。

source_pages / machine_daily_summaries / jackpot_events / slump_points 等へ
冪等に書き込む。ingest_html.py から利用する。単体では実行しない。

実行:
    なし（ライブラリ）。投入は python ingest_html.py
"""

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from config import PARSER_VERSION
from supabase_client import first_or_none


BATCH_SIZE = 500


def _iso(value):
    return value.isoformat() if value is not None else None


def chunks(rows, size=BATCH_SIZE):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


class SupabaseWriter:
    def __init__(self, supabase, run_id=None):
        self.db = supabase
        self.run_id = run_id
        self._store_cache = {}
        self._machine_cache = {}
        self._model_cache = {}

    def resolve_store_id(self, source_system, source_store_id):
        key = (source_system, str(source_store_id))
        if key in self._store_cache:
            return self._store_cache[key]
        row = first_or_none(
            self.db.table("stores")
            .select("store_id")
            .eq("source_system", source_system)
            .eq("source_store_id", int(source_store_id))
            .limit(1)
            .execute()
        )
        if not row:
            raise RuntimeError(
                f"stores未登録: source={source_system}, source_store_id={source_store_id}. "
                "先に python init_master.py を実行してください。"
            )
        self._store_cache[key] = row["store_id"]
        return row["store_id"]

    def resolve_machine_id(self, machine_code):
        if machine_code in self._machine_cache:
            return self._machine_cache[machine_code]
        row = first_or_none(
            self.db.table("machines")
            .select("machine_id,model_id")
            .eq("machine_code", machine_code)
            .limit(1)
            .execute()
        )
        if not row:
            raise RuntimeError(
                f"machines未登録: machine_code={machine_code}. 先に python init_master.py を実行してください。"
            )
        self._machine_cache[machine_code] = row
        return row

    def update_observed_master_values(self, page, store_id, machine_row):
        # HTMLで確認できた最新表示名/ガイドURLをマスタへ反映する。
        if page.store_name:
            self.db.table("stores").update({"store_name": page.store_name}).eq("store_id", store_id).execute()

        model_id = machine_row["model_id"]
        payload = {
            "source_model_name": page.source_model_name,
            "model_name": page.source_model_name,
            "machine_type": page.machine_type if page.machine_type in {"slot", "pachinko", "unknown"} else "unknown",
            "guide_url": page.guide_url,
        }
        self.db.table("models").update(payload).eq("model_id", model_id).execute()

    def get_or_create_source_page(self, page, source_path: Path, store_id, machine_id):
        query = (
            self.db.table("source_pages")
            .select("source_page_id")
            .eq("store_id", store_id)
            .eq("machine_id", machine_id)
            .eq("unit_number", page.unit_number)
            .eq("requested_data_date", page.requested_data_date.isoformat())
            .eq("content_hash", page.content_hash)
            .limit(1)
            .execute()
        )
        row = first_or_none(query)

        payload = {
            "run_id": self.run_id,
            "store_id": store_id,
            "machine_id": machine_id,
            "unit_number": page.unit_number,
            "requested_data_date": page.requested_data_date.isoformat(),
            "source_url": page.source_url,
            "http_status": 200,
            "fetched_at": page.fetched_at.isoformat(),
            "source_updated_at": _iso(page.source_updated_at),
            "content_hash": page.content_hash,
            "raw_storage_path": str(source_path),
            "parser_version": PARSER_VERSION,
            "parse_status": "pending",
            "error_message": None,
        }

        if row:
            source_page_id = row["source_page_id"]
            self.db.table("source_pages").update(payload).eq(
                "source_page_id", source_page_id
            ).execute()
            return source_page_id

        response = self.db.table("source_pages").insert(payload).execute()
        return response.data[0]["source_page_id"]

    def mark_source_page(self, source_page_id, status, error_message=None):
        self.db.table("source_pages").update(
            {
                "parse_status": status,
                "error_message": error_message,
                "parser_version": PARSER_VERSION,
            }
        ).eq("source_page_id", source_page_id).execute()

    def upsert_store_snapshot(self, page, store_id, source_page_id):
        s = page.store_snapshot
        if s is None:
            return
        payload = {
            "store_id": store_id,
            "snapshot_date": s.snapshot_date.isoformat(),
            "pachinko_count": s.pachinko_count,
            "slot_count": s.slot_count,
            "source_page_id": source_page_id,
            "observed_at": s.observed_at.isoformat(),
        }
        self.db.table("store_daily_snapshots").upsert(
            payload,
            on_conflict="store_id,snapshot_date",
        ).execute()

    def upsert_summaries(self, page, store_id, machine_id, source_page_id):
        rows = []
        for s in [page.primary_summary, *page.related_summaries]:
            rows.append(
                {
                    "machine_id": machine_id,
                    "store_id": store_id,
                    "data_date": s.data_date.isoformat(),
                    "unit_number": page.unit_number,
                    "play_rate_yen": page.play_rate_yen,
                    "bb_count": s.bb_count,
                    "rb_count": s.rb_count,
                    "art_count": s.art_count,
                    "current_start": s.current_start,
                    "max_hold": s.max_hold,
                    "total_start": s.total_start,
                    "prev_day_final_start": s.prev_day_final_start,
                    "combined_prob_denominator": s.combined_prob_denominator,
                    "bb_prob_denominator": s.bb_prob_denominator,
                    "rb_prob_denominator": s.rb_prob_denominator,
                    "art_prob_denominator": s.art_prob_denominator,
                    "source_updated_at": _iso(s.source_updated_at),
                    "observed_at": page.fetched_at.isoformat(),
                    "source_page_id": source_page_id,
                    "extra_metrics": {"source_kind": s.source_kind},
                }
            )
        if rows:
            self.db.table("machine_daily_summaries").upsert(
                rows,
                on_conflict="machine_id,data_date",
            ).execute()

    def upsert_jackpot_events(self, page, store_id, machine_id, source_page_id):
        rows = [
            {
                "machine_id": machine_id,
                "store_id": store_id,
                "data_date": e.data_date.isoformat(),
                "unit_number": page.unit_number,
                "event_seq": e.event_seq,
                "source_row_order": e.source_row_order,
                "jackpot_no": e.jackpot_no,
                "start_count": e.start_count,
                "payout": e.payout,
                "event_type": e.event_type,
                "event_time": _iso(e.event_time),
                "event_at": _iso(e.event_at),
                "source_page_id": source_page_id,
            }
            for e in page.jackpot_events
        ]
        for batch in chunks(rows):
            self.db.table("jackpot_events").upsert(
                batch,
                on_conflict="machine_id,data_date,event_seq",
            ).execute()

    def upsert_slump_points(self, page, store_id, machine_id, source_page_id):
        rows = [
            {
                "machine_id": machine_id,
                "store_id": store_id,
                "data_date": p.data_date.isoformat(),
                "unit_number": page.unit_number,
                "point_seq": p.point_seq,
                "sampled_at": p.sampled_at.isoformat(),
                "slump_value": p.slump_value,
                "source_page_id": source_page_id,
            }
            for p in page.slump_points
        ]
        for batch in chunks(rows):
            self.db.table("slump_points").upsert(
                batch,
                on_conflict="machine_id,data_date,sampled_at",
            ).execute()

    def upsert_daily_metrics(self, page, machine_id):
        target = page.requested_data_date
        points = [p for p in page.slump_points if p.data_date == target]
        events = page.jackpot_events

        values = [p.slump_value for p in points]
        starts = [e.start_count for e in events if e.start_count is not None]
        payouts = [e.payout for e in events if e.payout is not None]

        payload = {
            "machine_id": machine_id,
            "data_date": target.isoformat(),
            "slump_final_value": values[-1] if values else None,
            "slump_max_value": max(values) if values else None,
            "slump_min_value": min(values) if values else None,
            "slump_range": (max(values) - min(values)) if values else None,
            "slump_point_count": len(values),
            "first_sample_at": _iso(points[0].sampled_at) if points else None,
            "last_sample_at": _iso(points[-1].sampled_at) if points else None,
            "max_start_count": max(starts) if starts else None,
            "avg_start_count": mean(starts) if starts else None,
            "max_event_payout": max(payouts) if payouts else None,
            "event_payout_sum": sum(payouts) if payouts else None,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "calculation_version": PARSER_VERSION,
        }
        self.db.table("machine_daily_metrics").upsert(
            payload,
            on_conflict="machine_id,data_date",
        ).execute()

    def write_page(self, page, source_path: Path):
        store_id = self.resolve_store_id(page.source_system, page.source_store_id)
        machine_row = self.resolve_machine_id(page.machine_code)
        machine_id = machine_row["machine_id"]

        self.update_observed_master_values(page, store_id, machine_row)
        source_page_id = self.get_or_create_source_page(
            page, source_path, store_id, machine_id
        )

        try:
            self.upsert_store_snapshot(page, store_id, source_page_id)
            self.upsert_summaries(page, store_id, machine_id, source_page_id)
            self.upsert_jackpot_events(page, store_id, machine_id, source_page_id)
            self.upsert_slump_points(page, store_id, machine_id, source_page_id)
            self.upsert_daily_metrics(page, machine_id)
            self.mark_source_page(source_page_id, "success")
            return source_page_id
        except Exception as exc:
            self.mark_source_page(source_page_id, "error", str(exc)[:4000])
            raise
