import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import logging

# 独自のモジュールをインポート
import config

def upload_to_s3(file_content_bytes: bytes, s3_filename: str, content_type: str = 'text/csv'):
    """
    指定された内容を指定されたファイル名でAWS S3にアップロードする。

    Args:
        file_content_bytes (bytes): アップロードするファイルの中身。
        s3_filename (str): S3上でのファイル名（フォルダパスを含むことができる）。
        content_type (str, optional): ファイルのコンテントタイプ。デフォルトは 'text/csv'。

    Returns:
        tuple: (成功したS3のパス, エラーメッセージ)
               成功した場合は (s3_path, None)
               失敗した場合は (None, error_message)
    """
    try:
        # S3クライアントを初期化
        # configから認証情報とリージョンを読み込む
        s3_client = boto3.client(
            's3',
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_S3_REGION
        )
        logging.info(f"S3へのアップロードを開始: s3://{config.AWS_S3_BUCKET_NAME}/{s3_filename}")

        # メモリから直接データをアップロード
        s3_client.put_object(
            Bucket=config.AWS_S3_BUCKET_NAME,
            Key=s3_filename,
            Body=file_content_bytes,
            ContentType=content_type
        )

        s3_path = f"s3://{config.AWS_S3_BUCKET_NAME}/{s3_filename}"
        logging.info(f"S3へのアップロードが成功しました: {s3_path}")
        
        return s3_path, None

    except NoCredentialsError:
        error_message = "S3の認証情報（Access Key IDまたはSecret Access Key）が見つかりません。設定を確認してください。"
        logging.error(f"エラー: {error_message}")
        return None, error_message
    except ClientError as e:
        # AWSからの具体的なエラーレスポンスをログに出力
        error_code = e.response.get("Error", {}).get("Code")
        error_message_from_aws = e.response.get("Error", {}).get("Message")
        error_message = f"S3へのアップロード中にAWSクライアントエラーが発生しました (Code: {error_code}): {error_message_from_aws}"
        logging.error(f"エラー: {error_message}")
        return None, error_message
    except Exception as e:
        error_message = f"S3へのアップロード中に予期せぬエラーが発生しました: {e}"
        logging.error(f"エラー: {error_message}")
        return None, error_message