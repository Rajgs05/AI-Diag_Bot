resource "google_compute_instance" "vm_instance" {
  name         = "web-server"
  machine_type = "f1-micro"
  zone         = "us-central1-a"
}

resource "google_sql_database_instance" "master" {
  name             = "master-instance"
  database_version = "POSTGRES_11"
  region           = "us-central1"
}

resource "google_storage_bucket" "static" {
  name     = "image-store"
  location = "US"
}