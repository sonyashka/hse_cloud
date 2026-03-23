output "nat_instance_ip" {
  description = "Public IP address of NAT instance"
  value       = yandex_vpc_address.nat_public_ip.external_ipv4_address[0].address
}

output "nginx_lb_ip" {
  description = "Public IP address of Nginx load balancer"
  value       = yandex_vpc_address.nginx_public_ip.external_ipv4_address[0].address
}

output "clickhouse_internal_ip" {
  description = "Internal IP address of ClickHouse"
  value       = yandex_compute_instance.clickhouse.network_interface[0].ip_address
}

output "logbroker1_internal_ip" {
  description = "Internal IP address of Logbroker 1"
  value       = yandex_compute_instance.logbroker1.network_interface[0].ip_address
}

output "logbroker2_internal_ip" {
  description = "Internal IP address of Logbroker 2"
  value       = yandex_compute_instance.logbroker2.network_interface[0].ip_address
}

output "ssh_access_command" {
  description = "Command to access internal VMs via NAT"
  value       = "ssh -J ${var.vm_user}@${yandex_vpc_address.nat_public_ip.external_ipv4_address[0].address} ${var.vm_user}@<internal_ip>"
}

output "logbroker_health_check" {
  description = "URL to check logbroker health via Nginx"
  value       = "http://${yandex_vpc_address.nginx_public_ip.external_ipv4_address[0].address}/health"
}