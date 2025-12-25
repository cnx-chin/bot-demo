# infra/storage.tf

# ---------------------------------------------------------
# Cloud Storage Bucket (画像・CSV保存用)
# ---------------------------------------------------------

resource "google_storage_bucket" "assets" {
  name          = var.gcs_bucket_name
  location      = var.region
  storage_class = "STANDARD"

  # バージョニングを有効にするか（誤削除対策）
  versioning {
    enabled = true
  }

  # パブリックアクセスを強制的に禁止（セキュリティ）
  public_access_prevention = "enforced"

  # ライフサイクルルール: 30日経過した古いファイルは自動削除（コスト削減）
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

# ---------------------------------------------------------
# Cloud Tasks Queue (非同期処理用キュー)
# ---------------------------------------------------------

resource "google_cloud_tasks_queue" "default" {
  name     = var.cloud_tasks_queue_id
  location = var.region

  # レートリミット設定 (Document AIのQuota制限などを考慮)
  rate_limits {
    max_dispatches_per_second = 10 # 1秒間に最大10タスク
    max_concurrent_dispatches = 50 # 最大同時実行数
  }

  # リトライ設定 (タスク失敗時の再試行ルール)
  retry_config {
    max_attempts       = 5      # 最大5回までリトライ
    max_retry_duration = "300s" # 最大5分間リトライを続ける
    min_backoff        = "1s"   # 最初は1秒待つ
    max_backoff        = "60s"  # 最大60秒待つ
  }

  depends_on = [google_project_service.cloudtasks]
}
