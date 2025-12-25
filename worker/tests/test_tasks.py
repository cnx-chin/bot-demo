import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# worker ディレクトリをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================================
# 【重要】configのインポート前にsecret_managerをモックする
# config.pyはトップレベルでget_secretを呼び出すため、インポート前にインターセプトが必要
# ============================================================================
mock_secret_manager_module = MagicMock()
# get_secretがダミー値を返すように設定し、config.pyの初期化エラーを防ぐ
mock_secret_manager_module.get_secret.return_value = "dummy_secret_value"
sys.modules['secret_manager'] = mock_secret_manager_module

# cv2とnumpyをモックする（ローカル環境依存を排除）
sys.modules['cv2'] = MagicMock()
sys.modules['numpy'] = MagicMock()

# これで安全にtasksをインポートできる
from tasks import process_image_and_reply

class TestTasks(unittest.TestCase):

    @patch('lineworks_api.get_store_code_by_user')
    @patch('lineworks_api.download_lw_attachment')
    @patch('image_processor.process_image')
    @patch('document_ai_processor.process_document')
    @patch('doc_ai_parser.parse_document_entities')
    @patch('csv_generator.generate_csv_content')
    @patch('csv_generator.generate_csv_filename')
    @patch('gcs_uploader.upload_processed_results')
    @patch('gcs_uploader.upload_error_image')
    @patch('s3_uploader.upload_to_s3')
    @patch('lineworks_api.send_lw_message')
    @patch('config.KEYWORDS', ["クレジット支払", "クレジット受入", "現金支払", "現金受入"])
    def test_process_image_and_reply_success(self, 
                                            mock_send_lw_message, 
                                            mock_upload_to_s3, 
                                            mock_upload_error_image,
                                            mock_upload_processed_results, 
                                            mock_generate_csv_filename,
                                            mock_generate_csv_content, 
                                            mock_parse_document_entities, 
                                            mock_process_document, 
                                            mock_process_image,
                                            mock_download_lw_attachment, 
                                            mock_get_store_code_by_user):
        """
        process_image_and_reply 関数が成功パスを正常に処理することを確認するテスト
        """
        
        # --- 1. Mockの戻り値を設定 ---
        mock_get_store_code_by_user.return_value = ("STORE001", None)
        mock_download_lw_attachment.return_value = (b"fake_image_bytes", None)
        mock_process_image.return_value = b"processed_fake_image_bytes"

        mock_document = MagicMock()
        mock_process_document.return_value = (mock_document, None)

        mock_parse_document_entities.return_value = ({
            'title': '現金支払', 
            'date': '2025-12-17', 
            'amount': 1000
        }, False, None)
        
        mock_generate_csv_content.return_value = ("csv_content_string", None)
        mock_generate_csv_filename.return_value = "STORE001_現金支払_20251217.csv"
        mock_upload_to_s3.return_value = (None, None)
        mock_send_lw_message.return_value = None
        mock_upload_processed_results.return_value = None

        # --- 2. テスト実行 ---
        process_image_and_reply("file_id_123", "user_id_456", None, "trace_id_789")

        # --- 3. アサーション（検証） ---
        mock_get_store_code_by_user.assert_called_once_with("user_id_456")
        mock_download_lw_attachment.assert_called_once_with("file_id_123")
        mock_process_image.assert_called_once_with(b"fake_image_bytes")
        mock_process_document.assert_called_once_with(b"processed_fake_image_bytes", 'image/jpeg')
        
        mock_upload_to_s3.assert_called_once_with("csv_content_string".encode('utf-8'), "STORE001_現金支払_20251217.csv")
        
        # 成功メッセージの検証
        mock_send_lw_message.assert_called_once()
        args, _ = mock_send_lw_message.call_args
        self.assertEqual(args[0], "user_id_456")
        
        # 文字化け回避のため、完全一致でメッセージ内容を検証する
        expected_msg = "「現金支払」の処理とアップロードが正常に完了しました。"
        self.assertEqual(args[1]["content"]["text"], expected_msg)
        
        # エラー処理が呼ばれていないことを確認
        mock_upload_error_image.assert_not_called()

if __name__ == '__main__':
    unittest.main()
