-- Pachislo Analytics Schema for Supabase / PostgreSQL
-- Generated for the エスパ攻略 project
-- Physical names: English / Logical names: Japanese comments

create extension if not exists pgcrypto;

-- =========================================================
-- 1. stores / 店舗マスタ
-- =========================================================
create table if not exists public.stores (
    store_id bigint generated always as identity primary key,
    source_system text not null default 'daidata',
    source_store_id integer not null,
    store_name text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_stores_source unique (source_system, source_store_id)
);

comment on table public.stores is '店舗マスタ';
comment on column public.stores.store_id is '店舗ID';
comment on column public.stores.source_system is 'データ取得元システム';
comment on column public.stores.source_store_id is '取得元店舗ID';
comment on column public.stores.store_name is '店舗名';
comment on column public.stores.is_active is '収集対象フラグ';
comment on column public.stores.created_at is '登録日時';
comment on column public.stores.updated_at is '更新日時';

-- =========================================================
-- 2. models / 機種マスタ
-- =========================================================
create table if not exists public.models (
    model_id bigint generated always as identity primary key,
    source_system text not null default 'daidata',
    source_model_name text not null,
    model_name text not null,
    machine_type text not null default 'unknown',
    guide_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ck_models_machine_type
        check (machine_type in ('slot', 'pachinko', 'unknown')),
    constraint uq_models_source unique (source_system, source_model_name)
);

comment on table public.models is '機種マスタ';
comment on column public.models.model_id is '機種ID';
comment on column public.models.source_system is 'データ取得元システム';
comment on column public.models.source_model_name is '取得元機種名';
comment on column public.models.model_name is '正規化機種名';
comment on column public.models.machine_type is '遊技種別';
comment on column public.models.guide_url is '遊技説明URL';
comment on column public.models.created_at is '登録日時';
comment on column public.models.updated_at is '更新日時';

-- =========================================================
-- 3. machines / 実台マスタ
-- =========================================================
create table if not exists public.machines (
    machine_id bigint generated always as identity primary key,
    machine_code text not null unique,
    model_id bigint not null references public.models(model_id),
    first_seen_date date,
    last_seen_date date,
    status text not null default 'active',
    note text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ck_machines_status
        check (status in ('active', 'removed', 'unknown')),
    constraint ck_machines_seen_dates
        check (
            first_seen_date is null
            or last_seen_date is null
            or last_seen_date >= first_seen_date
        )
);

comment on table public.machines is '実台マスタ';
comment on column public.machines.machine_id is '実台ID';
comment on column public.machines.machine_code is '実台コード';
comment on column public.machines.model_id is '機種ID';
comment on column public.machines.first_seen_date is '初回確認日';
comment on column public.machines.last_seen_date is '最終確認日';
comment on column public.machines.status is '実台ステータス';
comment on column public.machines.note is '備考';
comment on column public.machines.created_at is '登録日時';
comment on column public.machines.updated_at is '更新日時';

create index if not exists idx_machines_model_id
    on public.machines(model_id);

-- =========================================================
-- 4. machine_placements / 実台配置履歴
-- =========================================================
create table if not exists public.machine_placements (
    placement_id bigint generated always as identity primary key,
    machine_id bigint not null references public.machines(machine_id),
    store_id bigint not null references public.stores(store_id),
    unit_number integer not null,
    play_rate_yen numeric(8,2),
    valid_from date,
    valid_to date,
    source text not null default 'manual',
    created_at timestamptz not null default now(),
    constraint ck_machine_placements_unit_number
        check (unit_number > 0),
    constraint ck_machine_placements_play_rate
        check (play_rate_yen is null or play_rate_yen >= 0),
    constraint ck_machine_placements_valid_period
        check (
            valid_from is null
            or valid_to is null
            or valid_to >= valid_from
        ),
    constraint uq_machine_placements_start
        unique (machine_id, store_id, unit_number, valid_from)
);

comment on table public.machine_placements is '実台配置履歴';
comment on column public.machine_placements.placement_id is '配置履歴ID';
comment on column public.machine_placements.machine_id is '実台ID';
comment on column public.machine_placements.store_id is '店舗ID';
comment on column public.machine_placements.unit_number is '台番号';
comment on column public.machine_placements.play_rate_yen is '貸玉単価';
comment on column public.machine_placements.valid_from is '配置有効開始日';
comment on column public.machine_placements.valid_to is '配置有効終了日';
comment on column public.machine_placements.source is '配置情報登録元';
comment on column public.machine_placements.created_at is '登録日時';

create index if not exists idx_machine_placements_store_unit_period
    on public.machine_placements(store_id, unit_number, valid_from, valid_to);

create index if not exists idx_machine_placements_machine_period
    on public.machine_placements(machine_id, valid_from, valid_to);

-- =========================================================
-- 5. collection_runs / データ収集実行履歴
-- =========================================================
create table if not exists public.collection_runs (
    run_id uuid primary key default gen_random_uuid(),
    mode text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    collector_version text,
    target_store_count integer not null default 0,
    target_machine_count integer not null default 0,
    success_count integer not null default 0,
    failure_count integer not null default 0,
    status text not null default 'running',
    constraint ck_collection_runs_mode
        check (mode in ('realtime', 'today', '7days', 'manual')),
    constraint ck_collection_runs_status
        check (status in ('running', 'success', 'partial', 'error')),
    constraint ck_collection_runs_counts
        check (
            target_store_count >= 0
            and target_machine_count >= 0
            and success_count >= 0
            and failure_count >= 0
        )
);

comment on table public.collection_runs is 'データ収集実行履歴';
comment on column public.collection_runs.run_id is '収集実行ID';
comment on column public.collection_runs.mode is '収集モード';
comment on column public.collection_runs.started_at is '収集開始日時';
comment on column public.collection_runs.finished_at is '収集終了日時';
comment on column public.collection_runs.collector_version is '収集プログラムバージョン';
comment on column public.collection_runs.target_store_count is '対象店舗数';
comment on column public.collection_runs.target_machine_count is '対象台数';
comment on column public.collection_runs.success_count is '収集成功件数';
comment on column public.collection_runs.failure_count is '収集失敗件数';
comment on column public.collection_runs.status is '収集実行ステータス';

create index if not exists idx_collection_runs_started_at
    on public.collection_runs(started_at desc);

-- =========================================================
-- 6. source_pages / 取得元ページ管理
-- =========================================================
create table if not exists public.source_pages (
    source_page_id bigint generated always as identity primary key,
    run_id uuid references public.collection_runs(run_id) on delete set null,
    store_id bigint not null references public.stores(store_id),
    machine_id bigint references public.machines(machine_id),
    unit_number integer not null,
    requested_data_date date,
    source_url text not null,
    http_status smallint,
    fetched_at timestamptz not null default now(),
    source_updated_at timestamptz,
    content_hash text,
    raw_storage_path text,
    parser_version text,
    parse_status text not null default 'pending',
    error_message text,
    constraint ck_source_pages_unit_number
        check (unit_number > 0),
    constraint ck_source_pages_http_status
        check (http_status is null or http_status between 100 and 599),
    constraint ck_source_pages_parse_status
        check (parse_status in ('pending', 'success', 'partial', 'error'))
);

comment on table public.source_pages is '取得元ページ管理';
comment on column public.source_pages.source_page_id is '取得元ページID';
comment on column public.source_pages.run_id is '収集実行ID';
comment on column public.source_pages.store_id is '店舗ID';
comment on column public.source_pages.machine_id is '実台ID';
comment on column public.source_pages.unit_number is '取得時台番号';
comment on column public.source_pages.requested_data_date is '要求対象日';
comment on column public.source_pages.source_url is '取得元URL';
comment on column public.source_pages.http_status is 'HTTPステータス';
comment on column public.source_pages.fetched_at is '実取得日時';
comment on column public.source_pages.source_updated_at is 'サイト表示上の最終更新日時';
comment on column public.source_pages.content_hash is 'HTMLコンテンツハッシュ';
comment on column public.source_pages.raw_storage_path is 'Raw HTML保存先';
comment on column public.source_pages.parser_version is '解析プログラムバージョン';
comment on column public.source_pages.parse_status is '解析ステータス';
comment on column public.source_pages.error_message is '解析エラーメッセージ';

create index if not exists idx_source_pages_run_id
    on public.source_pages(run_id);

create index if not exists idx_source_pages_store_date
    on public.source_pages(store_id, requested_data_date);

create index if not exists idx_source_pages_machine_date
    on public.source_pages(machine_id, requested_data_date);

create index if not exists idx_source_pages_fetched_at
    on public.source_pages(fetched_at desc);

-- =========================================================
-- 7. store_daily_snapshots / 店舗日次スナップショット
-- =========================================================
create table if not exists public.store_daily_snapshots (
    store_id bigint not null references public.stores(store_id),
    snapshot_date date not null,
    pachinko_count integer,
    slot_count integer,
    source_page_id bigint references public.source_pages(source_page_id) on delete set null,
    observed_at timestamptz not null default now(),
    primary key (store_id, snapshot_date),
    constraint ck_store_daily_snapshots_counts
        check (
            (pachinko_count is null or pachinko_count >= 0)
            and (slot_count is null or slot_count >= 0)
        )
);

comment on table public.store_daily_snapshots is '店舗日次スナップショット';
comment on column public.store_daily_snapshots.store_id is '店舗ID';
comment on column public.store_daily_snapshots.snapshot_date is 'スナップショット日';
comment on column public.store_daily_snapshots.pachinko_count is 'パチンコ設置台数';
comment on column public.store_daily_snapshots.slot_count is 'スロット設置台数';
comment on column public.store_daily_snapshots.source_page_id is '取得元ページID';
comment on column public.store_daily_snapshots.observed_at is '観測日時';

-- =========================================================
-- 8. machine_daily_summaries / 実台日次サマリ
-- =========================================================
create table if not exists public.machine_daily_summaries (
    machine_id bigint not null references public.machines(machine_id),
    store_id bigint not null references public.stores(store_id),
    data_date date not null,
    unit_number integer not null,
    play_rate_yen numeric(8,2),
    bb_count integer,
    rb_count integer,
    art_count integer,
    current_start integer,
    max_hold integer,
    total_start integer,
    prev_day_final_start integer,
    combined_prob_denominator numeric(12,3),
    bb_prob_denominator numeric(12,3),
    rb_prob_denominator numeric(12,3),
    art_prob_denominator numeric(12,3),
    source_updated_at timestamptz,
    observed_at timestamptz not null default now(),
    source_page_id bigint references public.source_pages(source_page_id) on delete set null,
    extra_metrics jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    primary key (machine_id, data_date),
    constraint ck_machine_daily_summaries_unit
        check (unit_number > 0),
    constraint ck_machine_daily_summaries_counts
        check (
            (bb_count is null or bb_count >= 0)
            and (rb_count is null or rb_count >= 0)
            and (art_count is null or art_count >= 0)
            and (current_start is null or current_start >= 0)
            and (max_hold is null or max_hold >= 0)
            and (total_start is null or total_start >= 0)
            and (prev_day_final_start is null or prev_day_final_start >= 0)
        )
);

comment on table public.machine_daily_summaries is '実台日次サマリ';
comment on column public.machine_daily_summaries.machine_id is '実台ID';
comment on column public.machine_daily_summaries.store_id is '店舗ID';
comment on column public.machine_daily_summaries.data_date is '遊技日';
comment on column public.machine_daily_summaries.unit_number is '当日台番号';
comment on column public.machine_daily_summaries.play_rate_yen is '貸玉単価';
comment on column public.machine_daily_summaries.bb_count is 'BB回数';
comment on column public.machine_daily_summaries.rb_count is 'RB回数';
comment on column public.machine_daily_summaries.art_count is 'ART回数';
comment on column public.machine_daily_summaries.current_start is 'スタート回数';
comment on column public.machine_daily_summaries.max_hold is '最大持ち玉';
comment on column public.machine_daily_summaries.total_start is '累計スタート';
comment on column public.machine_daily_summaries.prev_day_final_start is '前日最終スタート';
comment on column public.machine_daily_summaries.combined_prob_denominator is '合成確率分母';
comment on column public.machine_daily_summaries.bb_prob_denominator is 'BB確率分母';
comment on column public.machine_daily_summaries.rb_prob_denominator is 'RB確率分母';
comment on column public.machine_daily_summaries.art_prob_denominator is 'ART確率分母';
comment on column public.machine_daily_summaries.source_updated_at is 'サイト表示上の最終更新日時';
comment on column public.machine_daily_summaries.observed_at is '観測日時';
comment on column public.machine_daily_summaries.source_page_id is '取得元ページID';
comment on column public.machine_daily_summaries.extra_metrics is '追加指標JSON';
comment on column public.machine_daily_summaries.updated_at is '更新日時';

create index if not exists idx_machine_daily_summaries_store_date
    on public.machine_daily_summaries(store_id, data_date desc);

create index if not exists idx_machine_daily_summaries_unit_date
    on public.machine_daily_summaries(store_id, unit_number, data_date desc);

-- =========================================================
-- 9. jackpot_events / 大当たり履歴
-- =========================================================
create table if not exists public.jackpot_events (
    event_id bigint generated always as identity primary key,
    machine_id bigint not null references public.machines(machine_id),
    store_id bigint not null references public.stores(store_id),
    data_date date not null,
    unit_number integer not null,
    event_seq smallint not null,
    source_row_order smallint,
    jackpot_no integer,
    start_count integer,
    payout integer,
    event_type text,
    event_time time,
    event_at timestamptz,
    source_page_id bigint references public.source_pages(source_page_id) on delete set null,
    constraint uq_jackpot_events_seq unique (machine_id, data_date, event_seq),
    constraint ck_jackpot_events_unit
        check (unit_number > 0),
    constraint ck_jackpot_events_seq
        check (event_seq > 0),
    constraint ck_jackpot_events_start
        check (start_count is null or start_count >= 0)
);

comment on table public.jackpot_events is '大当たり履歴';
comment on column public.jackpot_events.event_id is '大当たりイベントID';
comment on column public.jackpot_events.machine_id is '実台ID';
comment on column public.jackpot_events.store_id is '店舗ID';
comment on column public.jackpot_events.data_date is '遊技日';
comment on column public.jackpot_events.unit_number is '当日台番号';
comment on column public.jackpot_events.event_seq is 'イベント通番';
comment on column public.jackpot_events.source_row_order is 'HTML上行順';
comment on column public.jackpot_events.jackpot_no is '大当たり番号';
comment on column public.jackpot_events.start_count is 'スタート回数';
comment on column public.jackpot_events.payout is '出玉';
comment on column public.jackpot_events.event_type is '大当たり種別';
comment on column public.jackpot_events.event_time is 'イベント時刻';
comment on column public.jackpot_events.event_at is 'イベント日時';
comment on column public.jackpot_events.source_page_id is '取得元ページID';

create index if not exists idx_jackpot_events_machine_date_time
    on public.jackpot_events(machine_id, data_date, event_time);

create index if not exists idx_jackpot_events_store_date
    on public.jackpot_events(store_id, data_date);

-- =========================================================
-- 10. slump_points / スランプグラフ時系列
-- =========================================================
create table if not exists public.slump_points (
    slump_point_id bigint generated always as identity primary key,
    machine_id bigint not null references public.machines(machine_id),
    store_id bigint not null references public.stores(store_id),
    data_date date not null,
    unit_number integer not null,
    point_seq smallint,
    sampled_at timestamptz not null,
    slump_value integer not null,
    source_page_id bigint references public.source_pages(source_page_id) on delete set null,
    constraint uq_slump_points_sample
        unique (machine_id, data_date, sampled_at),
    constraint ck_slump_points_unit
        check (unit_number > 0),
    constraint ck_slump_points_seq
        check (point_seq is null or point_seq > 0)
);

comment on table public.slump_points is 'スランプグラフ時系列';
comment on column public.slump_points.slump_point_id is 'スランプポイントID';
comment on column public.slump_points.machine_id is '実台ID';
comment on column public.slump_points.store_id is '店舗ID';
comment on column public.slump_points.data_date is '遊技日';
comment on column public.slump_points.unit_number is '当日台番号';
comment on column public.slump_points.point_seq is 'ポイント通番';
comment on column public.slump_points.sampled_at is 'サンプル日時';
comment on column public.slump_points.slump_value is 'スランプグラフ値';
comment on column public.slump_points.source_page_id is '取得元ページID';

create index if not exists idx_slump_points_machine_date_seq
    on public.slump_points(machine_id, data_date, point_seq);

create index if not exists idx_slump_points_store_date
    on public.slump_points(store_id, data_date);

create index if not exists idx_slump_points_sampled_at
    on public.slump_points(sampled_at);

-- =========================================================
-- 11. machine_daily_metrics / 実台日次分析指標
-- =========================================================
create table if not exists public.machine_daily_metrics (
    machine_id bigint not null references public.machines(machine_id),
    data_date date not null,
    slump_final_value integer,
    slump_max_value integer,
    slump_min_value integer,
    slump_range integer,
    slump_point_count integer,
    first_sample_at timestamptz,
    last_sample_at timestamptz,
    max_start_count integer,
    avg_start_count numeric(12,3),
    max_event_payout integer,
    event_payout_sum bigint,
    calculated_at timestamptz not null default now(),
    calculation_version text,
    primary key (machine_id, data_date),
    constraint ck_machine_daily_metrics_point_count
        check (slump_point_count is null or slump_point_count >= 0),
    constraint ck_machine_daily_metrics_max_start
        check (max_start_count is null or max_start_count >= 0),
    constraint ck_machine_daily_metrics_sample_period
        check (
            first_sample_at is null
            or last_sample_at is null
            or last_sample_at >= first_sample_at
        )
);

comment on table public.machine_daily_metrics is '実台日次分析指標';
comment on column public.machine_daily_metrics.machine_id is '実台ID';
comment on column public.machine_daily_metrics.data_date is '遊技日';
comment on column public.machine_daily_metrics.slump_final_value is '最終スランプ値';
comment on column public.machine_daily_metrics.slump_max_value is '最大スランプ値';
comment on column public.machine_daily_metrics.slump_min_value is '最小スランプ値';
comment on column public.machine_daily_metrics.slump_range is 'スランプ値レンジ';
comment on column public.machine_daily_metrics.slump_point_count is 'スランプポイント数';
comment on column public.machine_daily_metrics.first_sample_at is '最初サンプル日時';
comment on column public.machine_daily_metrics.last_sample_at is '最終サンプル日時';
comment on column public.machine_daily_metrics.max_start_count is '最大スタート回数';
comment on column public.machine_daily_metrics.avg_start_count is '平均スタート回数';
comment on column public.machine_daily_metrics.max_event_payout is '最大イベント出玉';
comment on column public.machine_daily_metrics.event_payout_sum is 'イベント出玉合計';
comment on column public.machine_daily_metrics.calculated_at is '分析指標算出日時';
comment on column public.machine_daily_metrics.calculation_version is '分析ロジックバージョン';

create index if not exists idx_machine_daily_metrics_date
    on public.machine_daily_metrics(data_date desc);

-- =========================================================
-- updated_at automatic update trigger
-- =========================================================
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_stores_set_updated_at on public.stores;
create trigger trg_stores_set_updated_at
before update on public.stores
for each row execute function public.set_updated_at();

drop trigger if exists trg_models_set_updated_at on public.models;
create trigger trg_models_set_updated_at
before update on public.models
for each row execute function public.set_updated_at();

drop trigger if exists trg_machines_set_updated_at on public.machines;
create trigger trg_machines_set_updated_at
before update on public.machines
for each row execute function public.set_updated_at();

drop trigger if exists trg_machine_daily_summaries_set_updated_at
    on public.machine_daily_summaries;
create trigger trg_machine_daily_summaries_set_updated_at
before update on public.machine_daily_summaries
for each row execute function public.set_updated_at();

-- =========================================================
-- Notes
-- =========================================================
-- 1) Raw HTML itself should be stored in Supabase Storage / Object Storage.
--    source_pages.raw_storage_path stores only its path.
-- 2) machine_daily_summaries is intended to hold the latest daily state.
--    Realtime collection should UPSERT this table.
-- 3) jackpot_events.event_seq should be assigned in chronological order
--    from the start of the day so the sequence remains stable across refreshes.
-- 4) slump_points are idempotent by (machine_id, data_date, sampled_at).
-- 5) Weekly graph data is intentionally not persisted because it can be
--    reconstructed from daily slump_points and remains available in Raw HTML.
