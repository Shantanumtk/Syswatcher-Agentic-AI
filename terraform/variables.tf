variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use (leave empty for default)"
  type        = string
  default     = ""
}

variable "project" {
  description = "Project name  used in all resource names and tags"
  type        = string
  default     = "syswatcher"
}

variable "environment" {
  description = "Environment tag applied to all resources"
  type        = string
  default     = "monitoring"
}

#  Instance types 
variable "jump_instance_type" {
  description = "EC2 instance type for jump/monitoring server"
  type        = string
  default     = "t3.medium"   # 2 vCPU, 4GB  runs Docker + all SysWatcher services
}

variable "dev_instance_type" {
  description = "EC2 instance type for dev server"
  type        = string
  default     = "t3.small"    # 2 vCPU, 2GB
}

variable "test_instance_type" {
  description = "EC2 instance type for test server"
  type        = string
  default     = "t3.small"
}

#  Storage 
variable "jump_disk_gb" {
  description = "Root volume size (GB) for jump server"
  type        = number
  default     = 30
}

variable "dev_disk_gb" {
  description = "Root volume size (GB) for dev server"
  type        = number
  default     = 20
}

variable "test_disk_gb" {
  description = "Root volume size (GB) for test server"
  type        = number
  default     = 20
}

#  Network 
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR for the public subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH into jump server. Default = open (restrict in production)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "allowed_ui_cidr" {
  description = "CIDR allowed to access SysWatcher UI/API ports"
  type        = string
  default     = "0.0.0.0/0"
}

#  Key pair 
variable "key_name_prefix" {
  description = "Prefix for generated SSH key pair names"
  type        = string
  default     = "syswatcher"
}

variable "keys_output_dir" {
  description = "Local directory where SSH private keys are saved"
  type        = string
  default     = "./keys"
}
