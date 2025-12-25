# lineworks_api.py
import requests
import jwt
import time
import json
import base64
import hmac
import hashlib
import threading
from datetime import datetime
import re
import logging

# 配置pyをインポート
import config

# --- Access Token 管理 ---
_cached_token = None
_token_expiry_time = 0
_token_lock = threading.Lock()

def generate_new_access_token():
    """Service Account JWTを用いて新たなAccess Token"""
    global _cached_token, _token_expiry_time
    logging.info("新しい Access Token を取得中...")
    try:
        with open(config.SA_PRIVATE_KEY_PATH, 'r') as f:
            private_key = f.read()

        iat = int(time.time())
        # JWTの有効期限が長くなるとセキュリティに支障が出る可能性あり
        exp = iat + 300 # JWT 有効期限 5分

        payload = {
            'iss': config.SA_CLIENT_ID,
            'sub': config.SA_SERVICE_ACCOUNT,
            'iat': iat,
            'exp': exp,
            'scope': config.SA_SCOPES
        }

        jwt_token = jwt.encode(payload, private_key, algorithm='RS256')

        response = requests.post(
            config.LINEWORKS_TOKEN_URL,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'assertion': jwt_token,
                'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                'client_id': config.SA_CLIENT_ID,
                'client_secret': config.SA_CLIENT_SECRET, 
                'scope': config.SA_SCOPES
            },
            timeout=30
        )
        response.raise_for_status()
        token_data = response.json()
        new_token = token_data.get('access_token')
        expires_in_value = token_data.get('expires_in', config.DEFAULT_TOKEN_EXPIRY)

        try:
            expires_in_int = int(expires_in_value)
        except (ValueError, TypeError) as e:
            logging.warning(f"警告: APIから返された 'expires_in' ({expires_in_value}) を整数に変換できませんでした。デフォルト値 {config.DEFAULT_TOKEN_EXPIRY} を使用します。エラー: {e}")
            expires_in_int = config.DEFAULT_TOKEN_EXPIRY

        if not new_token:
            logging.critical("エラー: Token API レスポンスに access_token がありません。")
            _cached_token = None
            _token_expiry_time = 0
            return None

        _cached_token = new_token
        _token_expiry_time = time.time() + expires_in_int - config.TOKEN_REFRESH_BUFFER
        logging.info(f"新しい Access Token 取得成功。有効期限: {datetime.fromtimestamp(_token_expiry_time)}")
        return _cached_token

    except FileNotFoundError:
        logging.error(f"エラー: Private Key ファイルが見つかりません: {config.SA_PRIVATE_KEY_PATH}")
        return None
    except Exception as e:
        logging.error(f"エラー: Access Token の取得中にエラーが発生しました: {e}")
        if hasattr(e, 'response') and e.response is not None:
             logging.critical(f"  -> Response Status: {e.response.status_code}, Body: {e.response.text}")
        return None

def get_valid_access_token():
    """有効なAccess Tokenの取得（キャッシュおよびスレッドセーフ付き）"""
    with _token_lock:
        if _cached_token and time.time() < _token_expiry_time:
            return _cached_token
        else:
            return generate_new_access_token()

def get_lw_api_headers(include_content_type=True):
    """LINE WORKS API を呼び出すために必要な基本ヘッダーの取得（動的にトークンを取得）"""
    access_token = get_valid_access_token()
    if not access_token:
        raise ValueError("有効な Access Token を取得できませんでした。")
    headers = {'Authorization': f'Bearer {access_token}'}
    if include_content_type:
        headers['Content-Type'] = 'application/json'
    return headers

def get_user_info(user_id):
    """
    指定されたユーザーIDのユーザー情報を取得する (GET /users/{userId})。
    成功した場合はユーザー情報のJSONを、失敗した場合は(None, エラーメッセージ)を返す。
    """
    if not user_id:
        return None, "user_idが指定されていません。"
    
    url = f"{config.LINEWORKS_API_BASE}/users/{user_id}"
    try:
        headers = get_lw_api_headers(include_content_type=False)
        logging.info(f"ユーザー情報取得 API 呼び出し開始: userId={user_id}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status() # 2xx以外のステータスコードで例外を発生させる
        return response.json(), None
    except ValueError as e:
        return None, f"ユーザー情報取得のためのAccess Token取得失敗: {e}"
    except requests.exceptions.RequestException as e:
        error_message = f"ユーザー情報取得API呼び出しに失敗しました: {e}"
        if e.response is not None:
            error_message += f" Status: {e.response.status_code}, Body: {e.response.text}"
        logging.error(f"エラー: {error_message}")
        return None, error_message

def get_org_unit_info(org_unit_id):
    """
    指定された組織IDの組織情報を取得する (GET /orgunits/{orgUnitId})。
    成功した場合は組織情報のJSONを、失敗した場合は(None, エラーメッセージ)を返す。
    """
    if not org_unit_id:
        return None, "org_unit_idが指定されていません。"

    url = f"{config.LINEWORKS_API_BASE}/orgunits/{org_unit_id}"
    try:
        headers = get_lw_api_headers(include_content_type=False)
        logging.info(f"組織情報取得 API 呼び出し開始: orgUnitId={org_unit_id}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json(), None
    except ValueError as e:
        return None, f"組織情報取得のためのAccess Token取得失敗: {e}"
    except requests.exceptions.RequestException as e:
        error_message = f"組織情報取得API呼び出しに失敗しました: {e}"
        if e.response is not None:
            error_message += f" Status: {e.response.status_code}, Body: {e.response.text}"
        logging.error(f"エラー: {error_message}")
        return None, error_message


def download_lw_attachment(file_id):
    """LINE WORKS から添付ファイルの内容をダウンロード（302 を手動で処理し、2 回目のステップで認証情報を含む）"""
    if not file_id: return None, "fileId is missing"
    initial_url = f"{config.LINEWORKS_API_BASE}/bots/{config.LINEWORKS_BOT_ID}/attachments/{file_id}"
    try:
        headers_step1 = get_lw_api_headers(include_content_type=False)
        logging.info(f"ダウンロードリダイレクトURL取得 API 呼び出し開始: fileId={file_id}")
        response_initial = requests.get(initial_url, headers=headers_step1, timeout=30, allow_redirects=False)

        if response_initial.status_code == 302:
            download_url = response_initial.headers.get('Location')
            if not download_url: return None, "ダウンロードURLが見つかりませんでした（Locationヘッダー欠落）。"
            logging.info(f"リダイレクトURL取得成功: {download_url}")
            logging.info(f"実際のダウンロード開始 (Authorization ヘッダ付き): {download_url}")
            headers_step2 = {'Authorization': headers_step1['Authorization']}
            response_content = requests.get(download_url, headers=headers_step2, timeout=120)
            response_content.raise_for_status()
            logging.info(f"実際のダウンロード成功: fileId={file_id}, Content-Type={response_content.headers.get('Content-Type')}")
            return response_content.content, None
        else:
            error_message = f"ダウンロードURLの取得に失敗しました。Status: {response_initial.status_code}"
            try: error_message += f", Body: {response_initial.text}"
            except Exception: pass
            logging.error(f"エラー: {error_message}")
            if response_initial.status_code == 401: return None, "アクセストークンが無効か、このAPIを呼び出す権限（Scope）がありません。"
            return None, error_message
    except ValueError as e: return None, f"Access Token 取得失敗: {e}"
    except requests.exceptions.RequestException as e:
        logging.error(f"エラー: 添付ファイルのダウンロード処理中にエラー: {e}")
        return None, f"添付ファイルのダウンロード処理中にエラーが発生しました: {e}"
    except Exception as e:
        logging.error(f"エラー: 添付ファイルのダウンロード中に予期せぬエラー: {e}")
        return None, f"添付ファイルのダウンロード中に予期せぬエラーが発生しました: {e}"

def upload_lw_attachment(filename, file_content_bytes):
    """LINE WORKS にファイルをアップロード（2 ステップのプロセス、2 ステップ目は POST + multipart を使用）し、fileId を取得"""
    step1_url = f"{config.LINEWORKS_API_BASE}/bots/{config.LINEWORKS_BOT_ID}/attachments"
    step1_payload = json.dumps({"fileName": filename})
    try:
        headers_step1 = get_lw_api_headers()
        logging.info(f"アップロードURL取得 API 呼び出し開始: filename={filename}")
        response_step1 = requests.post(step1_url, headers=headers_step1, data=step1_payload, timeout=30)
        response_step1.raise_for_status()
        result_step1 = response_step1.json()
        file_id = result_step1.get('fileId')
        upload_url = result_step1.get('uploadUrl')
        if not file_id or not upload_url: return None, "アップロードURLまたはFileIDを取得できませんでした。"
        logging.info(f"アップロードURL取得成功: fileId={file_id}, uploadUrl={upload_url}")
    except ValueError as e: return None, f"Step 1 Access Token 取得失敗: {e}"
    except requests.exceptions.RequestException as e:
        logging.error(f"エラー: アップロードURL/FileID の取得に失敗しました: {e}")
        return None, f"アップロードURL/FileID の取得に失敗しました: {e}"
    except Exception as e: return None, f"アップロードURL/FileID 取得中に予期せぬエラー: {e}"

    try:
        logging.info(f"実際のファイルアップロード開始 (POST multipart): url={upload_url}")
        files_param = {'file': (filename, file_content_bytes, 'text/csv')}
        access_token = get_valid_access_token()
        if not access_token: return None, "Step 2 Access Token 取得失敗"
        headers_step2 = {'Authorization': f'Bearer {access_token}'}
        response_step2 = requests.post(upload_url, headers=headers_step2, files=files_param, timeout=120)
        response_step2.raise_for_status()
        logging.info(f"実際のファイルアップロード成功: fileId={file_id}")
        return file_id, None
    except ValueError as e: return None, f"Step 2 Access Token 取得失敗: {e}"
    except requests.exceptions.RequestException as e:
        logging.error(f"エラー: 実際のファイルアップロードに失敗しました (fileId: {file_id}): {e}")
        error_message = f"実際のファイルアップロードに失敗しました: {e}"
        if hasattr(e, 'response') and e.response is not None:
             logging.error(f"  -> Response Status: {e.response.status_code}, Body: {e.response.text}")
             error_message += f" Status: {e.response.status_code}, Body: {e.response.text}"
        return None, error_message
    except Exception as e:
        logging.error(f"エラー: 実際のファイルアップロード中に予期せぬエラー (fileId: {file_id}): {e}")
        return None, f"実際のファイルアップロード中に予期せぬエラー: {e}"

def send_lw_message(recipient_id, content_payload):
    """ユーザーまたはチャンネルにメッセージを送信"""
    if not recipient_id: return "recipient_id is missing"
    is_user = bool(re.match(r'^[a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12}$', recipient_id))
    if is_user: url = f"{config.LINEWORKS_API_BASE}/bots/{config.LINEWORKS_BOT_ID}/users/{recipient_id}/messages"
    else: url = f"{config.LINEWORKS_API_BASE}/bots/{config.LINEWORKS_BOT_ID}/channels/{recipient_id}/messages"
    try:
        headers = get_lw_api_headers()
        logging.info(f"メッセージ送信 API 呼び出し開始: recipient={recipient_id}, content type={content_payload.get('content',{}).get('type')}")
        response = requests.post(url, headers=headers, json=content_payload, timeout=60)
        response.raise_for_status()
        logging.info(f"メッセージ送信 API 成功: recipient={recipient_id}")
        return None
    except ValueError as e: return f"Access Token 取得失敗: {e}"
    except requests.exceptions.RequestException as e:
        logging.error(f"エラー: メッセージ送信中にエラー: {e}")
        return f"メッセージ送信中にエラーが発生しました: {e}"
    except Exception as e:
        logging.error(f"エラー: メッセージ送信中に予期せぬエラー: {e}")
        return f"メッセージ送信中に予期せぬエラーが発生しました: {e}"

def get_store_code_by_user(user_id):
    """
    ユーザーIDから所属組織の店舗コード（組織のdescription）を取得する。
    """
    logging.info(f"ユーザー情報の取得を開始: userId={user_id}")
    user_info, err = get_user_info(user_id)
    if err: return None, f"ユーザー情報の取得に失敗しました: {err}"

    try:
        org_unit_id = user_info['organizations'][0]['orgUnits'][0]['orgUnitId']
    except (IndexError, KeyError) as e:
        return None, f"ユーザー情報から組織IDの解析に失敗しました: {e}"
        
    logging.info(f"組織情報の取得を開始: orgUnitId={org_unit_id}")
    org_unit_info, err = get_org_unit_info(org_unit_id)
    if err: return None, f"組織情報の取得に失敗しました: {err}"
        
    store_code = org_unit_info.get('description')
    if not store_code: return None, "組織情報に店舗コードが設定されていません。"
        
    return store_code, None