import os
import ssl

from config import SUPABASE_KEY, SUPABASE_URL


def _build_ssl_context():
    """公開CAとOS/社内CAの両方を信頼する。

    httpx は既定で certifi のみを使うため、Netskope 等の
    社内SSL検査CAが Windows 証明書ストアにあっても検証に失敗する。
    """
    cafile = (
        os.environ.get("SSL_CERT_FILE")
        or os.environ.get("REQUESTS_CA_BUNDLE")
        or os.environ.get("CURL_CA_BUNDLE")
    )
    if cafile:
        ctx = ssl.create_default_context(cafile=cafile)
    else:
        try:
            import certifi

            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()

    ctx.load_default_certs()
    return ctx


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
        # from supabase import Client, create_client
        import httpx
        from supabase import Client, ClientOptions, create_client
    except ImportError as exc:
        raise RuntimeError(
            "supabase パッケージがありません。pip install -r requirements.txt を実行してください。"
        ) from exc

    # client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    http_client = httpx.Client(verify=_build_ssl_context())
    client: Client = create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(httpx_client=http_client),
    )
    return client


def first_or_none(response):
    data = getattr(response, "data", None) or []
    return data[0] if data else None
