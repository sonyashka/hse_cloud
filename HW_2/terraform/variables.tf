# Yandex Cloud credentials
variable "yc_token" {
  type        = string
  description = "Yandex Cloud OAuth token"
  sensitive   = true
}

variable "yc_cloud_id" {
  type        = string
  description = "Yandex Cloud ID"
}

variable "yc_folder_id" {
  type        = string
  description = "Yandex Cloud folder ID"
}

variable "yc_zone" {
  type        = string
  description = "Yandex Cloud zone"
  default     = "ru-central1-a"
}

# Network configuration
variable "network_cidr" {
  type        = string
  description = "CIDR for hw2-network"
  default     = "10.0.1.0/24"
}

# VM configuration
variable "vm_user" {
  type        = string
  description = "SSH user for VMs"
  default     = "ubuntu"
}

variable "ssh_public_key_path" {
  type        = string
  description = "Path to SSH public key"
  default     = "C:\\Users\\sonyashka\\sdp.pub"
}

# VM images
variable "ubuntu_image_id" {
  type        = string
  description = "Ubuntu 22.04 LTS image ID"
  default     = "fd817i7o8012578061ra" # Ubuntu 22.04 LTS
}

variable "nat_instance_image_id" {
  type        = string
  description = "NAT instance image ID"
  default     = "fd8vmcue7aajpmeo39kk" # Ubuntu-based NAT instance
}

# VM resources
variable "vm_platform_id" {
  type        = string
  description = "VM platform ID"
  default     = "standard-v3"
}

variable "logbroker_cpu" {
  type        = number
  description = "Logbroker VM CPU cores"
  default     = 2
}

variable "logbroker_ram" {
  type        = number
  description = "Logbroker VM RAM in GB"
  default     = 2
}

variable "clickhouse_cpu" {
  type        = number
  description = "ClickHouse VM CPU cores"
  default     = 2
}

variable "clickhouse_ram" {
  type        = number
  description = "ClickHouse VM RAM in GB"
  default     = 4
}

variable "nginx_cpu" {
  type        = number
  description = "Nginx VM CPU cores"
  default     = 2
}

variable "nginx_ram" {
  type        = number
  description = "Nginx VM RAM in GB"
  default     = 2
}