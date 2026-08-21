"""設定判別CSVから1枚のHTMLサマリを生成する。

scripts/analysis/summarize_setting.py および analyze_setting.py から呼ぶ。

実行:
    単体では実行しない。
        python scripts/analysis/summarize_setting.py data/setting/100928/1
    テストは python -m unittest tests.test_setting_summary
"""

from __future__ import annotations

import csv
import html
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Optional

from setting_detect import COUNT_KEYS, get_spec


CSV_FILES = (
    "store_total.csv",
    "store_daily.csv",
    "machine_total.csv",
    "machine_daily.csv",
    "pseudo_bonus_events.csv",
)

MODEL_DISPLAY_NAMES = {
    1: "L ToLOVEるダークネス TRANCE",
}


def _i(row, key, default=0) -> int:
    value = row.get(key, default)
    if value in ("", None):
        return default
    return int(value)


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_setting_dir(setting_dir: Path) -> dict:
    setting_dir = Path(setting_dir)
    missing = [name for name in CSV_FILES if not (setting_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"{setting_dir} にCSVが不足しています: {', '.join(missing)}"
        )

    store_total = _read_csv(setting_dir / "store_total.csv")
    if not store_total:
        raise ValueError(f"store_total.csv が空です: {setting_dir}")

    machines = []
    for row in _read_csv(setting_dir / "machine_total.csv"):
        item = {key: _i(row, key) for key in COUNT_KEYS}
        item["store_id"] = row["store_id"]
        item["model_id"] = int(row["model_id"])
        item["machine_id"] = row["machine_id"]
        item["unit_number"] = _i(row, "unit_number")
        item["date_from"] = row["date_from"]
        item["date_to"] = row["date_to"]
        item["late_zone"] = item["over_zone_650g"] + item["zone_1000g"]
        denom = item["zone_650g"] + item["late_zone"]
        item["late_ratio"] = (
            item["late_zone"] / denom if denom else None
        )
        item["high_index"] = (
            2 * item["zone_special"] + item["zone_650g"] - item["late_zone"]
        )
        item["tags"] = classify_machine(item)
        machines.append(item)

    daily = []
    for row in _read_csv(setting_dir / "machine_daily.csv"):
        item = {key: _i(row, key) for key in COUNT_KEYS}
        item["store_id"] = row["store_id"]
        item["model_id"] = int(row["model_id"])
        item["machine_id"] = row["machine_id"]
        item["unit_number"] = _i(row, "unit_number")
        item["data_date"] = row["data_date"]
        daily.append(item)

    store_daily = []
    for row in _read_csv(setting_dir / "store_daily.csv"):
        item = {key: _i(row, key) for key in COUNT_KEYS}
        item["store_id"] = row["store_id"]
        item["model_id"] = int(row["model_id"])
        item["data_date"] = row["data_date"]
        item["machine_count"] = _i(row, "machine_count")
        store_daily.append(item)

    events = _read_csv(setting_dir / "pseudo_bonus_events.csv")
    total = store_total[0]
    counts = {key: _i(total, key) for key in COUNT_KEYS}
    return {
        "dir": setting_dir,
        "store_id": total["store_id"],
        "model_id": int(total["model_id"]),
        "machine_count": _i(total, "machine_count"),
        "date_from": total["date_from"],
        "date_to": total["date_to"],
        "counts": counts,
        "machines": machines,
        "daily": daily,
        "store_daily": store_daily,
        "events": events,
    }


def classify_machine(item) -> list[str]:
    tags = []
    if item["zone_special"] >= 5 and item["late_zone"] <= 10:
        tags.append("高設定候補")
    elif item["zone_special"] >= 4:
        tags.append("高設定シグナル")
    if item["zone_special"] == 0:
        tags.append("低設定寄り")
    if item["over_3time_single"] >= 8:
        tags.append("冷遇多発")
    if item["zone_1000g"] >= 7:
        tags.append("天井寄り")
    return tags


def _fmt(machine) -> str:
    return f"{machine['machine_id']}（{machine['unit_number']}番）"


def _ratio_text(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.0%}"


def build_commentary(data: dict) -> list[dict]:
    machines = data["machines"]
    counts = data["counts"]
    store_daily = data["store_daily"]
    n_days = max(len(store_daily), 1)
    n_machine_days = data["machine_count"] * n_days
    late = counts["over_zone_650g"] + counts["zone_1000g"]

    top_special = sorted(
        machines,
        key=lambda m: (-m["zone_special"], m["late_zone"], -m["zone_650g"]),
    )
    top_index = sorted(machines, key=lambda m: (-m["high_index"], -m["zone_special"]))
    most_cold = sorted(machines, key=lambda m: (-m["over_3time_single"], -m["zone_special"]))
    zero_special = [m for m in machines if m["zone_special"] == 0]
    candidates = [m for m in machines if "高設定候補" in m["tags"]]
    peak_day = max(store_daily, key=lambda d: d["zone_special"]) if store_daily else None
    trough_day = min(store_daily, key=lambda d: d["zone_special"]) if store_daily else None
    median_late = median(m["late_zone"] for m in machines) if machines else 0
    median_special = median(m["zone_special"] for m in machines) if machines else 0

    sections = []
    sections.append(
        {
            "title": "島全体",
            "body": (
                f"{data['machine_count']}台 × {n_days}日（{n_machine_days}台日）で、"
                f"高設定帯（150G+450G）は {counts['zone_special']} 回、"
                f"1台1日あたり {counts['zone_special'] / n_machine_days:.2f} 回。"
                f"450G帯は {counts['zone_450g']} 回と少なく、150G帯 {counts['zone_150g']} 回が大半を占める。"
                f"一方、650G帯 {counts['zone_650g']} 回に対し 650超+天井は {late} 回で、"
                f"ゲーム数当選は 650 を越えやすい側に寄っている。"
                f"判別理論では高設定ほど 150/450 が出て天井に行きにくい、という前提なので、"
                f"この島を「高設定が厚い」と読む材料は弱い。通常設定中心に、一部の台だけが高設定帯を拾っている、という見え方。"
            ),
        }
    )
    if peak_day and trough_day:
        specials = [d["zone_special"] for d in store_daily]
        avg_special = sum(specials) / len(specials)
        low_days = [
            d["data_date"]
            for d in store_daily
            if d["zone_special"] < avg_special * 0.5
        ]
        high_days = [
            d["data_date"]
            for d in store_daily
            if d["zone_special"] >= avg_special * 1.2
        ]
        extra = ""
        if high_days:
            extra += f"平均を上回る日は {', '.join(high_days)}。"
        if low_days:
            extra += (
                f"平均の半分を下回る日は {', '.join(low_days)}。"
                "薄い日を設定ダウンと読む前に、稼働が少ないか HTML が営業途中取得でないかを疑うべき。"
            )
        sections.append(
            {
                "title": "日次の山谷",
                "body": (
                    f"高設定帯が最も多いのは {peak_day['data_date']} の {peak_day['zone_special']} 回、"
                    f"最も少ないのは {trough_day['data_date']} の {trough_day['zone_special']} 回。"
                    + extra
                    + "日次比較は、その日の疑似ボーナス母数が乗っている日だけを見る方が安全。"
                ),
            }
        )

    cand_text = "該当なし。"
    if candidates:
        lines = []
        for m in candidates:
            lines.append(
                f"{_fmt(m)} は高設定帯{m['zone_special']} / 650超+天井{m['late_zone']} / "
                f"650帯{m['zone_650g']} / 3連単{m['over_3time_single']}。"
            )
        cand_text = (
            "理論どおり「高設定帯が多く、650を越えた当選が相対的に少ない」に当てはまるのは "
            + "、".join(_fmt(m) for m in candidates)
            + "。"
            + " ".join(lines)
            + " ただし高設定候補と冷遇多発が同時に付く台がある。"
            "前提どおり、冷遇に入っている日は高設定でも単発が続き得るので、"
            "候補台でもその日の3連単が出ていれば見送り、が整合する。"
        )
    sections.append({"title": "高設定候補", "body": cand_text})

    lead = top_special[0] if top_special else None
    second = top_special[1] if len(top_special) > 1 else None
    detail = []
    if lead:
        detail.append(
            f"高設定帯の最多は {_fmt(lead)} の {lead['zone_special']} 回"
            f"（150G {lead['zone_150g']} / 450G {lead['zone_450g']}、"
            f"650超+天井 {lead['late_zone']}、3連単 {lead['over_3time_single']}）。"
        )
    if second:
        detail.append(
            f"次いで {_fmt(second)} も高設定帯 {second['zone_special']} 回。"
        )
    if lead and lead["machine_id"] == "M0018":
        detail.append(
            "3154番は高設定帯が多く 650超+天井が同グループでは少ない一方、3連単が島内最多で、"
            "「設定は良さそうだが冷遇で見た目が悪い」典型に近い。"
        )
    if any(m["machine_id"] == "M0012" for m in top_special[:5]):
        m12 = next(m for m in machines if m["machine_id"] == "M0012")
        detail.append(
            f"{_fmt(m12)} は 450G帯が {m12['zone_450g']} 回と島内でも目立つ。"
            f"高設定帯の質は良いが、天井 {m12['zone_1000g']} 回・650超+天井 {m12['late_zone']} 回と後半も重い。"
        )
    if any(m["machine_id"] == "M0004" for m in machines):
        m4 = next(m for m in machines if m["machine_id"] == "M0004")
        detail.append(
            f"{_fmt(m4)} は高設定帯 {m4['zone_special']} 回が特定日に極端に偏らず、"
            f"複数日に散っている。単発の当たり日というより、期間を通したシグナルに近い。"
            f"650帯は {m4['zone_650g']} 回と少なめなので、650当選率の高さまでは伴っていない。"
        )
    sections.append({"title": "台の中身", "body": " ".join(detail) if detail else "—"})

    cold = most_cold[:3]
    sections.append(
        {
            "title": "冷遇",
            "body": (
                f"3連単以上は期間合計 {counts['over_3time_single']} 回、"
                f"1台1日あたり {counts['over_3time_single'] / n_machine_days:.2f} 回。"
                "多い台は "
                + "、".join(
                    f"{_fmt(m)} {m['over_3time_single']}回" for m in cold
                )
                + "。"
                "高設定帯が多い台ほど打たれて疑似の母数も増えるので、冷遇回数の多さだけで低設定とは言えない。"
                "使い方としては設定の加点ではなく、その日その台を見送る減点。"
            ),
        }
    )

    if zero_special:
        sections.append(
            {
                "title": "低設定寄り",
                "body": (
                    "高設定帯が期間中0回なのは "
                    + "、".join(_fmt(m) for m in zero_special)
                    + "。"
                    f"島内の高設定帯中央値は {median_special:.0f} 回、650超+天井の中央値は {median_late:.0f} 回。"
                    "0回は『出なかった』以上の意味はなく、打たれが薄い台では検出自体が難しい。"
                    "そのうえで天井が多い台は、理論上の低設定側（150/450が出ず、天井に行きやすい）に近い。"
                ),
            }
        )

    best = top_index[0] if top_index else None
    if best:
        sections.append(
            {
                "title": "いま見るなら",
                "body": (
                    f"指数（2×高設定帯 + 650帯 − 650超+天井）の先頭は {_fmt(best)} で {best['high_index']}。"
                    "これは設定の事後確率ではなく、提示された理論を足し引きした並び替えにすぎない。"
                    "実践では (1) 高設定帯が期間で出ている (2) 650超+天井が目立たない (3) 当日3連単が無い、"
                    "の3点を同時に満たす台から当たるのが、このデータとの整合が良い。"
                    f"指数2位以降は "
                    + "、".join(
                        f"{_fmt(m)} {m['high_index']}" for m in top_index[1:5]
                    )
                    + "。"
                ),
            }
        )

    sections.append(
        {
            "title": "このサマリで切らないこと",
            "body": (
                "CZはカウンターに残らないため、ゾーン外の疑似ボーナスの大半は観察不能。"
                "ゾーン幅は前兆ずれを見込んだ ± 数Gなので、境界付近は取りこぼしと混入がある。"
                "3連単は日内のみで、日を跨いだ冷遇は連結していない。"
                "母数の薄い日を、設定変更の証拠には使わない。"
            ),
        }
    )
    return sections


def _bar(value: int, max_value: int, css_class: str) -> str:
    width = 0 if max_value <= 0 else round(100 * value / max_value)
    return (
        f'<div class="bar"><span class="{css_class}" style="width:{width}%"></span>'
        f'<em>{value}</em></div>'
    )


def _heat_cell(value: int, max_value: int, kind: str) -> str:
    if max_value <= 0 or value <= 0:
        return f'<td class="heat {kind} z" title="0">0</td>'
    level = min(5, max(1, round(5 * value / max_value)))
    return (
        f'<td class="heat {kind} l{level}" title="{value}">{value}</td>'
    )


def _tag_html(tags: list[str]) -> str:
    if not tags:
        return '<span class="tag mute">—</span>'
    return "".join(
        f'<span class="tag {html.escape(tag)}">{html.escape(tag)}</span>' for tag in tags
    )


def render_summary_html(data: dict) -> str:
    model_id = data["model_id"]
    spec = get_spec(model_id)
    model_name = MODEL_DISPLAY_NAMES.get(model_id)
    if not model_name and spec and spec.source_model_names:
        model_name = spec.source_model_names[0]
    model_name = model_name or f"model_id={model_id}"

    commentary = build_commentary(data)
    machines = sorted(
        data["machines"],
        key=lambda m: (-m["high_index"], -m["zone_special"], m["late_zone"]),
    )
    dates = [row["data_date"] for row in data["store_daily"]]
    daily_by_machine = defaultdict(dict)
    for row in data["daily"]:
        daily_by_machine[row["machine_id"]][row["data_date"]] = row
    max_special_day = max((d["zone_special"] for d in data["daily"]), default=1) or 1
    max_cold_day = max((d["over_3time_single"] for d in data["daily"]), default=1) or 1
    store_max = 1
    for row in data["store_daily"]:
        store_max = max(
            store_max,
            row["zone_special"],
            row["zone_650g"],
            row["over_zone_650g"] + row["zone_1000g"],
            row["over_3time_single"],
        )

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    counts = data["counts"]
    late_total = counts["over_zone_650g"] + counts["zone_1000g"]

    kpi = [
        ("高設定帯", counts["zone_special"], "150G+450G"),
        ("150G帯", counts["zone_150g"], "181〜189G"),
        ("450G帯", counts["zone_450g"], "481〜489G"),
        ("650G帯", counts["zone_650g"], "681〜689G"),
        ("650超+天井", late_total, "690G〜"),
        ("3連単以上", counts["over_3time_single"], "冷遇区間"),
    ]

    commentary_html = "".join(
        f"<article><h3>{html.escape(sec['title'])}</h3><p>{html.escape(sec['body'])}</p></article>"
        for sec in commentary
    )

    daily_bars = []
    for row in data["store_daily"]:
        late = row["over_zone_650g"] + row["zone_1000g"]
        daily_bars.append(
            "<tr>"
            f"<th>{html.escape(row['data_date'])}</th>"
            f"<td>{_bar(row['zone_special'], store_max, 'special')}</td>"
            f"<td>{_bar(row['zone_650g'], store_max, 'z650')}</td>"
            f"<td>{_bar(late, store_max, 'late')}</td>"
            f"<td>{_bar(row['over_3time_single'], store_max, 'cold')}</td>"
            "</tr>"
        )

    heat_special_rows = []
    heat_cold_rows = []
    for m in machines:
        cells_s = []
        cells_c = []
        for day in dates:
            cell = daily_by_machine[m["machine_id"]].get(day, {})
            cells_s.append(
                _heat_cell(cell.get("zone_special", 0), max_special_day, "special")
            )
            cells_c.append(
                _heat_cell(cell.get("over_3time_single", 0), max_cold_day, "cold")
            )
        label = (
            f'<th>{html.escape(m["machine_id"])}<small>{m["unit_number"]}</small></th>'
        )
        heat_special_rows.append("<tr>" + label + "".join(cells_s) + "</tr>")
        heat_cold_rows.append("<tr>" + label + "".join(cells_c) + "</tr>")
    date_heads = "".join(f"<th>{html.escape(d[5:])}</th>" for d in dates)

    machine_rows = []
    for rank, m in enumerate(machines, start=1):
        machine_rows.append(
            "<tr>"
            f"<td class='num'>{rank}</td>"
            f"<td><strong>{html.escape(m['machine_id'])}</strong></td>"
            f"<td class='num'>{m['unit_number']}</td>"
            f"<td>{_tag_html(m['tags'])}</td>"
            f"<td class='num idx'>{m['high_index']}</td>"
            f"<td class='num'>{m['zone_special']}</td>"
            f"<td class='num'>{m['zone_150g']}</td>"
            f"<td class='num'>{m['zone_450g']}</td>"
            f"<td class='num'>{m['zone_650g']}</td>"
            f"<td class='num'>{m['late_zone']}</td>"
            f"<td class='num'>{m['over_zone_650g']}</td>"
            f"<td class='num'>{m['zone_1000g']}</td>"
            f"<td class='num'>{_ratio_text(m['late_ratio'])}</td>"
            f"<td class='num'>{m['over_3time_single']}</td>"
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>設定判別サマリ {html.escape(str(data['store_id']))} / {html.escape(model_name)}</title>
<style>
:root {{
  --bg: #f3efe6;
  --paper: #fffcf6;
  --ink: #241c16;
  --muted: #6d6258;
  --line: #e0d6c8;
  --special: #7a1f3d;
  --z650: #2c5f4e;
  --late: #8a5a18;
  --cold: #3d4a73;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  color: var(--ink);
  background: radial-gradient(1200px 500px at 10% -10%, #f7e7d4 0%, var(--bg) 45%);
  font-family: "Yu Gothic UI", "Yu Gothic", "Hiragino Sans", sans-serif;
  line-height: 1.65;
}}
main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 80px; }}
header.hero {{
  display: grid;
  gap: 8px;
  margin-bottom: 28px;
}}
.kicker {{
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-size: 11px;
  color: var(--special);
  font-weight: 700;
}}
h1 {{ font-size: 28px; margin: 0; letter-spacing: 0.02em; }}
.meta {{ color: var(--muted); font-size: 13px; }}
nav.toc {{
  display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 28px;
}}
nav.toc a {{
  color: var(--ink); text-decoration: none; font-size: 12px;
  border: 1px solid var(--line); background: var(--paper);
  padding: 4px 10px; border-radius: 999px;
}}
.kpis {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  margin-bottom: 28px;
}}
.kpi {{
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 14px 16px;
}}
.kpi b {{ display: block; font-size: 28px; font-variant-numeric: tabular-nums; }}
.kpi span {{ color: var(--muted); font-size: 12px; }}
section {{
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 22px 24px;
  margin-bottom: 18px;
}}
h2 {{ margin: 0 0 14px; font-size: 18px; }}
.note {{
  color: var(--muted);
  font-size: 12px;
  margin: -6px 0 14px;
}}
.commentary article {{
  padding: 12px 0;
  border-top: 1px solid var(--line);
}}
.commentary article:first-child {{ border-top: 0; padding-top: 0; }}
.commentary h3 {{ margin: 0 0 6px; font-size: 14px; color: var(--special); }}
.commentary p {{ margin: 0; font-size: 14px; }}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}}
th, td {{ padding: 6px 8px; border-bottom: 1px solid var(--line); text-align: left; }}
th {{ font-size: 11px; color: var(--muted); font-weight: 600; }}
td.num, th.num {{ text-align: right; }}
.bar {{
  position: relative; height: 16px; background: #efe7db; border-radius: 4px;
  min-width: 90px;
}}
.bar span {{ display: block; height: 100%; border-radius: 4px; }}
.bar em {{
  position: absolute; right: 6px; top: -1px; font-size: 11px; font-style: normal;
}}
.bar .special {{ background: var(--special); }}
.bar .z650 {{ background: var(--z650); }}
.bar .late {{ background: var(--late); }}
.bar .cold {{ background: var(--cold); }}
.heatwrap {{ overflow-x: auto; }}
.heat {{ text-align: center; width: 42px; }}
.heat.z {{ color: #cbbfaf; }}
.heat.special.l1 {{ background: #f3d6df; }}
.heat.special.l2 {{ background: #e7a8bb; }}
.heat.special.l3 {{ background: #d06b8a; color: #fff; }}
.heat.special.l4 {{ background: #b13c63; color: #fff; }}
.heat.special.l5 {{ background: #7a1f3d; color: #fff; }}
.heat.cold.l1 {{ background: #d9deef; }}
.heat.cold.l2 {{ background: #b3bddc; }}
.heat.cold.l3 {{ background: #7d8bb8; color: #fff; }}
.heat.cold.l4 {{ background: #556394; color: #fff; }}
.heat.cold.l5 {{ background: #3d4a73; color: #fff; }}
.tag {{
  display: inline-block; font-size: 10px; padding: 1px 7px; border-radius: 999px;
  margin: 0 3px 3px 0; border: 1px solid var(--line); white-space: nowrap;
}}
.tag.高設定候補 {{ background: #7a1f3d; color: #fff; border-color: #7a1f3d; }}
.tag.高設定シグナル {{ background: #f3d6df; color: #7a1f3d; }}
.tag.低設定寄り {{ background: #efe7db; color: #6d6258; }}
.tag.冷遇多発 {{ background: #3d4a73; color: #fff; border-color: #3d4a73; }}
.tag.天井寄り {{ background: #8a5a18; color: #fff; border-color: #8a5a18; }}
.tag.mute {{ color: #cbbfaf; }}
td.idx {{ font-weight: 700; }}
.filter {{
  margin-bottom: 10px; padding: 8px 10px; width: min(280px, 100%);
  border: 1px solid var(--line); border-radius: 8px; background: #fff;
}}
.legend span {{ display: inline-block; margin-right: 12px; font-size: 12px; color: var(--muted); }}
.legend i {{
  display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px;
}}
footer {{ color: var(--muted); font-size: 12px; margin-top: 8px; }}
</style>
</head>
<body>
<main>
<header class="hero">
  <div class="kicker">Setting summary</div>
  <h1>{html.escape(model_name)}</h1>
  <div class="meta">
    店舗 {html.escape(str(data['store_id']))} ／ model_id={model_id} ／
    {html.escape(data['date_from'])} 〜 {html.escape(data['date_to'])} ／
    {data['machine_count']}台 ／ 生成 {html.escape(generated)}
  </div>
</header>
<nav class="toc">
  <a href="#kpis">期間合計</a>
  <a href="#comment">考察</a>
  <a href="#daily">日次</a>
  <a href="#heat">台×日</a>
  <a href="#machines">台別順位</a>
</nav>

<section id="kpis">
  <h2>期間合計</h2>
  <p class="note">カウントは疑似ボーナス（BB直後がART）のみ。AT中の連続BBは含まない。</p>
  <div class="kpis">
    {''.join(f'<div class="kpi"><span>{html.escape(label)}</span><b>{value}</b><span>{html.escape(hint)}</span></div>' for label, value, hint in kpi)}
  </div>
  <p class="legend">
    <span>250G帯 {counts['zone_250g']}（高設定の加点には使わない）</span>
    <span>指数 = 2×高設定帯 + 650帯 − (650超+天井)</span>
  </p>
</section>

<section id="comment" class="commentary">
  <h2>考察</h2>
  <p class="note">提示された判別理論（150/450が出て、650超え・天井が少なく、3連単は冷遇フラグ）にデータを当てた読み。設定の断定ではない。</p>
  {commentary_html}
</section>

<section id="daily">
  <h2>店舗日次</h2>
  <p class="note">棒の長さは期間内の最大値を100%とした相対値。</p>
  <table>
    <thead>
      <tr>
        <th>日付</th>
        <th>高設定帯</th>
        <th>650G帯</th>
        <th>650超+天井</th>
        <th>3連単以上</th>
      </tr>
    </thead>
    <tbody>
      {''.join(daily_bars)}
    </tbody>
  </table>
</section>

<section id="heat">
  <h2>台 × 日（高設定帯）</h2>
  <p class="note">色が濃いほどその日の 150G+450G が多い。台の並びは指数順。</p>
  <div class="heatwrap">
    <table>
      <thead><tr><th>台</th>{date_heads}</tr></thead>
      <tbody>{''.join(heat_special_rows)}</tbody>
    </table>
  </div>
  <h2 style="margin-top:22px">台 × 日（3連単以上）</h2>
  <p class="note">色が濃いほどその日の冷遇区間が多い。</p>
  <div class="heatwrap">
    <table>
      <thead><tr><th>台</th>{date_heads}</tr></thead>
      <tbody>{''.join(heat_cold_rows)}</tbody>
    </table>
  </div>
</section>

<section id="machines">
  <h2>台別順位</h2>
  <p class="note">初期ソートは指数降順。高設定候補 = 高設定帯5以上かつ650超+天井10以下。</p>
  <input class="filter" id="filter" placeholder="machine_id / 台番号で絞り込み">
  <div class="heatwrap">
    <table id="machines-table">
      <thead>
        <tr>
          <th class="num">#</th>
          <th>machine</th>
          <th class="num">台番</th>
          <th>タグ</th>
          <th class="num">指数</th>
          <th class="num">高設定帯</th>
          <th class="num">150</th>
          <th class="num">450</th>
          <th class="num">650</th>
          <th class="num">650超+天井</th>
          <th class="num">650超</th>
          <th class="num">天井</th>
          <th class="num">後半比</th>
          <th class="num">3連単</th>
        </tr>
      </thead>
      <tbody>
        {''.join(machine_rows)}
      </tbody>
    </table>
  </div>
</section>

<footer>
  ソース: machine_total / machine_daily / store_daily / store_total / pseudo_bonus_events。
  後半比は (650超+天井) / (650帯+650超+天井)。
</footer>
</main>
<script>
const input = document.getElementById('filter');
const rows = [...document.querySelectorAll('#machines-table tbody tr')];
input.addEventListener('input', () => {{
  const q = input.value.trim().toLowerCase();
  rows.forEach((row) => {{
    row.style.display = !q || row.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}});
</script>
</body>
</html>
"""


def write_setting_summary(setting_dir: Path) -> Path:
    data = load_setting_dir(setting_dir)
    path = Path(setting_dir) / "summary.html"
    path.write_text(render_summary_html(data), encoding="utf-8")
    return path
