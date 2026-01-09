# AWS EKS Cluster in a VPC
resource "aws_eks_cluster" "prod_cluster" {
  name     = "prod-eks"
  role_arn = "arn:aws:iam::123:role/eks-role"

  vpc_config {
    subnet_ids = ["subnet-123", "subnet-456"]
  }
}

# RDS Aurora Cluster
resource "aws_rds_cluster" "postgresql" {
  cluster_identifier      = "aurora-cluster-demo"
  engine                  = "aurora-postgresql"
  database_name           = "mydb"
  master_username         = "admin"
  master_password         = "password"
}

# S3 Bucket for Log Management
resource "aws_s3_bucket" "logs" {
  bucket = "enterprise-logs-2025"
}

# CloudWatch for Management
resource "aws_cloudwatch_log_group" "eks_logs" {
  name = "/aws/eks/prod/logs"
}

# Load Balancer
resource "aws_lb" "external_lb" {
  name               = "prod-alb"
  internal           = false
  load_balancer_type = "application"
}