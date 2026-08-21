"""raw HTML とスランプ出力のパス規則。

raw:
    data/raw/{store_id}/{model_id}/{YYYY-MM-DD}/{machine_id}.html
    旧形式も読み取り可能:
        data/raw/{store_id}/{YYYY-MM-DD}/{unit}.html
        data/raw/{YYYY-MM-DD}/{unit}.html

スランプ:
    data/slump/{store_id}/{model_id}/01_daily_by_machine/{YYYY-MM-DD}/
    data/slump/{store_id}/{model_id}/02_chained_by_machine/
    data/slump/{store_id}/{model_id}/03_daily_average/
    data/slump/{store_id}/{model_id}/04_chained_average/
    data/slump/{store_id}/{model_id}/series/

実行:
    なし（ライブラリ）。
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional
import re


DATE_DIR_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MACHINE_CODE_PATTERN = re.compile(r"^M\d+$")


@dataclass(frozen=True)
class RawHtmlLocation:
    store_id: Optional[str]
    model_id: Optional[str]
    data_date: Optional[date]
    machine_code: Optional[str]
    unit: Optional[int]


def raw_html_path(
    raw_dir: Path,
    store_id: str,
    model_id,
    data_date: date,
    machine_id: str,
) -> Path:
    return (
        Path(raw_dir)
        / str(store_id)
        / str(model_id)
        / data_date.isoformat()
        / f"{machine_id}.html"
    )


def parse_raw_html_path(path: Path) -> RawHtmlLocation:
    """ファイルパスから store / model / 日付 / 実台を推定する。"""
    path = Path(path)
    parent = path.parent
    data_date = None
    store_id = None
    model_id = None

    if DATE_DIR_PATTERN.match(parent.name):
        data_date = date.fromisoformat(parent.name)
        grandparent = parent.parent
        great = grandparent.parent
        if grandparent.name.isdigit() and great.name.isdigit():
            # data/raw/{store_id}/{model_id}/{date}/{machine_id}.html
            store_id = great.name
            model_id = grandparent.name
        elif grandparent.name.isdigit():
            # data/raw/{store_id}/{date}/{unit}.html
            store_id = grandparent.name

    machine_code = None
    unit = None
    if MACHINE_CODE_PATTERN.match(path.stem):
        machine_code = path.stem
    elif path.stem.isdigit():
        unit = int(path.stem)

    return RawHtmlLocation(
        store_id=store_id,
        model_id=model_id,
        data_date=data_date,
        machine_code=machine_code,
        unit=unit,
    )


def slump_store_model_dir(root: Path, store_id, model_id) -> Path:
    return Path(root) / str(store_id) / str(model_id)


def slump_daily_machine_dir(
    root: Path,
    data_date: date,
    store_id,
    model_id,
) -> Path:
    return (
        slump_store_model_dir(root, store_id, model_id)
        / "01_daily_by_machine"
        / data_date.isoformat()
    )


def slump_chained_machine_dir(root: Path, store_id, model_id) -> Path:
    return slump_store_model_dir(root, store_id, model_id) / "02_chained_by_machine"


def slump_daily_average_dir(root: Path, store_id, model_id) -> Path:
    return slump_store_model_dir(root, store_id, model_id) / "03_daily_average"


def slump_chained_average_dir(root: Path, store_id, model_id) -> Path:
    return slump_store_model_dir(root, store_id, model_id) / "04_chained_average"


def slump_series_dir(root: Path, store_id, model_id) -> Path:
    return slump_store_model_dir(root, store_id, model_id) / "series"
