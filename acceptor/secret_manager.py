import os
import logging
from google.cloud import secretmanager

# クライアントを初期化
client = secretmanager.SecretManagerServiceClient()

# 環境変数からGCPプロジェクトIDを取得
# 環境変数が設定されていない場合、gcloudのデフォルトプロジェクトが使用される
project_id = os.environ.get('GCP_PROJECT_ID', 'sunny-resolver-460603-m3') 

# 取得したシークレットをキャッシュするための辞書
_secret_cache = {}

# センシティブな情報のキーを定義（これらのキーの値はログに出力しない）
SENSITIVE_KEYS = [
    'LINEWORKS_BOT_SECRET',
    'SA_CLIENT_ID',
    'SA_CLIENT_SECRET',
    'SA_PRIVATE_KEY',
    'AWS_ACCESS_KEY_ID',
    'AWS_SECRET_ACCESS_KEY'
]

def get_secret(secret_id: str, logger: logging.Logger, version_id: str = "latest") -> str:
    """
    Secret Managerからシークレットの値を取得し、キャッシュし、ログを記録する関数。
    """
    # 1. 環境変数を最優先で確認
    env_val = os.environ.get(secret_id)
    if env_val:
        log_payload = {
            "message": "Loaded secret from environment variable.",
            "secret_id": secret_id,
            "source": "environment_variable"
        }
        if secret_id not in SENSITIVE_KEYS:
            log_payload["value"] = env_val
        else:
            log_payload["value_length"] = len(env_val)
        logger.info(log_payload)
        return env_val.strip()

    # キャッシュキーを作成
    cache_key = f"{secret_id}:{version_id}"

    # まずキャッシュを確認
    if cache_key in _secret_cache:
        # キャッシュから値を返す場合も、それがセンシティブでないならログに記録
        cached_value = _secret_cache[cache_key]
        log_payload = {
            "message": "Loaded secret from cache.",
            "secret_id": secret_id,
            "source": "cache"
        }
        if secret_id not in SENSITIVE_KEYS:
            log_payload["value"] = cached_value
        else:
            log_payload["value_length"] = len(cached_value)
        logger.info(log_payload)
        return cached_value

    # シークレットの完全なリソース名を構築
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"

    try:
        # シークレットバージョンにアクセス
        response = client.access_secret_version(request={"name": name})
        
        # ペイロードをデコードし、前後の空白や改行を削除
        payload = response.payload.data.decode("UTF-8").strip()
        
        # 結果をキャッシュに保存
        _secret_cache[cache_key] = payload
        
        # ログを記録
        log_payload = {
            "message": "Successfully loaded secret.",
            "secret_id": secret_id,
            "source": "Secret Manager"
        }
        if secret_id not in SENSITIVE_KEYS:
            log_payload["value"] = payload
        else:
            log_payload["value_length"] = len(payload)
        logger.info(log_payload)
        
        return payload
    except Exception as e:
        logger.critical(f"CRITICAL: Failed to access secret: {secret_id}. Details: {e}", exc_info=True)
        return None
