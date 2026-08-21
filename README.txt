Pachislo Collector v3 - Supabase Integration
=============================================

目的
----
1. unit_mapping.csv を唯一のローカル台マスタとして collector / parser が共通参照する。
2. unit_mapping.csv の内容を Supabase の stores / models / machines / machine_placements へ同期する。
3. 保存済みHTMLを解析し、Supabaseへ冪等に INSERT / UPSERT する。
4. 台番号が変更されても machine_code (M0001等) で実台を継続追跡する。

主なファイル
------------
config.py                 共通設定 / Supabase環境変数
machine_master.py         unit_mapping.csv 読込・整合性チェック・日付解決
collector_common.py       Playwright収集共通処理
html_parser.py            HTML -> Python構造化データ（DB非依存）
supabase_client.py        Supabaseクライアント生成
supabase_writer.py        各テーブルへの INSERT / UPSERT
slump_series.py           スランプ時系列の連結・平均化
storage_paths.py          raw HTML / スランプ出力のパス規則
model_lookup.py           models テーブルから model_id を解決
scripts/scraping/collect_oneday.py   指定日1日分収集
scripts/scraping/collect_7days.py    直近7日分収集
scripts/db/validate_master.py        台マスタ整合性チェック
scripts/db/init_master.py            CSV -> Supabaseマスタ同期
scripts/db/ingest_html.py            raw HTMLを一括解析してSupabaseへ投入
scripts/db/reorganize_storage.py     既存raw/スランプを機種別パスへ移動
scripts/analysis/parse_timeseries.py 従来のCSV時系列出力（ローカル確認用）
scripts/analysis/plot_slump.py       slump_points からグラフ生成
master/unit_mapping.csv   唯一のローカル台マスタ
db/pachislo_supabase_schema.sql  Supabase/PostgreSQL DDL
.env.example              環境変数サンプル

unit_mapping.csv
----------------
machine_id       実台コード。台番号が変わっても変更しない。
source_system    daidata 等
store_id         取得元サイト上の店舗ID
store_name       店舗名
model            取得元サイト上の機種名
machine_type     slot / pachinko / unknown
unit             その期間の台番号
play_rate_yen    貸玉単価
valid_from       配置有効開始日。空欄=管理開始以前から有効
valid_to         配置有効終了日。空欄=現在も有効

セットアップ
------------
1) Python依存ライブラリ

    pip install -r requirements.txt
    playwright install chromium

2) Supabase SQL Editorで以下を実行

    db/pachislo_supabase_schema.sql

3) .env.example をコピーして .env を作成

    SUPABASE_URL=...
    SUPABASE_SERVICE_ROLE_KEY=...

   service role / secret key はバックエンド取込専用。
   Gitへコミットせず、ブラウザやフロントエンドへ渡さないこと。

初期マスタ投入
--------------
まずローカル検証:

    python scripts/db/validate_master.py
    python scripts/db/init_master.py --dry-run

問題なければSupabaseへ同期:

    python scripts/db/init_master.py

同期対象:
    stores
    models
    machines
    machine_placements

同じCSVで再実行可能。既存マスタは更新し、配置履歴は既存期間を見つけて更新する。

HTML収集
--------
省略時は unit_mapping.csv の対象日配置を全件取得する。
店舗・機種で絞る場合はオプションを付ける。

    python scripts/scraping/collect_oneday.py 2026-08-21
    python scripts/scraping/collect_oneday.py 2026-08-21 --store-id 100928
    python scripts/scraping/collect_oneday.py 2026-08-21 --store-id 100928 --model "L ﾏｷﾞｱﾚｺｰﾄﾞ"

    python scripts/scraping/collect_7days.py
    python scripts/scraping/collect_7days.py --store-id 100928 --model "L ﾏｷﾞｱﾚｺｰﾄﾞ"

--model は unit_mapping.csv の機種名。全角半角・空白の揺れは無視する。

HTML解析のローカル確認
----------------------
rawディレクトリ構造が以下なら日付を自動判定する。

    data/raw/{store_id}/{model_id}/{YYYY-MM-DD}/{machine_id}.html

    例: data/raw/100928/1/2026-08-12/M0001.html

スランプ出力も同じ店舗×機種先行:

    data/slump/{store_id}/{model_id}/01_daily_by_machine/{YYYY-MM-DD}/
    data/slump/{store_id}/{model_id}/02_chained_by_machine/
    data/slump/{store_id}/{model_id}/03_daily_average/
    data/slump/{store_id}/{model_id}/04_chained_average/
    data/slump/{store_id}/{model_id}/series/

旧形式（store_id/日付/台番号）も解析時は読み取れる。
model_id は Supabase の models テーブルの機種ID。収集前に init_master.py が必要。

既存ファイルを新パスへ移す:

    python scripts/db/reorganize_storage.py --dry-run
    python scripts/db/reorganize_storage.py

全件dry-run:

    python scripts/db/ingest_html.py --dry-run

単体HTMLを日付指定してdry-run:

    python scripts/db/ingest_html.py C:/path/to/M0001.html --data-date 2026-08-12 --dry-run

解析結果JSONも確認する場合:

    python scripts/db/ingest_html.py C:/path/to/M0001.html \
        --data-date 2026-08-12 \
        --dry-run \
        --debug-json data/processed/M0001_debug.json

Supabase投入
------------
全raw HTML:

    python scripts/db/ingest_html.py

単体HTML:

    python scripts/db/ingest_html.py C:/path/to/M0001.html --data-date 2026-08-12

投入・更新するテーブル
----------------------
collection_runs
    1回の取込処理を記録。

source_pages
    HTML単位の取得元情報。SHA-256 content_hashを持つ。
    同一HTMLを再解析した場合は既存source_pageを再利用する。

store_daily_snapshots
    パチンコ/スロット設置台数。
    historical target_dateではなく、ページを観測した日として保存する。

machine_daily_summaries
    BB/RB/ART、スタート回数、最大持ち玉、累計スタート、各確率等。
    PRIMARY KEY = (machine_id, data_date) なのでリアルタイム再取得は更新される。

jackpot_events
    大当たり履歴。
    HTMLは新しい順だが、parserでは古い順に event_seq=1..N として安定採番する。
    UNIQUE(machine_id, data_date, event_seq) を使ってUPSERTする。

slump_points
    jqPlot内の時刻/スランプ値。
    UNIQUE(machine_id, data_date, sampled_at) により再取得時の重複を防ぐ。
    1つのHTMLに複数日分が入っている場合も取得するが、unit_mapping.csvで同じmachine_idと
    確認できた日だけ保存する。配置変更前後で別実台のデータを混ぜないため。

machine_daily_metrics
    対象日のスランプ最終/最大/最小/レンジ、ポイント数、イベント出玉等の派生指標。

過去データについて
------------------
HTMLの「過去のデータ」カードも machine_daily_summaries として抽出する。
ただし、その日付で同じstore/unitが同一machine_idに解決できる場合のみ採用する。

日時の意味
----------
data_date
    遊技対象日。

requested_data_date
    そのHTML取得時に要求したtarget_date。

fetched_at
    HTML取得日時。現状、既存raw HTMLはファイル更新日時をフォールバックとして使用する。

source_updated_at
    サイトHTMLに表示される「最終更新時間」。data_dateとは一致しない場合がある。

store_daily_snapshots.snapshot_date
    店舗台数を観測した日。source_updated_atを優先して決定する。

注意
----
Raw HTML自体のSupabase Storageアップロードは行わない。
source_pages.raw_storage_pathには現在ローカルパスを保存する。
Storageへ移行するときはこの列をObject Storageのキーへ差し替えられる。
