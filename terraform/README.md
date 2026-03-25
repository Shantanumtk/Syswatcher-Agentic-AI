# SysWatcher — Terraform AWS Infrastructure

Creates 3 EC2 instances on AWS:

| Server | Role          | Type       | What runs                    |
|--------|---------------|------------|------------------------------|
| jump   | monitoring    | t3.medium  | SysWatcher (Docker stack)    |
| dev    | development   | t3.small   | Your dev workloads           |
| test   | testing       | t3.small   | Your test workloads          |

All 3 are monitored by SysWatcher running on the jump server.

## Quick start

```bash
cd terraform

# 1. Copy and fill in vars
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars     # set aws_region, aws_profile

# 2. Deploy
./deploy.sh apply

# 3. SSH into jump server (after 2-3 min bootstrap)
ssh -i keys/syswatcher-jump.pem ubuntu@<jump-ip>

# 4. Run SysWatcher on jump server
cd /opt/syswatcher
git clone <your-repo> .
./install.sh
```

## What gets created

- **VPC** `10.0.0.0/16` with public subnet + internet gateway
- **3 EC2 instances** — Ubuntu 22.04 LTS, gp3 encrypted root volumes
- **3 Elastic IPs** — stable public IPs that survive reboots
- **3 SSH key pairs** — auto-generated, saved to `./keys/*.pem`
- **2 Security groups**:
  - `jump-sg` — SSH(22), UI(3001), API(8000), Grafana(3000) from internet
  - `monitored-sg` — SSH(22) + node_exporter(9100) from jump only
- **Bootstrap scripts** — Docker + node_exporter installed automatically

## Outputs

```bash
terraform output                        # all outputs
terraform output jump_public_ip         # jump server IP
terraform output ssh_jump               # SSH command
terraform output syswatcher_conf_servers_block  # paste into syswatcher.conf
terraform output prometheus_scrape_targets      # paste into prometheus.yml
terraform output summary                # full table
```

## Managing

```bash
./deploy.sh plan     # preview changes
./deploy.sh apply    # create / update
./deploy.sh outputs  # show all outputs
./deploy.sh refresh  # sync state with AWS
./deploy.sh destroy  # tear everything down
```

## Cost estimate (us-east-1)

| Resource      | Monthly est. |
|---------------|-------------|
| t3.medium     | ~$30        |
| 2x t3.small   | ~$30        |
| 3x EIP (used) | ~$0         |
| 70GB gp3 EBS  | ~$6         |
| **Total**     | **~$66/mo** |

Stop instances when not in use to save cost:
```bash
aws ec2 stop-instances --instance-ids $(terraform output -raw jump_instance_id)
```
