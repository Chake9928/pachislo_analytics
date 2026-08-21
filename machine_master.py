"""unit_mapping.csv の読込・整合性チェック・日付に対する配置解決。

台番号ではなく machine_id を実台の不変IDとして扱い、
valid_from / valid_to で対象日の配置を解決する。

実行:
    単体では実行しない。検証は python scripts/db/validate_master.py
"""

import csv
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional


MACHINE_ID_PATTERN = re.compile(r"^M\d+$")
VALID_MACHINE_TYPES = {"slot", "pachinko", "unknown"}


@dataclass(frozen=True)
class UnitAssignment:
    machine_id: str               # 論理実台コード: M0001 等
    store_id: str                 # 取得元店舗ID: 100928 等
    model: str                    # 取得元機種名
    unit: int                     # 台番号
    valid_from: Optional[date]
    valid_to: Optional[date]
    source_system: str = "daidata"
    store_name: str = ""
    machine_type: str = "unknown"
    play_rate_yen: Optional[Decimal] = None
    line_no: int = 0

    def is_active(self, target_date: date) -> bool:
        if self.valid_from is not None and target_date < self.valid_from:
            return False
        if self.valid_to is not None and target_date > self.valid_to:
            return False
        return True


def normalize_model(value: str) -> str:
    """表示揺れの影響を減らして機種名を比較する。"""
    value = unicodedata.normalize("NFKC", value or "")
    return "".join(value.split()).lower()


def _parse_optional_date(value: str, field_name: str, line_no: int):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"unit_mapping.csv {line_no}行目: {field_name}={value!r} は YYYY-MM-DD 形式ではありません"
        ) from exc


def _parse_optional_decimal(value: str, field_name: str, line_no: int):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(
            f"unit_mapping.csv {line_no}行目: {field_name}={value!r} は数値ではありません"
        ) from exc


def _interval(assignment: UnitAssignment):
    return (
        assignment.valid_from or date.min,
        assignment.valid_to or date.max,
    )


def _overlap(a: UnitAssignment, b: UnitAssignment) -> bool:
    a_start, a_end = _interval(a)
    b_start, b_end = _interval(b)
    return max(a_start, b_start) <= min(a_end, b_end)


def validate_assignments(assignments):
    errors = []

    # 1台のmachine_idが同じ日に複数の配置を持たないこと。
    by_machine = {}
    for a in assignments:
        by_machine.setdefault(a.machine_id, []).append(a)

    for machine_id, rows in by_machine.items():
        # 同一machine_idは同一機種として扱う。
        model_keys = {normalize_model(r.model) for r in rows}
        if len(model_keys) > 1:
            errors.append(
                f"machine_id={machine_id} に複数機種が割り当てられています"
            )

        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                if _overlap(left, right):
                    errors.append(
                        f"machine_id={machine_id} の有効期間が重複しています "
                        f"(CSV {left.line_no}行目 と {right.line_no}行目)"
                    )

    # 同一店舗・同一台番号が同じ日に複数machine_idへ割り当たらないこと。
    by_store_unit = {}
    for a in assignments:
        by_store_unit.setdefault((a.source_system, a.store_id, a.unit), []).append(a)

    for (source_system, store_id, unit), rows in by_store_unit.items():
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                if _overlap(left, right):
                    errors.append(
                        f"source={source_system}, store_id={store_id}, unit={unit} の有効期間が重複しています "
                        f"(machine_id={left.machine_id}/{right.machine_id})"
                    )

    # 同一取得元店舗IDに異なる店舗名を混在させない。
    store_names = {}
    for a in assignments:
        if not a.store_name:
            continue
        key = (a.source_system, a.store_id)
        store_names.setdefault(key, set()).add(a.store_name)
    for key, names in store_names.items():
        if len(names) > 1:
            errors.append(
                f"source={key[0]}, store_id={key[1]} に複数の店舗名があります: {sorted(names)}"
            )

    for a in assignments:
        if a.valid_from and a.valid_to and a.valid_from > a.valid_to:
            errors.append(f"CSV {a.line_no}行目: valid_from が valid_to より後です")
        if a.unit <= 0:
            errors.append(f"CSV {a.line_no}行目: unit は1以上である必要があります")
        if a.play_rate_yen is not None and a.play_rate_yen < 0:
            errors.append(f"CSV {a.line_no}行目: play_rate_yen は0以上である必要があります")

    if errors:
        raise ValueError("unit_mapping.csv に矛盾があります:\n- " + "\n- ".join(errors))


def load_assignments(csv_path: Path):
    if not csv_path.exists():
        raise FileNotFoundError(f"台マスタが見つかりません: {csv_path}")

    assignments = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {
            "machine_id",
            "store_id",
            "model",
            "unit",
            "valid_from",
            "valid_to",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"unit_mapping.csv に必須列がありません: {sorted(missing)}")

        fieldnames = set(reader.fieldnames or [])

        for line_no, row in enumerate(reader, start=2):
            machine_id = (row.get("machine_id") or "").strip()
            store_id = (row.get("store_id") or "").strip()
            model = (row.get("model") or "").strip()
            source_system = (row.get("source_system") or "daidata").strip() or "daidata"
            store_name = (row.get("store_name") or "").strip()
            machine_type = (row.get("machine_type") or "unknown").strip().lower() or "unknown"

            if not MACHINE_ID_PATTERN.match(machine_id):
                raise ValueError(
                    f"unit_mapping.csv {line_no}行目: machine_id={machine_id!r} が不正です"
                )
            if not store_id.isdigit():
                raise ValueError(
                    f"unit_mapping.csv {line_no}行目: store_id={store_id!r} が不正です"
                )
            if not model:
                raise ValueError(f"unit_mapping.csv {line_no}行目: model が空です")
            if machine_type not in VALID_MACHINE_TYPES:
                raise ValueError(
                    f"unit_mapping.csv {line_no}行目: machine_type={machine_type!r} が不正です"
                )

            try:
                unit = int(row.get("unit"))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"unit_mapping.csv {line_no}行目: unit={row.get('unit')!r} が不正です"
                ) from exc

            play_rate_yen = None
            if "play_rate_yen" in fieldnames:
                play_rate_yen = _parse_optional_decimal(
                    row.get("play_rate_yen"), "play_rate_yen", line_no
                )

            assignments.append(
                UnitAssignment(
                    machine_id=machine_id,
                    store_id=store_id,
                    model=model,
                    unit=unit,
                    valid_from=_parse_optional_date(row.get("valid_from"), "valid_from", line_no),
                    valid_to=_parse_optional_date(row.get("valid_to"), "valid_to", line_no),
                    source_system=source_system,
                    store_name=store_name,
                    machine_type=machine_type,
                    play_rate_yen=play_rate_yen,
                    line_no=line_no,
                )
            )

    validate_assignments(assignments)
    return assignments


def get_assignments_for_date(assignments, target_date: date):
    return sorted(
        [a for a in assignments if a.is_active(target_date)],
        key=lambda a: (a.source_system, a.store_id, a.unit, a.machine_id),
    )


def filter_assignments(assignments, store_id=None, model=None):
    """store_id / 機種名で配置を絞り込む。未指定の軸は全件対象。

    機種名は normalize_model で比較する（全角半角・空白の揺れを無視）。
    指定した軸に1件も該当しない場合は ValueError。
    """
    filtered = list(assignments)
    store_id = str(store_id).strip() if store_id is not None else ""
    model = str(model).strip() if model is not None else ""

    if store_id:
        by_store = [a for a in filtered if a.store_id == store_id]
        if not by_store:
            available = sorted({a.store_id for a in filtered})
            raise ValueError(
                f"store_id={store_id} に該当する配置がありません。"
                f" 候補: {available or '(なし)'}"
            )
        filtered = by_store

    if model:
        model_key = normalize_model(model)
        by_model = [
            a for a in filtered if normalize_model(a.model) == model_key
        ]
        if not by_model:
            available = sorted({a.model for a in filtered})
            raise ValueError(
                f"model={model!r} に該当する配置がありません。"
                f" 候補: {available or '(なし)'}"
            )
        filtered = by_model

    return filtered


def resolve_assignment(assignments, store_id: str, unit: int, target_date: date, source_system="daidata"):
    matches = [
        a
        for a in assignments
        if a.source_system == source_system
        and a.store_id == str(store_id)
        and a.unit == int(unit)
        and a.is_active(target_date)
    ]

    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(
            f"{target_date} source={source_system} store_id={store_id} unit={unit} に複数のマスタが該当します"
        )
    return matches[0]


def resolve_assignment_by_machine_id(assignments, machine_id: str, target_date: date):
    matches = [
        a
        for a in assignments
        if a.machine_id == machine_id and a.is_active(target_date)
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(
            f"{target_date} machine_id={machine_id} に複数のマスタが該当します"
        )
    return matches[0]
