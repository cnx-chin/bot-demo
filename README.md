# 🚀 LINE WORKS Document AI Bot Server

LINE WORKSのBot機能を活用し、チャット経由でアップロードされた帳票画像などを **Google Cloud Document AI** で解析し、結果をCSVとして保存・通知する自動化システムです。

## 🌟 システム概要

このシステムは、LINE WORKSからのイベント受信と実際のデータ処理を分離した **非同期アーキテクチャ** を採用しており、高いスケーラビリティと応答性を確保しています。

### 🏗️ アーキテクチャ構成

1.  **📡 Acceptor Service (`acceptor/`)**
    *   **役割**: イベント受信ゲートウェイ (Cloud Run)
    *   **機能**: 
        *   LINE WORKSからのWebhookイベントを受信・**署名検証** (`X-WORKS-Signature`)。
        *   イベントデータをGoogle Cloud Tasksトピック (`lineworks-events`) に即座にパブリッシュ。
        *   LINE WORKSサーバーへ200 OKを迅速に返し、タイムアウトを防ぎます。

2.  **⚙️ Worker Service (`worker/`)**
    *   **役割**: データ処理バックエンド (Cloud Run)
    *   **機能**: 
        *   Cloud Tasksからメッセージをサブスクライブ。
        *   LINE WORKS APIを利用して画像をダウンロードし、**高度な画像前処理**（90度/180度回転補正、影除去）を実行。
        *   **Google Cloud Document AI** を使用してドキュメントをOCR/構造化解析。
        *   解析結果に基づいてCSVファイルを生成。
        *   生成されたデータを **Google Cloud Storage (GCS)** および **AWS S3** へアップロード。
        *   処理完了通知や解析結果をLINE WORKSユーザーへ返信。

3.  **☁️ Infrastructure (`infra/`)**
    *   **役割**: インフラ管理 (IaC)
    *   **基盤**: Terraform (GCS Backend)

## 📂 ディレクトリ構造と役割

### 1. Acceptor (`acceptor/`)
Webhookリクエストを受け付け、検証し、キューに入れるための軽量サービス。

*   `main.py`: FastAPIエントリーポイント。
*   `lineworks_api.py`: **署名検証ロジック**。LINE WORKSからのリクエストが正当かチェックします。
*   `secret_manager.py` / `config.py`: 設定とSecret管理。

### 2. Worker (`worker/`)
実際のビジネスロジックを実行する非同期ワーカー。

*   `main.py`: Cloud Tasksメッセージリスナー。
*   `tasks.py`: **メイン処理フロー**（ダウンロード→加工→解析→CSV→アップロード→通知）。
*   `image_processor.py`: **画像処理エンジン**。OpenCVを使用し、回転補正や影除去を行います。
*   `lineworks_api.py`: **APIクライアント**。トークン管理、ファイルDL、メッセージ送信など。
*   `document_ai_processor.py` / `doc_ai_parser.py`: Document AIとの連携とデータ解析。
*   `gcs_uploader.py` / `s3_uploader.py`: マルチクラウドストレージへのアップロード。

### 3. Infrastructure (`infra/`)
TerraformによるGCPリソース定義。状態管理（State）は **GCS Backend** で行われ、チーム開発時の排他制御（Locking）が有効化されています。

## ✅ 前提条件

*   **Google Cloud Platform (GCP)** プロジェクト (Document AI, Cloud Run, Cloud Tasks, Secret Manager有効化)
*   **LINE WORKS Developer Console** (Bot作成, API 2.0設定)
*   **Terraform** (v1.0+) & **gcloud CLI**

## 🔑 環境変数 / Secret Manager

本番環境では **Google Secret Manager** で厳重に管理されます。

*   `LINEWORKS_BOT_ID`, `LINEWORKS_BOT_SECRET` ... (Bot認証)
*   `LINEWORKS_PRIVATE_KEY` ... (Service Account認証用秘密鍵)
*   `GOOGLE_CLOUD_PROJECT`, `CLOUD_TASKS_QUEUE_ID` ... (GCP設定)
*   `DOCUMENT_AI_PROCESSOR_ID` ... (DocAI設定)

## 💻 開発とデプロイ

### ローカル実行に関する注意 ⚠️
本システムは **Google Cloud Tasks** や **LINE WORKS Webhook (署名検証)**、**Document AI** などのクラウドサービスに高度に依存しています。
そのため、単純な `python main.py` だけでは完全な動作確認はできません。

*   **ロジック確認**: ユニットテスト (`worker/tests/`) を活用してください。
*   **結合テスト**: 開発用の Cloud Run 環境へデプロイして動作確認することを推奨します。

### インフラ構築 (Terraform) 🛠️

Terraformの状態ファイル（tfstate）は **Google Cloud Storage (GCS)** で管理されています。

```bash
cd infra

# 初期化 (GCS Backendの設定)
terraform init

# 実行計画の確認
terraform plan

# リソースの適用
terraform apply
```

### アプリケーションのデプロイ 🚀

通常は `gcloud run deploy` コマンド、または設定済みの CI/CD パイプライン経由でデプロイします。

```bash
# 例: Acceptorのデプロイ
gcloud run deploy acceptor-service --source ./acceptor ...

# 例: Workerのデプロイ
gcloud run deploy worker-service --source ./worker ...
```
