import logging
from secret_manager import get_secret

# このモジュール用のロガーをセットアップ
config_logger = logging.getLogger(__name__)

# --- LINE WORKS Bot 設定 (署名検証に必要) ---
LINEWORKS_BOT_SECRET = get_secret('LINEWORKS_BOT_SECRET', logger=config_logger)

# --- Google Cloud 設定 ---
GCP_PROJECT_ID = get_secret('GCP_PROJECT_ID', logger=config_logger)
GCP_LOCATION = get_secret('GCP_LOCATION', logger=config_logger)
CLOUD_TASKS_QUEUE_ID = get_secret('CLOUD_TASKS_QUEUE_ID', logger=config_logger)

# --- ワーカーサービス設定 ---
# ワーカーサービスのCloud Run URL
WORKER_URL = get_secret('WORKER_URL', logger=config_logger)

# --- サービスアカウント設定 (OIDCトークン作成に必要) ---
# Cloud Tasksがワーカーサービスを呼び出す際に使用するサービスアカウントのメールアドレス
GCP_SERVICE_ACCOUNT_EMAIL = get_secret('GCP_SERVICE_ACCOUNT_EMAIL', logger=config_logger)