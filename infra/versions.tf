 # infra/versions.tf

 terraform {
   # 根拠: https://developer.hashicorp.com/terraform/downloads#terraform-versions
   required_version = ">= 1.14.3"

   backend "gcs" {
     bucket = "run-sources-sunny-resolver-460603-m3-asia-northeast1"
     prefix = "terraform/state"
   }

   required_providers {
     google = {
       source  = "hashicorp/google"
       # 根拠: https://registry.terraform.io/providers/hashicorp/google/latest
       version = ">= 7.14.0"
     }
   }
 }