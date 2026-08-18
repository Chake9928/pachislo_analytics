from config import SUPABASE_KEY, SUPABASE_URL


def create_supabase_client():
    if not SUPABASE_URL:
        raise RuntimeError(
            "SUPABASE_URL が未設定です。.env に Supabase Project URL を設定してください。"
        )
    if not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY が未設定です。.env にサーバー側専用キーを設定してください。"
        )

    try:
        from supabase import Client, create_client
    except ImportError as exc:
        raise RuntimeError(
            "supabase パッケージがありません。pip install -r requirements.txt を実行してください。"
        ) from exc

    client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return client


def first_or_none(response):
    data = getattr(response, "data", None) or []
    return data[0] if data else None
