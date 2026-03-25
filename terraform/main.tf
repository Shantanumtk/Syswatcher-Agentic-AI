# 
# Provider
# 
provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# 
# Data sources
# 
data "aws_availability_zones" "available" {
  state = "available"
}

# Latest Ubuntu 22.04 LTS AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]   # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

# 
# SSH Key Pairs  one per server
# 
locals {
  servers = ["jump", "dev", "test"]
}

resource "tls_private_key" "syswatcher" {
  for_each  = toset(local.servers)
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "syswatcher" {
  for_each   = toset(local.servers)
  key_name   = "${var.project}-${each.key}-key"
  public_key = tls_private_key.syswatcher[each.key].public_key_openssh

  tags = {
    Name   = "${var.project}-${each.key}-key"
    Server = each.key
  }
}

# Save private keys locally
resource "local_file" "private_key" {
  for_each        = toset(local.servers)
  content         = tls_private_key.syswatcher[each.key].private_key_pem
  filename        = "${var.keys_output_dir}/${var.project}-${each.key}.pem"
  file_permission = "0600"
}

# 
# VPC
# 
resource "aws_vpc" "syswatcher" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${var.project}-vpc" }
}

resource "aws_internet_gateway" "syswatcher" {
  vpc_id = aws_vpc.syswatcher.id
  tags   = { Name = "${var.project}-igw" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.syswatcher.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = { Name = "${var.project}-public-subnet" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.syswatcher.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.syswatcher.id
  }

  tags = { Name = "${var.project}-public-rt" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# 
# Security Groups
# 

# Jump server  SysWatcher runs here
resource "aws_security_group" "jump" {
  name        = "${var.project}-jump-sg"
  description = "SysWatcher jump server  UI, API, Prometheus, Grafana"
  vpc_id      = aws_vpc.syswatcher.id

  # SSH
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # SysWatcher Chat UI
  ingress {
    description = "SysWatcher UI"
    from_port   = 3001
    to_port     = 3001
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ui_cidr]
  }

  # FastAPI
  ingress {
    description = "SysWatcher API"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ui_cidr]
  }

  # Grafana
  ingress {
    description = "Grafana"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ui_cidr]
  }

  # Prometheus
  ingress {
    description = "Prometheus"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]   # internal only
  }

  # node_exporter on jump itself
  ingress {
    description = "node_exporter (internal)"
    from_port   = 9100
    to_port     = 9100
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-jump-sg" }
}

# Dev + Test servers  monitored servers
resource "aws_security_group" "monitored" {
  name        = "${var.project}-monitored-sg"
  description = "Dev/Test servers monitored by SysWatcher"
  vpc_id      = aws_vpc.syswatcher.id

  # SSH from jump server only
  ingress {
    description = "SSH from jump"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.public_subnet_cidr]
  }

  # node_exporter  Prometheus scrapes this
  ingress {
    description = "node_exporter scrape from jump"
    from_port   = 9100
    to_port     = 9100
    protocol    = "tcp"
    cidr_blocks = [var.public_subnet_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-monitored-sg" }
}

# 
# User data scripts
# 
locals {
  # Jump server bootstrap  installs Docker + dependencies
  jump_user_data = <<-USERDATA
    #!/bin/bash
    set -e
    export DEBIAN_FRONTEND=noninteractive

    # System update
    apt-get update -qq
    apt-get upgrade -y -qq

    # Install deps
    apt-get install -y -qq \
      curl git wget python3 python3-pip \
      ca-certificates gnupg lsb-release \
      net-tools htop unzip jq

    # Install Docker
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
      | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

    # Add ubuntu user to docker group
    usermod -aG docker ubuntu

    # Enable + start Docker
    systemctl enable docker
    systemctl start docker

    # Install node_exporter on jump server itself
    NODE_VERSION="1.8.0"
    cd /tmp
    wget -q "https://github.com/prometheus/node_exporter/releases/download/v$${NODE_VERSION}/node_exporter-$${NODE_VERSION}.linux-amd64.tar.gz"
    tar xf "node_exporter-$${NODE_VERSION}.linux-amd64.tar.gz"
    mv "node_exporter-$${NODE_VERSION}.linux-amd64/node_exporter" /usr/local/bin/
    rm -rf "node_exporter-$${NODE_VERSION}.linux-amd64"*

    cat > /etc/systemd/system/node_exporter.service << 'SERVICE'
    [Unit]
    Description=Node Exporter
    After=network.target
    [Service]
    Type=simple
    ExecStart=/usr/local/bin/node_exporter
    Restart=always
    [Install]
    WantedBy=multi-user.target
    SERVICE

    systemctl daemon-reload
    systemctl enable node_exporter
    systemctl start node_exporter

    # Create syswatcher working directory
    mkdir -p /opt/syswatcher
    chown ubuntu:ubuntu /opt/syswatcher

    # Signal bootstrap complete
    touch /tmp/syswatcher_bootstrap_complete
    echo "Jump server bootstrap complete" >> /var/log/syswatcher_bootstrap.log
  USERDATA

  # Dev + Test server bootstrap  installs node_exporter only
  monitored_user_data = <<-USERDATA
    #!/bin/bash
    set -e
    export DEBIAN_FRONTEND=noninteractive

    apt-get update -qq
    apt-get install -y -qq curl wget net-tools htop

    # Install node_exporter
    NODE_VERSION="1.8.0"
    cd /tmp
    wget -q "https://github.com/prometheus/node_exporter/releases/download/v$${NODE_VERSION}/node_exporter-$${NODE_VERSION}.linux-amd64.tar.gz"
    tar xf "node_exporter-$${NODE_VERSION}.linux-amd64.tar.gz"
    mv "node_exporter-$${NODE_VERSION}.linux-amd64/node_exporter" /usr/local/bin/
    rm -rf "node_exporter-$${NODE_VERSION}.linux-amd64"*

    cat > /etc/systemd/system/node_exporter.service << 'SERVICE'
    [Unit]
    Description=Node Exporter
    After=network.target
    [Service]
    Type=simple
    ExecStart=/usr/local/bin/node_exporter
    Restart=always
    [Install]
    WantedBy=multi-user.target
    SERVICE

    systemctl daemon-reload
    systemctl enable node_exporter
    systemctl start node_exporter

    touch /tmp/syswatcher_bootstrap_complete
    echo "Monitored server bootstrap complete" >> /var/log/syswatcher_bootstrap.log
  USERDATA
}

# 
# EC2 Instances
# 

# Jump server  runs SysWatcher
resource "aws_instance" "jump" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.jump_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.jump.id]
  key_name               = aws_key_pair.syswatcher["jump"].key_name
  user_data              = local.jump_user_data

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.jump_disk_gb
    delete_on_termination = true
    encrypted             = true

    tags = { Name = "${var.project}-jump-root" }
  }

  tags = {
    Name = "${var.project}-jump"
    Role = "monitoring"
  }

  lifecycle {
    ignore_changes = [ami]  # don't replace on AMI update
  }
}

# Dev server
resource "aws_instance" "dev" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.dev_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.monitored.id]
  key_name               = aws_key_pair.syswatcher["dev"].key_name
  user_data              = local.monitored_user_data

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.dev_disk_gb
    delete_on_termination = true
    encrypted             = true

    tags = { Name = "${var.project}-dev-root" }
  }

  tags = {
    Name = "${var.project}-dev"
    Role = "development"
  }

  lifecycle {
    ignore_changes = [ami]
  }
}

# Test server
resource "aws_instance" "test" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.test_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.monitored.id]
  key_name               = aws_key_pair.syswatcher["test"].key_name
  user_data              = local.monitored_user_data

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.test_disk_gb
    delete_on_termination = true
    encrypted             = true

    tags = { Name = "${var.project}-test-root" }
  }

  tags = {
    Name = "${var.project}-test"
    Role = "testing"
  }

  lifecycle {
    ignore_changes = [ami]
  }
}

# 
# Elastic IPs  stable public IPs that survive reboots
# 
resource "aws_eip" "jump" {
  instance = aws_instance.jump.id
  domain   = "vpc"
  tags     = { Name = "${var.project}-jump-eip" }
}

resource "aws_eip" "dev" {
  instance = aws_instance.dev.id
  domain   = "vpc"
  tags     = { Name = "${var.project}-dev-eip" }
}

resource "aws_eip" "test" {
  instance = aws_instance.test.id
  domain   = "vpc"
  tags     = { Name = "${var.project}-test-eip" }
}
