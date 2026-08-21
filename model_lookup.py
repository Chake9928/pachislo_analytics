"""models テーブルから model_id を解決する。

収集・パス整理で機種フォルダ名に DB の model_id を使う。
unit_mapping.csv の機種名と models.source_model_name / model_name を照合する。

実行:
    なし（ライブラリ）。先に python scripts/db/init_master.py が必要。
"""

from machine_master import normalize_model
from supabase_client import create_supabase_client


def load_model_id_map(db=None):
    """(source_system, 正規化機種名) -> model_id"""
    if db is None:
        db = create_supabase_client()

    rows = (
        db.table("models")
        .select("model_id,source_system,source_model_name,model_name")
        .execute()
        .data
        or []
    )
    mapping = {}
    for row in rows:
        source_system = row["source_system"]
        model_id = row["model_id"]
        for name in (row.get("source_model_name"), row.get("model_name")):
            if not name:
                continue
            mapping[(source_system, normalize_model(name))] = model_id
    return mapping


def resolve_model_id(source_system: str, model_name: str, model_id_map) -> int:
    key = (source_system, normalize_model(model_name))
    model_id = model_id_map.get(key)
    if model_id is None:
        raise RuntimeError(
            "models に機種がありません: "
            f"source_system={source_system} model={model_name!r}。"
            "先に python scripts/db/init_master.py を実行してください。"
        )
    return model_id
