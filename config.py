import os
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 基準日の切り替え
# ============================================================
# 通常運用：PCのシステム日付を利用
BASE_DATE = datetime.now().astimezone().date()

# 過去日を手動指定して試す場合は、上の行をコメントアウトし、下を有効化
# BASE_DATE = date.fromisoformat("2026-08-17")

# ============================================================
# マスタ / Playwright / 保存設定
# ============================================================
UNIT_MAPPING_CSV = Path("./master/unit_mapping.csv")
PROFILE_DIR = Path("./browser_profile").resolve()
RAW_DIR = Path("./data/raw")
PROCESSED_DIR = Path("./data/processed")
SLUMP_DIR = Path("./data/slump")

HEADLESS = True
WAIT_SECONDS = 2.0
NAVIGATION_TIMEOUT_MS = 30_000

# ============================================================
# Supabase
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# サーバー側の収集・取込処理専用。フロントエンドには絶対に渡さないこと。
SUPABASE_KEY = SUPABASE_SERVICE_ROLE_KEY

SOURCE_SYSTEM = os.getenv("SOURCE_SYSTEM", "daidata").strip() or "daidata"
PARSER_VERSION = os.getenv("PARSER_VERSION", "v3.0.0").strip() or "v3.0.0"
COLLECTOR_VERSION = os.getenv("COLLECTOR_VERSION", "v3.0.0").strip() or "v3.0.0"
