# infra/main.tf

# ---------------------------------------------------------
# Provider 設定
# ---------------------------------------------------------
provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------
# Data Sources (既存リソースの参照)
# ---------------------------------------------------------

# 現在のプロジェクト情報を取得（動的にProject Numberなどを参照するため）
data "google_project" "project" {}

# Secret Manager上のSecretバージョン(latest)を参照
# これにより、Terraformは「秘密の値」自体は知らずに、その「場所」だけをCloud Runに教えることができます

data "google_secret_manager_secret_version" "lineworks_bot_secret" {
  secret = var.secret_id_lineworks_bot_secret
}

data "google_secret_manager_secret_version" "lineworks_bot_id" {
  secret = var.secret_id_lineworks_bot_id
}

# --- Service Account Credentials (JSON Key) ---
# 注意: 本来はWorkload Identity Federationを使うべきですが、
# 既存実装に合わせてJSONキーファイルの中身をSecret Managerから取得する想定にします。
# もしJSONキーを使わず、Cloud RunのService Account自体に権限を与える設計に変更済みなら、これは不要です。
data "google_secret_manager_secret_version" "sa_private_key" {
  secret = var.secret_id_sa_private_key
}

data "google_secret_manager_secret_version" "sa_client_id" {
  secret = var.secret_id_sa_client_id
}

data "google_secret_manager_secret_version" "sa_client_secret" {
  secret = var.secret_id_sa_client_secret
}

data "google_secret_manager_secret_version" "sa_service_account" {
  secret = var.secret_id_sa_service_account
}

# --- AWS Credentials ---
data "google_secret_manager_secret_version" "aws_access_key" {
  secret = var.secret_id_aws_access_key_id
}

data "google_secret_manager_secret_version" "aws_secret_key" {
  secret = var.secret_id_aws_secret_access_key
}

# ---------------------------------------------------------
# Enable APIs (必要なAPIの有効化)
# ---------------------------------------------------------
# これを定義しておくと、新しい環境でも自動的にAPIがONになります

resource "google_project_service" "run" {
  service = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudtasks" {
  service = "cloudtasks.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  service = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam" {
  service = "iam.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "documentai" {
  service = "documentai.googleapis.com"
  disable_on_destroy = false
}
