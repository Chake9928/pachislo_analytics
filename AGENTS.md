# AGENTS.md

## Project
パチスロ店舗データを収集・分析するシステム。

## Stack
- Python 3.10+
- Playwright
- BeautifulSoup
- Supabase / PostgreSQL

## Architecture
- collector: HTML取得
- raw: HTML保存
- parser: HTMLから構造化データ抽出
- db: SupabaseへのINSERT/UPSERT
- Raw HTMLと構造化データを分離する

## Data model rules
- 台番号を実台IDとして扱わない
- machine_idは実台個体の不変ID
- unit_numberは配置履歴
- store_id / model_id / machine_id / data_dateを分析軸とする
- HTML取得日時と遊技日を混同しない

## Development rules
- 既存DDLとの整合性を確認してからDB処理を変更する
- 修正後は必ずテストを実行する
- 既存データを壊す変更は勝手に行わない
- .envや秘密鍵をGitへコミットしない