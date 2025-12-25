import os
from pathlib import Path
import logging
from secret_manager import get_secret

# ロガーを設定
logger = logging.getLogger(__name__)

# --- LINE WORKS Bot 設定 ---
LINEWORKS_BOT_ID = get_secret('LINEWORKS_BOT_ID', logger)

# --- LINE WORKS API 設定 ---
LINEWORKS_API_BASE = "https://www.worksapis.com/v1.0"
LINEWORKS_TOKEN_URL = 'https://auth.worksmobile.com/oauth2/v2.0/token'

# --- Service Account 設定 ---
SA_CLIENT_ID = get_secret('SA_CLIENT_ID', logger)
SA_CLIENT_SECRET = get_secret('SA_CLIENT_SECRET', logger)
SA_SERVICE_ACCOUNT = get_secret('SA_SERVICE_ACCOUNT', logger)
# !!! 重要: keyファイルのパスを間違いないように設定 !!!
# このパスはCloud Runのボリュームマウントによって提供される
SA_PRIVATE_KEY_PATH = os.environ.get('SA_PRIVATE_KEY_PATH')

# ---Bot権限スコープ ---
SA_SCOPES = 'bot bot.message user.read orgunit.read'

# ---AWS S3 設定  ---
AWS_S3_BUCKET_NAME = get_secret('AWS_S3_BUCKET_NAME', logger)
AWS_ACCESS_KEY_ID = get_secret('AWS_ACCESS_KEY_ID', logger)
AWS_SECRET_ACCESS_KEY = get_secret('AWS_SECRET_ACCESS_KEY', logger)
AWS_S3_REGION = get_secret('AWS_S3_REGION', logger)

# アップロード先のGCSバケット名
GCS_BUCKET_NAME = get_secret('GCS_BUCKET_NAME', logger)

# ---Document AI 設定 ---
# Document AI プロセッサが設置されているリージョン
DOC_AI_LOCATION = get_secret('DOC_AI_LOCATION', logger)
# トレーニングしたプロセッサのID
DOC_AI_PROCESSOR_ID = get_secret('DOC_AI_PROCESSOR_ID', logger)
# 特定のバージョンのID
DOC_AI_PROCESSOR_VERSION_ID = get_secret('DOC_AI_PROCESSOR_VERSION_ID', logger)
# GCPプロジェクトIDは他の場所でも使われるため、一元管理
GCP_PROJECT_ID = get_secret('GCP_PROJECT_ID', logger)

# --- CSV とファイル処理設定 ---
KEYWORDS = ["クレジット支払", "クレジット受入", "現金支払", "現金受入"]
# タイトル揺らぎ補正用の特徴文字セット（原子レベルでのAND検索用）
CREDIT_CHARS = {'ク', 'レ', 'ジ', 'ッ', 'ト'}
CASH_CHARS = {'現', '金'}
PAYMENT_CHARS = {'支', '払'}
RECEIPT_CHARS = {'受', '入'}

DEFAULT_PREFIX = "unknown_form"


# --- その他の設定 ---
# Access Token キャッシュの事前更新時間（秒）
TOKEN_REFRESH_BUFFER = 300 # 5分
# Access Token デフォルト有効期間（秒）
DEFAULT_TOKEN_EXPIRY = 3600 # 1時間