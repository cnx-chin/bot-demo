# worker/main.py

import os
import json
from flask import Flask, request, abort
import uuid 
import logging 
from context import trace_id_var

# 独自のモジュールをインポート
import tasks
import logger_config 

# Flaskアプリケーションを作成する前に、ロギングを最初に設定する
logger_config.configure_logging()

app = Flask(__name__)

@app.route("/worker", methods=['POST'])
def worker_endpoint():
    """
    Cloud Tasksからタスクを受信し、処理を実行するエンドポイント。
    構造化ロギングを使用する。
    """
    task_data = request.get_json(force=True)
    
    # acceptorから渡されたtrace_idを取得、なければ新規作成
    # これにより、リクエストのライフサイクル全体を追跡できる
    trace_id = task_data.get('trace_id', str(uuid.uuid4()))
    trace_id_var.set(trace_id)

    # ログにtrace_idを含めることで、検索やフィルタリングが容易になる
    logging.info(f"ワーカーがタスクを受信しました。ペイロード: {task_data}")

    try:
        file_id = task_data.get('file_id')
        if not file_id:
            logging.error("エラー: task_dataにfile_idが含まれていません。")
            # 不正なリクエスト。再試行は無意味なので400を返す。
            return "Bad Request: file_id is missing", 400
        user_id=task_data.get('user_id')

        # メインの処理ロジックを呼び出す
        # 成功した場合はそのまま完了する。
        # 失敗した場合は、この関数が例外を投げる。
        tasks.process_image_and_reply(
            file_id=file_id,
            user_id=user_id,
            channel_id=task_data.get('channel_id'),
            trace_id=trace_id 
        )

        # 正常に完了した場合
        logging.info(f"ワーカー処理成功: user_id={user_id}")
        # Cloud Tasksに成功を通知
        return "Task completed successfully", 200

    except Exception as e:
        # tasks.process_image_and_replyの内部で発生したすべての例外を捕捉する。
        # このブロックに来た時点で「タスク失敗」が確定。
        # ユーザーへのエラー通知は、上記の関数内で行われている。
        # exc_info=True を付けることで、完全なエラーのスタックトレースがログに自動的に記録される
        logging.error(f"ハンドリングされたエラー: {e}タスクを失敗としてマークします。", exc_info=True)
        return f"Task failed: {e}", 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)