# jackpot_events から差枚スランプを再構成する試作

店舗 `source_store_id=100928`（エスパス日拓秋葉原駅前店）、機種 `L ToLOVEるﾀﾞｰｸﾈｽver.8.7`、実台 `M0001`（3075番）の1台で試した。

## 目的

公式 `slump_points` はおおむね1時間間隔のため、AT連チャン中の細かい差枚変化が見えない。
`jackpot_events` の `start_count` と `payout` から差枚を積み上げ、より細かいスランプを描く。

## 算出式

公式スペックのコイン持ち **30G / 50枚** を通常時消費の指標にする。

```
consumption = start_count * 50 / 30
delta       = payout - consumption
slump       = cumsum(delta)   # その日の起点を 0
```

- `start_count` は直前イベント終了後〜当該イベント開始までのゲーム数。
- `payout` はデータカウンター上の実獲得枚数（ART行は -2 など小さな負値もあり得る）。
- 各大当たりの `delta` を1つの slump_point とし、累積を Y にする。

折れ線では同一時刻に2点を置く。

1. `pre_payout` … 通常時消費の直後（大当たり直前）
2. `post_payout` … 払出直後

これにより、通常時は右下がり、大当たりは縦方向の跳ね上がりになる。

最終イベント後の `machine_daily_summaries.current_start`（現在スタート）があれば、残ゲーム分の消費だけを末尾に足す。
時刻は遊技日内に収め、取込時刻 `observed_at` は使わない。

## 実行

```
python tmp/jackpot_slump/plot_jackpot_slump.py
python tmp/jackpot_slump/plot_jackpot_slump.py --machine-code M0001
```

## 出力

```
tmp/jackpot_slump/
  plot_jackpot_slump.py
  METHOD.md
  out/
    summary.json
    series/
      event_slump_points.csv   # イベント1件 = 差枚1点（累積後）
      derived_points.csv       # origin / pre / post / 残スタート
      daily_comparison.csv     # 公式スランプとの日次比較
    plots/
      daily_overlay/           # 時刻軸、公式との重ね描き
      daily_games/             # 累計G軸
      chained_M0001.png
      chained_official_M0001.png
      daily_final_compare.png
      zoom_at_burst_*.png      # AT集中区間の拡大
```

## 結果（M0001, 2026-08-12 .. 2026-09-01, 19日）

| 指標 | 値 |
| --- | --- |
| jackpot 件数 | 995 |
| 公式 slump 点数 | 334 |
| 1日あたり点数 | 公式 15.8 点 / 推定 52.4 イベント |
| 日次系列の平均相関 | 0.73 |
| 最終差枚の平均差（推定 − 公式） | -479 枚 |
| 平均 RMSE | 811 枚 |

- 形状は公式スランプに沿う日が多い（相関 0.8 超が半数以上）。
- 点数は公式の約3.3倍。AT中は数分間隔で点が入り、1時間サンプリングでは潰れる山谷が見える。
- 推定系列は公式より平均で約 480 枚低い。30G/50枚は平均値なので、実ベル・リプレイより消費を多めに見積もっている可能性が高い。
- 公式値はおおむね 100 枚刻み。推定値は小数を含む連続値。

## 注意点

- 通常時以外（ST の 0〜15G など）にも同じ 30G/50枚 を掛けている。ART の `payout=-2` と二重気味になるが、ゲーム数が小さいので影響は限定的。
- 2026-08-18 は jackpot が午前で途切れ、公式スランプだけ夕方まで伸びている。HTML取得が早い、または履歴が途中までの日は推定が使えない。
- ベル・リプレイの実変動、AT中のゲーム内消費のばらつきは復元できない。
- 本試作は `plot_slump.py` を置き換えない。問題なければ、同じ算出を本番スクリプトへ移植する。
