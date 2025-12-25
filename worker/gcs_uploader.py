from google.cloud import storage
from google.cloud.exceptions import NotFound
import logging
import datetime
import os

# 独自のモジュールをインポート
import config

def _get_current_jst_now() -> datetime.datetime:
    """現在の日時(JST)を取得して返す"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(jst)

def _upload_with_logging(file_bytes: bytes, gcs_path: str, content_type: str, description: str):
    """
    アップロード処理とログ出力を共通化したヘルパー関数
    """
    logging.info(f"GCS{description}への保存を開始: {gcs_path}")
    _, err = upload_to_gcs(file_bytes, gcs_path, content_type=content_type)
    if err:
        logging.warning(f"GCS{description}への保存に失敗: {err}")

def _extract_date_parts_from_filename(filename: str) -> tuple[str, str, str, str]:
    """
    ファイル名から日付を抽出し、フォーマット済み文字列と年月日を返す。
    失敗した場合は現在の日付をフォールバックとして使用する。
    """
    try:
        timestamp_part = filename.split('_')[0]
        if len(timestamp_part) >= 8:
            year = timestamp_part[0:4]
            month = timestamp_part[4:6]
            day = timestamp_part[6:8]
            date_str = f"{year}年{month}月{day}日"
            return date_str, year, month, day
    except Exception:
        logging.warning(f"ファイル名 '{filename}' からの日付抽出に失敗。現在時刻でフォールバックします。")

    # フォールバック: 現在時刻を使用
    now = _get_current_jst_now()
    year, month, day = now.strftime('%Y'), now.strftime('%m'), now.strftime('%d')
    date_str = f"{year}年{month}月{day}日"
    return date_str, year, month, day

def upload_processed_results(is_review_needed: bool, store_code: str, csv_filename: str, image_bytes: bytes, csv_bytes: bytes, processed_image_bytes: bytes = None):
    """
    画像とCSVファイルをGCSにアップロードする。
    全てのファイルをアーカイブに保存し、レビューが必要な場合は追加でレビュー用フォルダにも保存する。
    処理済み画像(processed_image_bytes)がある場合は、レビュー用フォルダにのみ保存する。
    """
    try:
        # ファイル名から日付関連の情報を取得
        _, year_folder, month_folder, day_folder = _extract_date_parts_from_filename(csv_filename)
        
        base_name, _ = os.path.splitext(csv_filename)
        image_filename_for_gcs = f"{base_name}.jpg"

        # 1. 全てのファイルをproduction-archiveに保存
        archive_base_path = f"production-archive/{year_folder}/{month_folder}/{day_folder}/{store_code}"
        archive_image_path = f"{archive_base_path}/{image_filename_for_gcs}"
        archive_csv_path = f"{archive_base_path}/{csv_filename}"

        _upload_with_logging(image_bytes, archive_image_path, 'image/jpeg', 'アーカイブ(画像)')
        _upload_with_logging(csv_bytes, archive_csv_path, 'text/csv', 'アーカイブ(CSV)')

        # 2. レビューが必要な場合は、追加でreview-neededフォルダにも保存
        if is_review_needed:
            logging.info("レビューが必要なため、レビュー用フォルダにも追加保存します。")
            review_base_path = f"review-needed/{year_folder}/{month_folder}/{day_folder}/{store_code}"
            review_image_path = f"{review_base_path}/{image_filename_for_gcs}"
            review_csv_path = f"{review_base_path}/{csv_filename}"

            _upload_with_logging(image_bytes, review_image_path, 'image/jpeg', 'レビュー用(画像)')
            _upload_with_logging(csv_bytes, review_csv_path, 'text/csv', 'レビュー用(CSV)')
            
            # 3. 処理済み画像がある場合、レビュー用フォルダに追加保存
            if processed_image_bytes:
                processed_image_filename = f"{base_name}_processed.jpg"
                review_processed_image_path = f"{review_base_path}/{processed_image_filename}"
                _upload_with_logging(processed_image_bytes, review_processed_image_path, 'image/jpeg', 'レビュー用(処理済み画像)')

    except Exception:
        logging.warning("GCSへのアップロード中に予期せぬエラーが発生しました。", exc_info=True)

def upload_error_image(store_code: str, image_bytes: bytes, processed_image_bytes: bytes = None):
    """
    タイトルが読み取れなかった画像などを、後で確認できるようにGCSのレビュー用フォルダに保存する。
    ファイル名は YYYYMMDDHHMMSSSSS_{store_code}.jpg とする。
    """
    try:
        now = _get_current_jst_now()
        year, month, day = now.strftime('%Y'), now.strftime('%m'), now.strftime('%d')

        # ファイル名とパスを生成 (時刻情報を追加してユニークにする)
        timestamp_for_filename = now.strftime('%Y%m%d%H%M%S%f')[:-3]
        image_filename = f"{timestamp_for_filename}_{store_code}.jpg"
        review_base_path = f"review-needed/{year}/{month}/{day}/{store_code}"
        review_image_path = f"{review_base_path}/{image_filename}"

        logging.info(f"タイトル不明のため、画像をレビュー用フォルダに保存します: {review_image_path}")
        _upload_with_logging(image_bytes, review_image_path, 'image/jpeg', 'レビュー用(エラー画像)')

        # 処理済み画像がある場合、レビュー用フォルダに追加保存
        if processed_image_bytes:
            processed_image_filename = f"{timestamp_for_filename}_{store_code}_processed.jpg"
            review_processed_image_path = f"{review_base_path}/{processed_image_filename}"
            _upload_with_logging(processed_image_bytes, review_processed_image_path, 'image/jpeg', 'レビュー用(処理済みエラー画像)')

    except Exception:
        logging.warning("タイトル不明画像の保存中に予期せぬエラーが発生しました。", exc_info=True)

def upload_to_gcs(file_content_bytes: bytes, gcs_filename: str, content_type: str = 'text/csv'):
    """
    指定された内容を指定されたファイル名でGoogle Cloud Storageにアップロードする。

    Args:
        file_content_bytes (bytes): アップロードするファイルの中身。
        gcs_filename (str): GCS上でのファイル名。
        content_type (str, optional): ファイルのコンテントタイプ。デフォルトは 'text/csv'。

    Returns:
        tuple: (成功したGCSのパス, エラーメッセージ)
               成功した場合は (gcs_path, None)
               失敗した場合は (None, error_message)
    """
    try:
        # GCSクライアントを初期化
        # Cloud Run環境では、サービスアカウントの権限が自動的に使用される
        storage_client = storage.Client()

        # 指定されたバケットを取得
        bucket = storage_client.bucket(config.GCS_BUCKET_NAME)
        
        # バケットが存在しない場合のハンドリング（
        if not bucket.exists():
            error_message = f"GCSバケット '{config.GCS_BUCKET_NAME}' が見つかりません。"
            logging.warning(f"エラー: {error_message}")
            return None, error_message

        # アップロード先のBlob（ファイル）オブジェクトを作成
        blob = bucket.blob(gcs_filename)

        logging.info(f"GCSへのアップロードを開始: gs://{config.GCS_BUCKET_NAME}/{gcs_filename}")

        # メモリから直接データをアップロード
        blob.upload_from_string(
            data=file_content_bytes,
            content_type=content_type
        )

        gcs_path = f"gs://{config.GCS_BUCKET_NAME}/{gcs_filename}"
        logging.info(f"GCSへのアップロードが成功しました: {gcs_path}")
        
        return gcs_path, None

    except Exception as e:
        error_message = f"GCSへのアップロード中に予期せぬエラーが発生しました: {e}"
        logging.critical(f"エラー: {error_message}")
        return None, error_message