# logger_config.py

import logging
from google.cloud.logging.handlers import CloudLoggingHandler, setup_logging
import google.cloud.logging

# 独自のモジュールをインポート
import config
from context import trace_id_var 

class CloudTraceFilter(logging.Filter):
    """
    ログレコードに、Google Cloud Loggingがネイティブに認識する
    'trace'フィールドと、検索用の'traceId'フィールドを追加するフィルター。
    """
    def filter(self, record):
        trace_id = trace_id_var.get()
        record.trace = f"projects/{config.GCP_PROJECT_ID}/traces/{trace_id}"
        
        # jsonPayloadに独立したフィールドとして追加
        record.json_fields = {
            "traceId": trace_id
        }
        return True

def configure_logging():
    """
    CloudLoggingHandlerと公式のヘルパー関数を使用して、
    構造化ロギングとネイティブなTraceIDの付与を設定する。
    """
    client = google.cloud.logging.Client()
    
    # ハンドラを作成
    handler = CloudLoggingHandler(client, name="bot-ocr-worker")

    # フィルターをハンドラに追加
    handler.addFilter(CloudTraceFilter())
    
    # ハンドラをロガーに設定
    setup_logging(handler)
    
    # アプリケーション全体のログレベルを設定
    logging.getLogger().setLevel(logging.INFO)

    print("構造化ロギングが設定されました（公式ヘルパー関数使用）。")