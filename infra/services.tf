# infra/services.tf

# ==============================================================================
# Service Accounts (SA)
# ==============================================================================

resource "google_service_account" "acceptor" {
  account_id   = "bot-acceptor-sa-v2"
  display_name = "Bot Acceptor Service Account"
}

resource "google_service_account" "worker" {
  account_id   = "bot-worker-sa-v2"
  display_name = "Bot Worker Service Account"
}

# ==============================================================================
# IAM Role Bindings
# ==============================================================================

locals {
  # Development: Copying all roles from legacy 'ocr-bot-runner' SA to ensure compatibility.
  # Excluded 'roles/resourcemanager.projectIamAdmin' for safety.
  dev_sa_roles = toset([
    "roles/cloudtasks.admin",
    "roles/cloudtasks.enqueuer",
    "roles/cloudtasks.viewer",
    "roles/documentai.apiUser",
    "roles/documentai.viewer",
    "roles/iam.serviceAccountTokenCreator",
    "roles/iam.serviceAccountUser",
    "roles/logging.logWriter",
    "roles/run.admin",
    "roles/secretmanager.secretAccessor",
    "roles/secretmanager.viewer",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/storage.bucketViewer",
    "roles/storage.objectAdmin"
  ])
}

# --- Apply All Roles to Acceptor SA ---
resource "google_project_iam_member" "acceptor_roles" {
  for_each = local.dev_sa_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.acceptor.email}"
}

# --- Apply All Roles to Worker SA ---
resource "google_project_iam_member" "worker_roles" {
  for_each = local.dev_sa_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.worker.email}"
}

# Resource-specific bindings (Good to keep for specificity)
resource "google_cloud_tasks_queue_iam_binding" "acceptor_enqueuer" {
  project  = google_cloud_tasks_queue.default.project
  location = google_cloud_tasks_queue.default.location
  name     = google_cloud_tasks_queue.default.name
  role     = "roles/cloudtasks.enqueuer"
  members  = ["serviceAccount:${google_service_account.acceptor.email}"]
}

resource "google_cloud_run_service_iam_binding" "worker_invoker" {
  location = google_cloud_run_v2_service.worker.location
  project  = google_cloud_run_v2_service.worker.project
  service  = google_cloud_run_v2_service.worker.name
  role     = "roles/run.invoker"
  members  = ["serviceAccount:${google_service_account.acceptor.email}"]
}

resource "google_storage_bucket_iam_binding" "worker_storage_admin" {
  bucket  = google_storage_bucket.assets.name
  role    = "roles/storage.objectAdmin"
  members = ["serviceAccount:${google_service_account.worker.email}"]
}

# ==============================================================================
# Cloud Run Services
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Acceptor Service
# ------------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "acceptor" {
  name     = "bot-acceptor-v2"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.acceptor.email
    
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello" 

      # --- 通常の環境変数 ---
      env {
        name  = "ENV"
        value = var.env
      }
      # コード期待: GCP_PROJECT_ID
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      # コード期待: CLOUD_TASKS_QUEUE_ID
      env {
        name  = "CLOUD_TASKS_QUEUE_ID"
        value = google_cloud_tasks_queue.default.name
      }
      # コード期待: GCP_LOCATION
      env {
        name  = "GCP_LOCATION"
        value = var.region
      }
      # コード期待: WORKER_URL
      env {
        name  = "WORKER_URL"
        value = "${google_cloud_run_v2_service.worker.uri}/worker"
      }
      # コード期待: GCP_SERVICE_ACCOUNT_EMAIL (OIDCトークン生成用)
      env {
        name  = "GCP_SERVICE_ACCOUNT_EMAIL"
        value = google_service_account.acceptor.email
      }
      
      # --- Secret Manager からの環境変数注入 ---
      env {
        name = "LINEWORKS_BOT_SECRET"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret_version.lineworks_bot_secret.secret
            version = "latest"
          }
        }
      }
      env {
        name = "LINEWORKS_BOT_ID"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret_version.lineworks_bot_id.secret
            version = "latest"
          }
        }
      }
    }
  }
  
  depends_on = [
    google_project_service.run,
    google_project_iam_member.acceptor_roles
  ]

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
  }
}

resource "google_cloud_run_service_iam_member" "acceptor_public" {
  location = google_cloud_run_v2_service.acceptor.location
  project  = google_cloud_run_v2_service.acceptor.project
  service  = google_cloud_run_v2_service.acceptor.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ------------------------------------------------------------------------------
# 2. Worker Service
# ------------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "worker" {
  name     = "bot-worker-v2"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY" 
  deletion_protection = false

  template {
    service_account = google_service_account.worker.email
    timeout = "300s"

    # --- Volume Mount 定義 (Secretをファイルとしてマウント) ---
    volumes {
      name = "sa-key-volume"
      secret {
        secret = data.google_secret_manager_secret_version.sa_private_key.secret
        items {
          version = "latest"
          path    = "key.json" # マウント後のファイル名
        }
      }
    }

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello" 

      resources {
        limits = {
          cpu    = "1000m"
          memory = "1Gi"
        }
      }

      # --- Volume Mount 設定 ---
      volume_mounts {
        name       = "sa-key-volume"
        mount_path = "/secrets/sa_key"
      }

      # --- 通常の環境変数 ---
      env {
        name  = "ENV"
        value = var.env
      }
      # コード期待: GCP_PROJECT_ID
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      # コード期待: GCS_BUCKET_NAME
      env {
        name  = "GCS_BUCKET_NAME"
        value = google_storage_bucket.assets.name
      }
      # コード期待: DOC_AI_PROCESSOR_ID
      env {
        name  = "DOC_AI_PROCESSOR_ID"
        value = var.doc_ai_processor_id
      }
      # コード期待: DOC_AI_LOCATION
      env {
        name  = "DOC_AI_LOCATION"
        value = var.doc_ai_location
      }
      # コード期待: DOC_AI_PROCESSOR_VERSION_ID
      env {
        name  = "DOC_AI_PROCESSOR_VERSION_ID"
        value = var.doc_ai_processor_version_id
      }
      # コード期待: AWS_S3_BUCKET_NAME
      env {
        name  = "AWS_S3_BUCKET_NAME"
        value = var.aws_s3_bucket_name
      }
      # コード期待: AWS_S3_REGION
      env {
        name  = "AWS_S3_REGION"
        value = var.aws_s3_region
      }
      # コード期待: SA_PRIVATE_KEY_PATH (マウントしたファイルを指す)
      env {
        name  = "SA_PRIVATE_KEY_PATH"
        value = "/secrets/sa_key/key.json"
      }
      
      # --- Secret Manager からの環境変数注入 ---
      env {
        name = "LINEWORKS_BOT_ID"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret_version.lineworks_bot_id.secret
            version = "latest"
          }
        }
      }
      env {
        name = "SA_CLIENT_ID"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret_version.sa_client_id.secret
            version = "latest"
          }
        }
      }
      env {
        name = "SA_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret_version.sa_client_secret.secret
            version = "latest"
          }
        }
      }
      env {
        name = "SA_SERVICE_ACCOUNT"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret_version.sa_service_account.secret
            version = "latest"
          }
        }
      }
      env {
        name = "AWS_ACCESS_KEY_ID"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret_version.aws_access_key.secret
            version = "latest"
          }
        }
      }
      env {
        name = "AWS_SECRET_ACCESS_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret_version.aws_secret_key.secret
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.run,
    google_project_iam_member.worker_roles
  ]

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
  }
}
