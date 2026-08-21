"""機種別の設定判別カウント。

データカウンターの大当たり履歴（BB / ART）から疑似ボーナスを抽出し、
ゾーン当選と ST 単発の連を機種ルールで集計する。
判別条件は機種ごとに異なるため、model_id で仕様を切り替える。

実行:
    単体では実行しない。集計は python scripts/analysis/analyze_setting.py
    テストは python -m unittest tests.test_setting_detect
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from machine_master import normalize_model


ST_TYPES = {"ART", "AT"}
BB_TYPES = {"BB"}

ZONE_KEYS = (
    "zone_150g",
    "zone_250g",
    "zone_450g",
    "zone_650g",
    "over_zone_650g",
    "zone_1000g",
)
COUNT_KEYS = ZONE_KEYS + ("over_3time_single", "zone_special")
SPECIAL_ZONE_KEYS = ("zone_150g", "zone_450g")


@dataclass(frozen=True)
class PseudoBonus:
    start_count: Optional[int]
    zone: str
    event_seq: Optional[int] = None


@dataclass
class DayCounts:
    zone_150g: int = 0
    zone_250g: int = 0
    zone_450g: int = 0
    zone_650g: int = 0
    over_zone_650g: int = 0
    zone_1000g: int = 0
    over_3time_single: int = 0
    zone_special: int = 0
    pseudo_bonuses: list[PseudoBonus] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        return {key: getattr(self, key) for key in COUNT_KEYS}


class SettingSpec:
    """機種ごとのゾーン定義と単発判定。"""

    model_id: int
    source_model_names: tuple[str, ...] = ()

    def classify_zone(self, start_count: Optional[int]) -> str:
        raise NotImplementedError

    def analyze_events(self, events) -> DayCounts:
        bonuses = extract_pseudo_bonuses(events)
        counts = DayCounts()
        labeled = []
        for bonus in bonuses:
            zone = self.classify_zone(bonus.start_count)
            labeled.append(
                PseudoBonus(
                    start_count=bonus.start_count,
                    zone=zone,
                    event_seq=bonus.event_seq,
                )
            )
            if zone in ZONE_KEYS:
                setattr(counts, zone, getattr(counts, zone) + 1)
        counts.pseudo_bonuses = labeled
        counts.over_3time_single = count_over_3time_single(events)
        counts.zone_special = sum(
            getattr(counts, key) for key in SPECIAL_ZONE_KEYS
        )
        return counts


class ToloveruTranceSpec(SettingSpec):
    """model_id=1 L ToLOVEるダークネス TRANCE（ver.8.7）。

    疑似ボーナス後の ST はデータカウンター上 ART（AT 表記）。
    ゲーム数当選は告知前兆のため、カウンター表記は内部ゲーム数より約35G遅い。
    """

    model_id = 1
    source_model_names = ("L ToLOVEるﾀﾞｰｸﾈｽver.8.7",)

    def classify_zone(self, start_count: Optional[int]) -> str:
        if start_count is None:
            return ""
        if 180 < start_count < 190:
            return "zone_150g"
        if 280 < start_count < 290:
            return "zone_250g"
        if 480 < start_count < 490:
            return "zone_450g"
        if 680 < start_count < 690:
            return "zone_650g"
        if 690 <= start_count <= 1000:
            return "over_zone_650g"
        if start_count > 1000:
            return "zone_1000g"
        return ""


SPECS: dict[int, SettingSpec] = {
    ToloveruTranceSpec.model_id: ToloveruTranceSpec(),
}

NAME_TO_MODEL_ID: dict[str, int] = {}
for _spec in SPECS.values():
    for _name in _spec.source_model_names:
        NAME_TO_MODEL_ID[normalize_model(_name)] = _spec.model_id


def get_spec(model_id) -> Optional[SettingSpec]:
    try:
        key = int(model_id)
    except (TypeError, ValueError):
        return None
    return SPECS.get(key)


def resolve_known_model_id(model_name: str) -> Optional[int]:
    return NAME_TO_MODEL_ID.get(normalize_model(model_name))


def is_st(event) -> bool:
    return str(getattr(event, "event_type", "") or "").strip().upper() in ST_TYPES


def is_bb(event) -> bool:
    return str(getattr(event, "event_type", "") or "").strip().upper() in BB_TYPES


def _event_seq(event, index: int) -> Optional[int]:
    seq = getattr(event, "event_seq", None)
    if seq is None:
        return index + 1
    return seq


def extract_pseudo_bonuses(events) -> list[PseudoBonus]:
    """疑似ボーナス = 直後が ST（ART/AT）である BB。

    AT 中の連続 BB は直後が BB のため除外される。
    """
    events = list(events)
    bonuses = []
    for index, event in enumerate(events):
        if not is_bb(event):
            continue
        nxt = events[index + 1] if index + 1 < len(events) else None
        if nxt is None or not is_st(nxt):
            continue
        bonuses.append(
            PseudoBonus(
                start_count=getattr(event, "start_count", None),
                zone="",
                event_seq=_event_seq(event, index),
            )
        )
    return bonuses


def count_over_3time_single(events) -> int:
    """ST と ST の間の BB が1つだけの区間を単発とし、3連以上の回数を返す。

    1回の冷遇区間（3連単が途切れずに続く）を1回と数える。
    日を跨いだ連結は行わない。
    """
    events = list(events)
    st_indexes = [i for i, event in enumerate(events) if is_st(event)]
    streak = 0
    episodes = 0
    for left, right in zip(st_indexes, st_indexes[1:]):
        bb_count = sum(1 for event in events[left + 1 : right] if is_bb(event))
        if bb_count == 1:
            streak += 1
            if streak == 3:
                episodes += 1
        else:
            streak = 0
    return episodes
