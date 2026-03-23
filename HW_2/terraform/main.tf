# Создаем сеть и подсеть
resource "yandex_vpc_network" "hw2_network" {
  name = "hw2-network"
}

resource "yandex_vpc_subnet" "hw2_subnet" {
  name           = "hw2-subnet"
  zone           = var.yc_zone
  network_id     = yandex_vpc_network.hw2_network.id
  v4_cidr_blocks = [var.network_cidr]
}

# Создаем статические публичные IP для NAT и Nginx
resource "yandex_vpc_address" "nat_public_ip" {
  name = "nat-public-ip"
  external_ipv4_address {
    zone_id = var.yc_zone
  }
}

resource "yandex_vpc_address" "nginx_public_ip" {
  name = "nginx-public-ip"
  external_ipv4_address {
    zone_id = var.yc_zone
  }
}

# Security group for internal VMs
resource "yandex_vpc_security_group" "internal_sg" {
  name        = "internal-security-group"
  network_id  = yandex_vpc_network.hw2_network.id
  description = "Security group for internal VMs (logbroker, clickhouse)"

  ingress {
    protocol       = "TCP"
    description    = "SSH from NAT"
    port           = 22
    v4_cidr_blocks = ["10.0.1.0/24"]
  }

  ingress {
    protocol       = "TCP"
    description    = "ClickHouse from logbrokers"
    port           = 8123
    v4_cidr_blocks = ["10.0.1.0/24"]
  }

  ingress {
    protocol       = "TCP"
    description    = "Logbroker health checks"
    port           = 8080
    v4_cidr_blocks = ["10.0.1.0/24"]
  }

  egress {
    protocol       = "ANY"
    description    = "Allow all outgoing traffic"
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}

# Security group for NAT instance (allows SSH from internet)
resource "yandex_vpc_security_group" "nat_sg" {
  name        = "nat-security-group"
  network_id  = yandex_vpc_network.hw2_network.id
  description = "Security group for NAT instance"

  ingress {
    protocol       = "TCP"
    description    = "SSH from internet"
    port           = 22
    v4_cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    protocol       = "ANY"
    description    = "Allow all outgoing traffic"
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}

# Security group for Nginx (allows HTTP from internet)
resource "yandex_vpc_security_group" "nginx_sg" {
  name        = "nginx-security-group"
  network_id  = yandex_vpc_network.hw2_network.id
  description = "Security group for Nginx load balancer"

  ingress {
    protocol       = "TCP"
    description    = "HTTP from internet"
    port           = 80
    v4_cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    protocol       = "TCP"
    description    = "SSH from NAT"
    port           = 22
    v4_cidr_blocks = ["10.0.1.0/24"]
  }

  egress {
    protocol       = "ANY"
    description    = "Allow all outgoing traffic"
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}

# NAT instance
resource "yandex_compute_instance" "nat" {
  name        = "nat-instance"
  platform_id = var.vm_platform_id
  zone        = var.yc_zone

  resources {
    cores  = 2
    memory = 2
  }

  boot_disk {
    initialize_params {
      image_id = var.nat_instance_image_id
      size     = 20
    }
  }

  network_interface {
    subnet_id          = yandex_vpc_subnet.hw2_subnet.id
    nat                = true
    nat_ip_address     = yandex_vpc_address.nat_public_ip.external_ipv4_address[0].address
    ip_address         = cidrhost(var.network_cidr, 5) # 10.0.1.5
    security_group_ids = [yandex_vpc_security_group.nat_sg.id]
  }

  metadata = {
    ssh-keys  = "${var.vm_user}:${file(var.ssh_public_key_path)}"
    user-data = <<-EOF
      #cloud-config
      write_files:
        - path: /etc/sysctl.d/10-ip-forwarding.conf
          content: "net.ipv4.ip_forward=1"
      runcmd:
        - sysctl -p /etc/sysctl.d/10-ip-forwarding.conf
        - iptables -t nat -A POSTROUTING -s ${var.network_cidr} -o eth0 -j MASQUERADE
        - apt-get update
        - apt-get install -y iptables-persistent
      EOF
  }
}

# Nginx load balancer
resource "yandex_compute_instance" "nginx" {
  name        = "nginx-lb"
  platform_id = var.vm_platform_id
  zone        = var.yc_zone

  resources {
    cores  = var.nginx_cpu
    memory = var.nginx_ram
  }

  boot_disk {
    initialize_params {
      image_id = var.ubuntu_image_id
      size     = 20
    }
  }

  network_interface {
    subnet_id          = yandex_vpc_subnet.hw2_subnet.id
    nat                = true
    nat_ip_address     = yandex_vpc_address.nginx_public_ip.external_ipv4_address[0].address
    ip_address         = cidrhost(var.network_cidr, 10) # 10.0.1.10
    security_group_ids = [yandex_vpc_security_group.nginx_sg.id]
  }

  metadata = {
    ssh-keys  = "${var.vm_user}:${file(var.ssh_public_key_path)}"
    user-data = <<-EOF
      #cloud-config
      package_update: true
      packages:
        - nginx
      write_files:
        - path: /etc/nginx/nginx.conf
          content: |
            user www-data;
            worker_processes auto;
            pid /run/nginx.pid;
            include /etc/nginx/modules-enabled/*.conf;

            events {
                worker_connections 1024;
            }

            http {
                upstream logbroker_backend {
                    server 10.0.1.20:8080;
                    server 10.0.1.21:8080;
                }

                server {
                    listen 80;
                    server_name _;

                    location / {
                        proxy_pass http://logbroker_backend;
                        proxy_set_header Host $host;
                        proxy_set_header X-Real-IP $remote_addr;
                        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                        proxy_set_header X-Forwarded-Proto $scheme;
                        proxy_connect_timeout 5s;
                        proxy_read_timeout 30s;
                    }
                }
            }
      runcmd:
        - systemctl enable nginx
        - systemctl start nginx
        - ufw allow 80/tcp
        - ufw allow 22/tcp
        - ufw --force enable
      EOF
  }
}

# ClickHouse database
resource "yandex_compute_instance" "clickhouse" {
  name        = "clickhouse-db"
  platform_id = var.vm_platform_id
  zone        = var.yc_zone

  resources {
    cores  = var.clickhouse_cpu
    memory = var.clickhouse_ram
  }

  boot_disk {
    initialize_params {
      image_id = var.ubuntu_image_id
      size     = 30
    }
  }

  network_interface {
    subnet_id          = yandex_vpc_subnet.hw2_subnet.id
    ip_address         = cidrhost(var.network_cidr, 30) # 10.0.1.30
    security_group_ids = [yandex_vpc_security_group.internal_sg.id]
  }

  metadata = {
    ssh-keys  = "${var.vm_user}:${file(var.ssh_public_key_path)}"
    user-data = <<-EOF
      #cloud-config
      package_update: true
      packages:
        - docker.io
        - docker-compose
      write_files:
        - path: /home/ubuntu/docker-compose.yml
          content: |
            version: '3.8'
            services:
              clickhouse:
                image: yandex/clickhouse-server:latest
                container_name: clickhouse-server
                ports:
                  - "8123:8123"
                  - "9000:9000"
                volumes:
                  - clickhouse_data:/var/lib/clickhouse
                ulimits:
                  nofile:
                    soft: 262144
                    hard: 262144
                restart: unless-stopped
            volumes:
              clickhouse_data:
        - path: /home/ubuntu/init-clickhouse.sql
          content: |
            CREATE DATABASE IF NOT EXISTS default;
            CREATE TABLE IF NOT EXISTS default.logs
            (
                timestamp DateTime,
                level String,
                message String,
                service String,
                extra String
            )
            ENGINE = MergeTree()
            ORDER BY (timestamp, service, level);
      runcmd:
        - docker-compose -f /home/ubuntu/docker-compose.yml up -d
        - sleep 10
        - docker exec clickhouse-server clickhouse-client --query "$(cat /home/ubuntu/init-clickhouse.sql)"
      EOF
  }
}

# Logbroker instances
resource "yandex_compute_instance" "logbroker1" {
  name        = "logbroker-1"
  platform_id = var.vm_platform_id
  zone        = var.yc_zone

  resources {
    cores  = var.logbroker_cpu
    memory = var.logbroker_ram
  }

  boot_disk {
    initialize_params {
      image_id = var.ubuntu_image_id
      size     = 20
    }
  }

  network_interface {
    subnet_id          = yandex_vpc_subnet.hw2_subnet.id
    ip_address         = cidrhost(var.network_cidr, 20) # 10.0.1.20
    security_group_ids = [yandex_vpc_security_group.internal_sg.id]
  }

  metadata = {
    ssh-keys  = "${var.vm_user}:${file(var.ssh_public_key_path)}"
    user-data = <<-EOF
      #cloud-config
      package_update: true
      packages:
        - docker.io
      write_files:
        - path: /home/ubuntu/.env
          content: |
            CLICKHOUSE_HOST=10.0.1.30
            CLICKHOUSE_PORT=8123
            CLICKHOUSE_DB=default
            CLICKHOUSE_TABLE=logs
            APP_HOST=0.0.0.0
            APP_PORT=8080
            LOG_LEVEL=INFO
            BUFFER_FLUSH_INTERVAL=1
            BUFFER_MAX_SIZE=1000
        - path: /home/ubuntu/run-logbroker.sh
          content: |
            #!/bin/bash
            docker pull cr.yandex/crpbe7nb53vn7u8scn27/logbroker:latest
            docker run -d \
              --name logbroker \
              --restart unless-stopped \
              -p 8080:8080 \
              --env-file /home/ubuntu/.env \
              -v /var/logbroker/buffer:/app/buffer \
              cr.yandex/crpbe7nb53vn7u8scn27/logbroker:latest
          permissions: '0755'
      runcmd:
        - mkdir -p /var/logbroker/buffer/pending /var/logbroker/buffer/sent
        - chmod 755 /home/ubuntu/run-logbroker.sh
        - /home/ubuntu/run-logbroker.sh
      EOF
  }
}

resource "yandex_compute_instance" "logbroker2" {
  name        = "logbroker-2"
  platform_id = var.vm_platform_id
  zone        = var.yc_zone

  resources {
    cores  = var.logbroker_cpu
    memory = var.logbroker_ram
  }

  boot_disk {
    initialize_params {
      image_id = var.ubuntu_image_id
      size     = 20
    }
  }

  network_interface {
    subnet_id          = yandex_vpc_subnet.hw2_subnet.id
    ip_address         = cidrhost(var.network_cidr, 21) # 10.0.1.21
    security_group_ids = [yandex_vpc_security_group.internal_sg.id]
  }

  metadata = {
    ssh-keys  = "${var.vm_user}:${file(var.ssh_public_key_path)}"
    user-data = <<EOF
      #cloud-config
      package_update: true
      packages:
        - docker.io
      write_files:
        - path: /home/ubuntu/.env
          content: |
            CLICKHOUSE_HOST=10.0.1.30
            CLICKHOUSE_PORT=8123
            CLICKHOUSE_DB=default
            CLICKHOUSE_TABLE=logs
            APP_HOST=0.0.0.0
            APP_PORT=8080
            LOG_LEVEL=INFO
            BUFFER_FLUSH_INTERVAL=1
            BUFFER_MAX_SIZE=1000
        - path: /home/ubuntu/run-logbroker.sh
          content: |
            #!/bin/bash
            docker pull cr.yandex/crpbe7nb53vn7u8scn27/logbroker:latest
            docker run -d \
              --name logbroker \
              --restart unless-stopped \
              -p 8080:8080 \
              --env-file /home/ubuntu/.env \
              -v /var/logbroker/buffer:/app/buffer \
              cr.yandex/crpbe7nb53vn7u8scn27/logbroker:latest
          permissions: '0755'
      runcmd:
        - mkdir -p /var/logbroker/buffer/pending /var/logbroker/buffer/sent
        - chmod 755 /home/ubuntu/run-logbroker.sh
        - /home/ubuntu/run-logbroker.sh
      EOF
  }

  depends_on = [
    yandex_compute_instance.clickhouse
  ]
}