import os
from google.cloud import secretmanager
import logging

# ロガーを取得
logger = logging.getLogger(__name__)

# クライアントインスタンスをキャッシュするグローバル変数（遅延初期化用）
_client = None

# API呼び出し頻度を減らすためのキャッシュ
_secret_cache = {}

# フォールバック用のプロジェクトID（Cloud Runの環境変数が設定されていない場合に使用）
_FALLBACK_PROJECT_ID = 'sunny-resolver-460603-m3'

def _get_client():
    """
    SecretManagerServiceClientのシングルトンを取得する。
    初回呼び出し時のみ初期化を行う（遅延ロード）。
    """
    global _client
    if _client is None:
        _client = secretmanager.SecretManagerServiceClient()
    return _client

def _get_project_id():
    """
    GCPプロジェクトIDを取得する。
    環境変数を優先し、設定されていない場合はフォールバック値を使用する。
    """
    project_id = os.environ.get('GCP_PROJECT_ID')
    if not project_id:
        # 環境変数が設定されていない場合、警告を出力してフォールバック値を使用
        logger.warning(f"GCP_PROJECT_ID not set in environment. Using fallback: {_FALLBACK_PROJECT_ID}")
        return _FALLBACK_PROJECT_ID
    return project_id

def get_secret(secret_id: str, logger_instance=None, version_id: str = "latest") -> str:
    """
    Secret Managerからシークレットの値を取得し、キャッシュする関数。
    """
    # ロガーが渡されていない場合はモジュールレベルのロガーを使用
    log = logger_instance or logger

    # 1. 環境変数を最優先で確認
    env_val = os.environ.get(secret_id)
    if env_val:
        log.info(f"Loaded secret '{secret_id}' from environment variable.")
        return env_val.strip()

    # プロジェクトIDを取得
    project_id = _get_project_id()

    # キャッシュキーを作成
    cache_key = f"{secret_id}:{version_id}"

    # まずキャッシュを確認
    if cache_key in _secret_cache:
        return _secret_cache[cache_key]

    # クライアントを取得（ここで初めてGCP接続が初期化される）
    try:
        client = _get_client()
    except Exception as e:
        log.error(f"Failed to initialize Secret Manager Client: {e}")
        raise e

    # シークレットの取得処理
    try:
        # version_id が "latest" の場合、最新の有効なバージョンを検索
        if version_id == "latest":
            
            secret_path = f"projects/{project_id}/secrets/{secret_id}"
            # list_secret_versions は例外をスローする可能性がある
            versions = client.list_secret_versions(request={"parent": secret_path})
            
            # 有効なバージョンを探す（デフォルトで新しい順）
            target_name = None
            for version in versions:
                if version.state == secretmanager.SecretVersion.State.ENABLED:
                    target_name = version.name
                    log.info(f"Using enabled version: {target_name}")
                    break
            
            if not target_name:
                raise Exception(f"No enabled versions found for secret: {secret_id}")
            
            name = target_name
        else:
            name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
            
        # シークレットバージョンにアクセス
        response = client.access_secret_version(request={"name": name})
        
        # ペイロードをデコード
        payload = response.payload.data.decode("UTF-8").strip()
        
        # 結果をキャッシュに保存
        _secret_cache[cache_key] = payload
        
        return payload
    except Exception as e:
        log.error(f"Error accessing secret: {secret_id}. Details: {e}")
        # エラーが発生した場合は、Noneを返す代わりに例外を再発生させる
        raise e