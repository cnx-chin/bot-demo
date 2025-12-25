from google.api_core.client_options import ClientOptions
from google.cloud import documentai
import logging

# 独自のモジュールをインポート
import config

def process_document(file_content_bytes: bytes, file_mime_type: str):
    """
    指定されたファイルの内容をGoogle Cloud Document AIで処理する。
    
    Args:
        file_content_bytes: 処理するファイルのバイトデータ。
        file_mime_type: ファイルのMIMEタイプ (例: 'application/pdf', 'image/jpeg')。

    Returns:
        成功した場合は、Documentオブジェクトを返す。
        失敗した場合は、(None, エラーメッセージ) を返す。
    """
    logging.info("--- Document AI プロセッサモジュール ---")

    opts = ClientOptions(
        api_endpoint=f"{config.DOC_AI_LOCATION}-documentai.googleapis.com"
    )
    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    # プロセッサのバージョンも指定する場合のロジック
    if config.DOC_AI_PROCESSOR_VERSION_ID:
        logging.info(f"指定されたプロセッサバージョンを使用: {config.DOC_AI_PROCESSOR_VERSION_ID}")
        name = client.processor_version_path(
            config.GCP_PROJECT_ID,
            config.DOC_AI_LOCATION,
            config.DOC_AI_PROCESSOR_ID,
            config.DOC_AI_PROCESSOR_VERSION_ID
        )
    else:
        logging.info("デフォルトのプロセッサバージョンを使用します。")
        name = client.processor_path(
            config.GCP_PROJECT_ID, config.DOC_AI_LOCATION, config.DOC_AI_PROCESSOR_ID
        )

    raw_document = documentai.RawDocument(
        content=file_content_bytes, mime_type=file_mime_type
    )

    request = documentai.ProcessRequest(
        name=name,
        raw_document=raw_document
    )

    try:
        logging.info(f"Document AIへの処理リクエストを送信: processor='{name}'")
        result = client.process_document(request=request)
        document = result.document
        
        logging.info("Document AIによる処理が成功しました。")
        return document, None

    except Exception as e:
        error_message = f"Document AIでの処理中にエラーが発生しました: {e}"
        logging.error(f"エラー: {error_message}")
        return None, error_message