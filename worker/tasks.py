import logging
import datetime
import os

# 独自のモジュールをインポート
import lineworks_api
import document_ai_processor
import doc_ai_parser
import csv_generator
import gcs_uploader
import s3_uploader
import config
import image_processor
from google.cloud import documentai # デバッグ用


def process_image_and_reply(file_id, user_id, channel_id, trace_id: str):
    """
    ファイルの取得からDocument AIでの処理、S3とCloud storageへのアップロード、成功通知までの全プロセスを処理する。
    構造化ロギングを使用する。
    """

    recipient_id = user_id if user_id else channel_id
    if not recipient_id:
        # このエラーはmain.pyに捕捉される
        raise ValueError("受信者IDが不明。")

    user_facing_error = ""
    try:
        # --- 1. 店舗コードを取得 ---
        logging.info("ステップ1: 店舗コードの取得を開始...")
        store_code, err = lineworks_api.get_store_code_by_user(user_id)
        if err:
            user_facing_error = f"店舗コードを取得できませんでした。ITHDへお問い合わせください。"
            raise Exception(f"店舗コードの取得に失敗しました: {err}")
        logging.info(f"店舗コード取得成功: {store_code}")

        # --- 2. ファイルをダウンロード ---
        logging.info(f"ステップ2: ファイルのダウンロードを開始: fileId={file_id}")
        file_bytes, err = lineworks_api.download_lw_attachment(file_id)
        if err:
            user_facing_error = f"写真の処理に失敗しました。お手数ですが、テレマスにて手入力してください。"
            raise Exception(f"Download failed: {err}")

        # --- 2.5 画像の前処理 (回転補正 & 影除去) ---
        logging.info("ステップ2.5: 画像の前処理(回転補正・影除去)を開始...")
        processed_file_bytes = image_processor.process_image(file_bytes)

        # --- 3. Document AIでファイルを処理 ---
        # 処理済みの画像を使用することでOCR精度を向上させる
        logging.info("ステップ3: Document AIでの処理を開始...")
        document, err = document_ai_processor.process_document(processed_file_bytes, 'image/jpeg')
        if err:
            user_facing_error = "写真の読み取り処理（OCR）中にエラーが発生しました。お手数ですが、テレマスにて手入力してください。"
            raise Exception(f"Document AI failed: {err}")

        # --- 4. AIの解析結果を構造化データに変換 ---
        logging.info("ステップ4: AI解析結果の構造化を開始...")
        parsed_data, is_review_needed, user_warning = doc_ai_parser.parse_document_entities(document)
        if not parsed_data or not parsed_data.get('title'):
            # タイトルが読み取れなかった場合、画像をレビュー用フォルダに保存する
            # 原本画像と処理済み画像の両方を保存する
            gcs_uploader.upload_error_image(store_code, file_bytes, processed_image_bytes=processed_file_bytes)
            user_facing_error = "写真の処理に失敗しました。出納票の写真を正しく撮影して、もう一度アップロードするか、テレマスにて手入力してください。"
            raise Exception("No valid data parsed from document.")

        # --- 4.5. タイトルがキーワードに存在するかチェック ---
        title = parsed_data.get('title', '')
        if title not in config.KEYWORDS:
            user_facing_error = "写真の処理に失敗しました。出納票の写真を正しく撮影して、もう一度アップロードするか、テレマスにて手入力してください。"
            raise Exception(f"Title '{title}' not in recognized keywords.")

        # --- 5. CSVファイル内容(BOMなし)を生成 ---
        logging.info("ステップ5: CSVファイル内容の生成を開始...")
        csv_content, err = csv_generator.generate_csv_content(parsed_data)
        if err:
            user_facing_error = "ファイルの作成に失敗しました。お手数ですが、テレマスにて手入力してください。"
            raise Exception(f"CSV generation failed: {err}")
        csv_content_bytes = csv_content.encode('utf-8')

        # --- 6. GCS/S3用のファイル名を生成 ---
        gcs_filename = csv_generator.generate_csv_filename(store_code, parsed_data.get('title'))
        logging.info(f"生成されたファイル名: {gcs_filename}")   

        # --- 7. GCSへ成果物をアップロード ---
        logging.info("ステップ7: GCSへの成果物アップロードを開始...")
        try:
            gcs_uploader.upload_processed_results(
                is_review_needed=is_review_needed,
                store_code=store_code,
                csv_filename=gcs_filename,
                image_bytes=file_bytes,
                csv_bytes=csv_content_bytes,
                processed_image_bytes=processed_file_bytes
            )
        except Exception:
            # この処理はノンクリティカルなので、失敗しても警告ログのみで処理を続行
            logging.warning("GCSへの成果物アップロード中に予期せぬエラーが発生しました。", exc_info=True)

        # --- 8. S3（検証環境）へアップロード ---
        logging.info("ステップ8: S3へのアップロードを開始...")
        _, err = s3_uploader.upload_to_s3(csv_content_bytes, gcs_filename)
        if err:
            user_facing_error = "処理結果を保存する際にエラーが発生しました。お手数ですが、テレマスにて手入力してください。"
            raise Exception(f"S3 Upload failed: {err}")

        # --- 9. ユーザーに成功を通知 ---
        logging.info("ステップ9: ユーザーへの成功通知を送信...")
        success_message = f"「{title}」の処理とアップロードが正常に完了しました。"
        
        if user_warning:
            success_message = f"「{title}」{user_warning}"

        success_payload = {"content": {"type": "text", "text": success_message}}
        err = lineworks_api.send_lw_message(recipient_id, success_payload)
        if err:
            raise Exception(f"成功メッセージの送信に失敗しました: {err}")

    except Exception as e:
        # --- 統一エラー処理 ---
        # ユーザーに送信するエラーメッセージを確定
        if not user_facing_error:
            user_facing_error = "処理中に予期せぬ問題が発生しました。お手数ですが、テレマスにて手入力してください。"
        
        # ユーザーへのエラー通知を試みる
        error_payload = {"content": {"type": "text", "text": user_facing_error}}
        err_send = lineworks_api.send_lw_message(recipient_id, error_payload)
        if err_send:
            # エラー通知の送信自体に失敗した場合は、重大なエラーとしてログに記録
            logging.critical(f"重大なエラー: ユーザーへのエラー通知の送信にも失敗しました: {err_send}")

        logging.error(f"タスク処理中にエラーが発生しました: {e}", exc_info=True)
        # main.pyに例外を再発生させて、タスクが失敗したことを伝える
        # main.py側で完全なスタックトレースが記録される
        raise e