variable "project_id" {
  description = "GCPプロジェクトID"
  type        = string
}

variable "region" {
  description = "GCPリージョン"
  type        = string
  default     = "asia-northeast1"
}

variable "env" {
  description = "環境名 "
  type        = string
  default     = "dev"
}

# --- Cloud Tasks 設定 ---

variable "cloud_tasks_queue_id" {
  description = "Cloud TasksのキューID"
  type        = string
  default     = "bot-server-queue"
}

# --- Cloud Storage (GCS) 設定 ---

variable "gcs_bucket_name" {
  description = "成果物を保存するGCSバケット名"
  type        = string
}

# --- Document AI 設定 ---

variable "doc_ai_location" {
  description = "Document AIのロケーション"
  type        = string
  default     = "us"
}

variable "doc_ai_processor_id" {
  description = "Document AI プロセッサID"
  type        = string
}

variable "doc_ai_processor_version_id" {
  description = "Document AI プロセッサバージョンID"
  type        = string
}

# --- AWS S3 設定 (Secret Managerで管理するが、バケット名やリージョンは変数でも可) ---

variable "aws_s3_bucket_name" {
  description = "AWS S3 バケット名"
  type        = string
}

variable "aws_s3_region" {
  description = "AWS S3 リージョン"
  type        = string
  default     = "ap-northeast-1"
}

# --- Secret Manager 参照用 ID (Secret Manager上のシークレット名) ---
# Terraformはこれらの名前を使ってSecret Managerから値を参照し、Cloud Runに注入します

variable "secret_id_lineworks_bot_secret" {
  description = "Secret Manager: LINE WORKS Bot SecretのID名"
  type        = string
  default     = "LINEWORKS_BOT_SECRET"
}

variable "secret_id_lineworks_bot_id" {
  description = "Secret Manager: LINE WORKS Bot IDのID名"
  type        = string
  default     = "LINEWORKS_BOT_ID"
}

variable "secret_id_sa_client_id" {
  description = "Secret Manager: Service Account Client IDのID名"
  type        = string
  default     = "SA_CLIENT_ID"
}

variable "secret_id_sa_client_secret" {
  description = "Secret Manager: Service Account Client SecretのID名"
  type        = string
  default     = "SA_CLIENT_SECRET"
}

variable "secret_id_sa_service_account" {
  description = "Secret Manager: Service Account EmailのID名"
  type        = string
  default     = "SA_SERVICE_ACCOUNT"
}

variable "secret_id_sa_private_key" {
  description = "Secret Manager: Service Account Private Key (ファイル内容) のID名"
  type        = string
  default     = "SA_PRIVATE_KEY"
}

variable "secret_id_aws_access_key_id" {
  description = "Secret Manager: AWS Access Key IDのID名"
  type        = string
  default     = "AWS_ACCESS_KEY_ID"
}

variable "secret_id_aws_secret_access_key" {
  description = "Secret Manager: AWS Secret Access KeyのID名"
  type        = string
  default     = "AWS_SECRET_ACCESS_KEY"
}
