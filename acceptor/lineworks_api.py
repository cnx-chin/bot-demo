import base64
import hashlib
import hmac
import logging

# 独自のモジュールをインポート
import config

def verify_signature(signature_header, request_body):
    """
    LINE WORKSからのコールバックリクエストの署名を検証する。
    この関数は、リクエストがLINE WORKSから正当に送られたものであることを保証する。
    """
    # X-WORKS-Signature ヘッダーが存在しない場合は検証失敗
    if not signature_header:
        logging.error("エラー: X-WORKS-Signature ヘッダーが見つかりません。")
        return False

    try:
        # Bot Secretを秘密鍵として使用し、リクエストボディをHMAC-SHA256でハッシュ化
        secret_key_bytes = config.LINEWORKS_BOT_SECRET.encode('utf-8')
        body_bytes = request_body # request_bodyは既にbytes形式
        
        hash_obj = hmac.new(secret_key_bytes, body_bytes, hashlib.sha256).digest()
        
        # ハッシュ化した結果をBase64エンコード
        calculated_signature = base64.b64encode(hash_obj)

        # 受信した署名と計算した署名が一致するかどうかを比較

        if hmac.compare_digest(calculated_signature, signature_header.encode('utf-8')):
            return True
        else:
            logging.error("エラー: 署名が一致しません！")
            return False
    except Exception as e:
        logging.error("エラー: 署名検証中に例外が発生しました: {e}")
        return False