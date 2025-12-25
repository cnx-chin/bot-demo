# acceptor/main.py

import os
import json
import uuid
import logging
from flask import Flask, request, abort
from google.cloud import tasks_v2
from context import trace_id_var

# 独自のモジュールをインポート
import config
import lineworks_api
import logger_config

# Flaskアプリケーションを作成する前に、ロギングを最初に設定する
logger_config.configure_logging()

app = Flask(__name__)

# Cloud Tasks クライアントを初期化
tasks_client = tasks_v2.CloudTasksClient()

@app.route("/callback", methods=['POST'])
def callback():
    """
    LINE WORKSからのコールバックを受信し、署名を検証し、
    Cloud Taskを作成してバックグラウンド処理をワーカーに依頼する。
    構造化ロギングとtrace_idを使用する。
    """
    # リクエストごとにユニークなtrace_idを生成
    trace_id = str(uuid.uuid4())
    trace_id_var.set(trace_id)

    # 0.受信したリクエストのヘッダーと生ボディをログに記録
    # ヘッダーは辞書に変換して記録
    request_headers = dict(request.headers)
    # ボディはbytes形式なので、デコードして記録
    request_body_str = request.get_data(as_text=True)

    logging.info({
        "message": "Acceptorがコールバックリクエストを完全に受信しました。",
        "headers": request_headers,
        "raw_body": request_body_str
    })

    # 1. 署名検証(LINE WORKSからの正当なリクエストであることを確認)
    signature_header = request.headers.get('X-WORKS-Signature')
    request_body = request.get_data()
    if not lineworks_api.verify_signature(signature_header, request_body):
        logging.warning("署名検証失敗。リクエストを破棄します。")
        abort(401)

    # 2. リクエストボディをJSONとして解析
    try:
        event_data = json.loads(request_body.decode('utf-8'))
    except json.JSONDecodeError:
        logging.error("エラー: リクエストボディのJSON解析に失敗しました。")
        # JSON解析失敗時でもLINE WORKSには200を返す
        return "OK", 200

    # 3. 必要な情報を抽出
    event_type = event_data.get('type')
    if event_type != 'message':
        logging.info(f"メッセージタイプ以外のイベント ({event_type}) を受信。処理をスキップします。")
        return "OK", 200
    
    # userIdを抽出し、構造化ログとして記録
    user_id = event_data.get('source', {}).get('userId')
    
    logging.info({
        "message": "Acceptorがコールバックリクエストを受信しました。",
        "userId": user_id,
        "eventType": event_type
    })

    content = event_data.get('content', {})
    content_type = content.get('type')

    if content_type in ['image', 'file']:
        file_id = content.get('fileId')
        if file_id:
            try:
                # 4. Cloud Taskを作成
                source = event_data.get('source', {})
                task_payload = {
                    'file_id': file_id,
                    'user_id': user_id,
                    'channel_id': source.get('channelId'),
                    'trace_id': trace_id 
                }
                
                queue_path = tasks_client.queue_path(config.GCP_PROJECT_ID, config.GCP_LOCATION, config.CLOUD_TASKS_QUEUE_ID)
                
                task = {
                    "http_request": {
                        "http_method": tasks_v2.HttpMethod.POST,
                        "url": config.WORKER_URL,
                        "headers": {"Content-Type": "application/json"},
                        "body": json.dumps(task_payload).encode(),
                        "oidc_token": {"service_account_email": config.GCP_SERVICE_ACCOUNT_EMAIL}
                    }
                }
                
                tasks_client.create_task(parent=queue_path, task=task)
                logging.info(f"Cloud Task作成成功: trace_id={trace_id}")

            except Exception as e:
                # 5. Cloud Task作成失敗時のエラーハンドリング
                logging.critical("重大なエラー: Cloud Taskの作成中に例外が発生しました。", exc_info=True)

    # 6. LINE WORKSには常に200 OKを返す
    return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)