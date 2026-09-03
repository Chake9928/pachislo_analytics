"""上位ST到達の台日一覧をCSV出力する。

店舗 100928 / L ToLOVEるﾀﾞｰｸﾈｽver.8.7 の全台×全日。
たい焼き（ツラヌキ）は同一上位ST区間として結合する。

出力:
    data/analysis/100928/1/upper_reach_machine_day.csv
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from machine_master import normalize_model
from supabase_client import create_supabase_client

PAGE_SIZE = 1000
SOURCE_STORE_ID = 100928
MODEL_NAME = "L ToLOVEるﾀﾞｰｸﾈｽver.8.7"
ST_TYPES = {"ART", "AT"}
BB_TYPES = {"BB"}

OUT = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "analysis"
    / "100928"
    / "1"
    / "upper_reach_machine_day.csv"
)


def paginate(query):
    rows = []
    start = 0
    while True:
        batch = query.range(start, start + PAGE_SIZE - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE


def is_st(ev):
    return str(ev.get("event_type") or "").strip().upper() in ST_TYPES


def is_bb(ev):
    return str(ev.get("event_type") or "").strip().upper() in BB_TYPES


def classify(events, i):
    ev = events[i]
    prev_e = events[i - 1] if i > 0 else None
    next_e = events[i + 1] if i + 1 < len(events) else None
    payout = ev.get("payout")
    start = ev.get("start_count")
    if is_bb(ev) and payout is not None and payout <= 100 and next_e is not None and is_st(next_e):
        return "memorial_bonus"
    if (
        is_bb(ev)
        and payout is not None
        and 100 < payout <= 250
        and next_e is not None
        and is_st(next_e)
    ):
        return "episode_bonus"
    if (
        is_bb(ev)
        and prev_e is not None
        and is_st(prev_e)
        and start is not None
        and 1 <= start <= 15
    ):
        return "trouble_bonus"
    if is_bb(ev) and start is not None and start >= 30 and payout is not None and payout >= 400:
        return "trouble_bonus_after_taiyaki"
    if is_st(ev):
        return "first_st"
    if is_bb(ev):
        return "unclassified_bb"
    return "other"


def build_cycles(events):
    judged = [classify(events, i) for i in range(len(events))]
    starts = [
        i
        for i, jid in enumerate(judged)
        if jid in {"memorial_bonus", "episode_bonus", "trouble_bonus_after_taiyaki"}
    ]
    cycles = []
    for si, start_i in enumerate(starts):
        end_i = starts[si + 1] - 1 if si + 1 < len(starts) else len(events) - 1
        chunk_j = judged[start_i : end_i + 1]
        chunk = events[start_i : end_i + 1]
        kind = chunk_j[0]
        bbs = [e for e, j in zip(chunk, chunk_j) if is_bb(e)]
        troubles = [e for e, j in zip(chunk, chunk_j) if j == "trouble_bonus"]
        unclass = [e for e, j in zip(chunk, chunk_j) if j == "unclassified_bb"]
        at_like = troubles + unclass
        if kind == "trouble_bonus_after_taiyaki":
            at_like = [chunk[0]] + at_like
        payouts = [e.get("payout") or 0 for e in bbs]
        cycles.append(
            {
                "kind": kind,
                "is_taiyaki": kind == "trouble_bonus_after_taiyaki",
                "n_at_like": len(at_like),
                "payout_sum": sum(payouts),
                "max_payout": max(payouts) if payouts else 0,
            }
        )
    return cycles


def group_sessions(cycles):
    sessions = []
    i = 0
    while i < len(cycles):
        c = cycles[i]
        if c["is_taiyaki"] and not sessions:
            group = [c]
            i += 1
            while i < len(cycles) and cycles[i]["is_taiyaki"]:
                group.append(cycles[i])
                i += 1
            sessions.append(group)
            continue
        if c["is_taiyaki"]:
            sessions[-1].append(c)
            i += 1
            continue
        group = [c]
        i += 1
        while i < len(cycles) and cycles[i]["is_taiyaki"]:
            group.append(cycles[i])
            i += 1
        sessions.append(group)
    return sessions


def session_reason(group):
    payout = sum(c["payout_sum"] for c in group)
    max_payout = max(c["max_payout"] for c in group)
    n_at = sum(c["n_at_like"] for c in group)
    has_taiyaki = any(c["is_taiyaki"] for c in group)
    if has_taiyaki:
        return "taiyaki", payout
    if payout >= 1000:
        return "cut_1000", payout
    if n_at >= 3 and max_payout >= 400:
        return "st3_highpay", payout
    return None, payout


REASON_LABEL = {
    "taiyaki": "たい焼き推定",
    "cut_1000": "実獲得1000枚以上",
    "st3_highpay": "ST3連かつAT400枚以上",
}


def fetch():
    db = create_supabase_client()
    store = (
        db.table("stores")
        .select("store_id,source_store_id,store_name")
        .eq("source_store_id", SOURCE_STORE_ID)
        .execute()
        .data
        or []
    )[0]
    models = db.table("models").select("model_id,source_model_name,model_name").execute().data or []
    wanted = normalize_model(MODEL_NAME)
    model = next(
        r
        for r in models
        if normalize_model(r["source_model_name"]) == wanted
        or normalize_model(r["model_name"]) == wanted
    )
    machines = (
        db.table("machines")
        .select("machine_id,machine_code,model_id")
        .eq("model_id", model["model_id"])
        .order("machine_code")
        .execute()
        .data
        or []
    )
    placements = (
        db.table("machine_placements")
        .select("machine_id,unit_number")
        .eq("store_id", store["store_id"])
        .execute()
        .data
        or []
    )
    unit_by_machine = {r["machine_id"]: r["unit_number"] for r in placements}
    machine_ids = [m["machine_id"] for m in machines if m["machine_id"] in unit_by_machine]
    summaries = paginate(
        db.table("machine_daily_summaries")
        .select("machine_id,data_date,unit_number")
        .eq("store_id", store["store_id"])
        .in_("machine_id", machine_ids)
        .order("data_date")
        .order("unit_number")
    )
    events = paginate(
        db.table("jackpot_events")
        .select("machine_id,data_date,event_seq,start_count,payout,event_type")
        .eq("store_id", store["store_id"])
        .in_("machine_id", machine_ids)
        .order("machine_id")
        .order("data_date")
        .order("event_seq")
    )
    return store, model, machines, unit_by_machine, summaries, events


def main():
    store, model, machines, unit_by_machine, summaries, events = fetch()
    code = {m["machine_id"]: m["machine_code"] for m in machines}
    events_by = defaultdict(list)
    event_dates = set()
    for ev in events:
        events_by[(ev["machine_id"], ev["data_date"])].append(ev)
        event_dates.add(ev["data_date"])

    rows = []
    for s in summaries:
        if s["data_date"] not in event_dates:
            continue
        mid = s["machine_id"]
        ddate = s["data_date"]
        unit = s.get("unit_number") or unit_by_machine.get(mid)
        evs = sorted(events_by.get((mid, ddate), []), key=lambda x: x["event_seq"] or 0)
        cycles = build_cycles(evs) if evs else []
        sessions = group_sessions(cycles)
        reasons = []
        payouts = []
        for g in sessions:
            reason, payout = session_reason(g)
            if reason:
                reasons.append(reason)
                payouts.append(payout)
        reached = bool(reasons)
        unique_reasons = []
        for r in ("taiyaki", "cut_1000", "st3_highpay"):
            if r in reasons:
                unique_reasons.append(REASON_LABEL[r])
        rows.append(
            {
                "日付": ddate,
                "台番号": unit,
                "上位に入ったか": "○" if reached else "×",
                "実台コード": code.get(mid, ""),
                "大当たり件数": len(evs),
                "上位区間数": len(reasons),
                "判定根拠": " / ".join(unique_reasons),
                "最大区間実獲得": max(payouts) if payouts else "",
            }
        )

    rows.sort(key=lambda r: (r["日付"], r["台番号"] or 0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "日付",
                "台番号",
                "上位に入ったか",
                "実台コード",
                "大当たり件数",
                "上位区間数",
                "判定根拠",
                "最大区間実獲得",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    n = len(rows)
    n_yes = sum(1 for r in rows if r["上位に入ったか"] == "○")
    n_taiyaki = sum(1 for r in rows if "たい焼き推定" in r["判定根拠"])
    n_cut = sum(
        1
        for r in rows
        if r["上位に入ったか"] == "○" and "たい焼き推定" not in r["判定根拠"] and "実獲得1000枚以上" in r["判定根拠"]
    )
    n_st3_only = sum(
        1
        for r in rows
        if r["判定根拠"] == "ST3連かつAT400枚以上"
    )
    print(f"wrote {OUT}")
    print(f"n={n} reached={n_yes} rate={100.0 * n_yes / n:.1f}%")
    print(f"taiyaki_days={n_taiyaki} cut_only_days={n_cut} st3_only_days={n_st3_only}")


if __name__ == "__main__":
    main()
