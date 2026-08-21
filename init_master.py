"""unit_mapping.csv を Supabase のマスタテーブルへ同期する。

stores / models / machines / machine_placements を INSERT または更新する。
同じCSVで再実行可能。実台の model_id 付け替えは自動では行わない。

実行:
    python init_master.py --dry-run
    python init_master.py

オプション:
    --dry-run  DBを更新せず、同期内容だけ表示する
"""

import argparse
from collections import OrderedDict
from datetime import date
from decimal import Decimal

from config import UNIT_MAPPING_CSV
from machine_master import UnitAssignment, load_assignments
from supabase_client import create_supabase_client, first_or_none


def _iso(value):
    return value.isoformat() if value is not None else None


def _decimal(value):
    return float(value) if isinstance(value, Decimal) else value


def unique_preserve(items, key):
    result = OrderedDict()
    for item in items:
        result.setdefault(key(item), item)
    return list(result.values())


class MasterSync:
    def __init__(self, supabase, dry_run=False):
        self.db = supabase
        self.dry_run = dry_run
        self.store_ids = {}
        self.model_ids = {}
        self.machine_ids = {}

    def sync_store(self, a: UnitAssignment):
        key = (a.source_system, a.store_id)
        if key in self.store_ids:
            return self.store_ids[key]

        payload = {
            "source_system": a.source_system,
            "source_store_id": int(a.store_id),
            "store_name": a.store_name or f"store_{a.store_id}",
            "is_active": True,
        }
        print(f"[STORE] {key} {payload['store_name']}")
        if self.dry_run:
            synthetic = -(len(self.store_ids) + 1)
            self.store_ids[key] = synthetic
            return synthetic

        row = first_or_none(
            self.db.table("stores")
            .select("store_id,store_name")
            .eq("source_system", a.source_system)
            .eq("source_store_id", int(a.store_id))
            .limit(1)
            .execute()
        )
        if row:
            self.db.table("stores").update(payload).eq("store_id", row["store_id"]).execute()
            store_id = row["store_id"]
        else:
            inserted = self.db.table("stores").insert(payload).execute()
            store_id = inserted.data[0]["store_id"]

        self.store_ids[key] = store_id
        return store_id

    def sync_model(self, a: UnitAssignment):
        key = (a.source_system, a.model)
        if key in self.model_ids:
            return self.model_ids[key]

        payload = {
            "source_system": a.source_system,
            "source_model_name": a.model,
            "model_name": a.model,
            "machine_type": a.machine_type or "unknown",
        }
        print(f"[MODEL] {key} type={payload['machine_type']}")
        if self.dry_run:
            synthetic = -(len(self.model_ids) + 1)
            self.model_ids[key] = synthetic
            return synthetic

        row = first_or_none(
            self.db.table("models")
            .select("model_id")
            .eq("source_system", a.source_system)
            .eq("source_model_name", a.model)
            .limit(1)
            .execute()
        )
        if row:
            self.db.table("models").update(payload).eq("model_id", row["model_id"]).execute()
            model_id = row["model_id"]
        else:
            inserted = self.db.table("models").insert(payload).execute()
            model_id = inserted.data[0]["model_id"]

        self.model_ids[key] = model_id
        return model_id

    def sync_machine(self, a: UnitAssignment, model_id):
        if a.machine_id in self.machine_ids:
            return self.machine_ids[a.machine_id]

        print(f"[MACHINE] {a.machine_id} model={a.model}")
        if self.dry_run:
            synthetic = -(len(self.machine_ids) + 1)
            self.machine_ids[a.machine_id] = synthetic
            return synthetic

        row = first_or_none(
            self.db.table("machines")
            .select("machine_id,model_id")
            .eq("machine_code", a.machine_id)
            .limit(1)
            .execute()
        )

        if row:
            if row["model_id"] != model_id:
                raise RuntimeError(
                    f"machine_code={a.machine_id} はDB上で別model_id={row['model_id']}に紐付いています。"
                    "実台IDの付け替えは自動では行いません。"
                )
            machine_id = row["machine_id"]
            self.db.table("machines").update({"status": "active"}).eq("machine_id", machine_id).execute()
        else:
            payload = {
                "machine_code": a.machine_id,
                "model_id": model_id,
                "first_seen_date": _iso(a.valid_from),
                "last_seen_date": None,
                "status": "active",
            }
            inserted = self.db.table("machines").insert(payload).execute()
            machine_id = inserted.data[0]["machine_id"]

        self.machine_ids[a.machine_id] = machine_id
        return machine_id

    def sync_placement(self, a: UnitAssignment, machine_id, store_id):
        payload = {
            "machine_id": machine_id,
            "store_id": store_id,
            "unit_number": a.unit,
            "play_rate_yen": _decimal(a.play_rate_yen),
            "valid_from": _iso(a.valid_from),
            "valid_to": _iso(a.valid_to),
            "source": "unit_mapping.csv",
        }
        print(
            f"[PLACEMENT] {a.machine_id} store={a.store_id} unit={a.unit} "
            f"{payload['valid_from'] or '-inf'}..{payload['valid_to'] or '+inf'}"
        )
        if self.dry_run:
            return

        # valid_from=NULL を含むため、UNIQUE制約だけに依存せず既存行を明示検索する。
        candidates = (
            self.db.table("machine_placements")
            .select("placement_id,valid_from,valid_to")
            .eq("machine_id", machine_id)
            .eq("store_id", store_id)
            .eq("unit_number", a.unit)
            .execute()
        ).data or []

        matched = None
        for row in candidates:
            if row.get("valid_from") == payload["valid_from"]:
                matched = row
                break

        if matched:
            self.db.table("machine_placements").update(payload).eq(
                "placement_id", matched["placement_id"]
            ).execute()
        else:
            self.db.table("machine_placements").insert(payload).execute()


def main():
    parser = argparse.ArgumentParser(description="unit_mapping.csv をSupabaseマスタへ同期")
    parser.add_argument("--dry-run", action="store_true", help="DB更新せず同期内容だけ表示")
    args = parser.parse_args()

    assignments = load_assignments(UNIT_MAPPING_CSV)
    print(f"[INFO] master rows={len(assignments)}")

    db = None if args.dry_run else create_supabase_client()
    sync = MasterSync(db, dry_run=args.dry_run)

    # 店舗・機種を先に同期。
    for a in unique_preserve(assignments, lambda x: (x.source_system, x.store_id)):
        sync.sync_store(a)
    for a in unique_preserve(assignments, lambda x: (x.source_system, x.model)):
        sync.sync_model(a)

    # 実台と配置履歴。
    for a in assignments:
        store_id = sync.sync_store(a)
        model_id = sync.sync_model(a)
        machine_id = sync.sync_machine(a, model_id)
        sync.sync_placement(a, machine_id, store_id)

    print("\n[OK] master sync completed" + (" (dry-run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
