#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}${NC} $1"; }
info() { echo -e "  ${BLUE}${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}${NC} $1"; }

CMD=${1:-apply}

# Must run from terraform/ directory
cd "$(dirname "$0")"

echo ""
echo -e "${BOLD}SysWatcher  Terraform deployment${NC}"
echo ""

#  Check terraform 
if ! command -v terraform &>/dev/null; then
  fail "terraform not found"
  echo "  Install: https://developer.hashicorp.com/terraform/install"
  exit 1
fi
ok "terraform $(terraform version -json | python3 -c 'import sys,json; print(json.load(sys.stdin)["terraform_version"])')"

#  Check AWS credentials 
if ! aws sts get-caller-identity &>/dev/null; then
  fail "AWS credentials not configured"
  echo "  Run: aws configure"
  echo "  Or:  export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=..."
  exit 1
fi
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region 2>/dev/null || echo "unknown")
ok "AWS account: $ACCOUNT  region: $REGION"

#  tfvars 
if [ ! -f terraform.tfvars ]; then
  if [ -f terraform.tfvars.example ]; then
    warn "terraform.tfvars not found  copying from example"
    cp terraform.tfvars.example terraform.tfvars
    warn "Review terraform.tfvars before continuing"
    "${EDITOR:-nano}" terraform.tfvars
  else
    fail "terraform.tfvars not found"
    exit 1
  fi
fi
ok "terraform.tfvars found"

#  Create keys directory 
mkdir -p keys

case "$CMD" in

  #  init 
  init)
    info "Running terraform init..."
    terraform init
    ok "Initialised"
    ;;

  #  plan 
  plan)
    terraform init -upgrade -input=false
    terraform plan -out=tfplan
    ok "Plan saved to tfplan"
    ;;

  #  apply 
  apply)
    info "Initialising Terraform..."
    terraform init -upgrade -input=false

    info "Planning..."
    terraform plan -out=tfplan

    echo ""
    echo "Resources to create:"
    echo "  3 EC2 instances (jump + dev + test)"
    echo "  3 Elastic IPs"
    echo "  3 SSH key pairs (saved to ./keys/)"
    echo "  1 VPC + subnet + IGW + route table"
    echo "  2 Security groups"
    echo ""
    read -rp "Apply? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
      echo "Aborted"
      exit 0
    fi

    info "Applying..."
    terraform apply tfplan
    ok "Infrastructure created"

    #  Post-apply: update syswatcher.conf 
    echo ""
    info "Extracting outputs..."

    JUMP_IP=$(terraform output -raw jump_public_ip)
    DEV_IP=$(terraform output  -raw dev_public_ip)
    TEST_IP=$(terraform output -raw test_public_ip)

    JUMP_KEY=$(terraform output -raw key_jump)
    DEV_KEY=$(terraform output  -raw key_dev)
    TEST_KEY=$(terraform output -raw key_test)

    # Update ../syswatcher.conf if it exists
    CONF="../syswatcher.conf"
    if [ -f "$CONF" ]; then
      info "Updating syswatcher.conf with server IPs..."

      python3 - << PYEOF
import re

conf_path = '$CONF'
with open(conf_path) as f:
    content = f.read()

# Remove existing server lines
content = re.sub(r'^(jump|dev|test)\s*=.*\n?', '', content, flags=re.MULTILINE)

# Add new server block after the # -- Servers -- comment
server_block = """jump = $JUMP_IP   ubuntu   $JUMP_KEY
dev  = $DEV_IP   ubuntu   $DEV_KEY
test = $TEST_IP   ubuntu   $TEST_KEY
"""

content = re.sub(
    r'(# Format: name = IP.*\n)',
    r'\1' + server_block,
    content
)

with open(conf_path, 'w') as f:
    f.write(content)

print('  syswatcher.conf updated')
PYEOF
      ok "syswatcher.conf updated with server IPs"
    else
      warn "syswatcher.conf not found at $CONF  update manually"
    fi

    #  Print summary 
    echo ""
    terraform output summary
    echo ""
    echo -e "${BOLD}SSH commands:${NC}"
    terraform output ssh_jump
    terraform output ssh_dev
    terraform output ssh_test
    echo ""
    echo -e "${BOLD}Next steps:${NC}"
    echo "  1. Wait 2-3 minutes for EC2 bootstrap to finish"
    echo "  2. SSH into jump server:"
    echo "     $(terraform output -raw ssh_jump)"
    echo "  3. From jump server, run SysWatcher:"
    echo "     cd /opt/syswatcher"
    echo "     git clone <your-repo> ."
    echo "     ./install.sh"
    echo ""
    ;;

  #  destroy 
  destroy)
    warn "This will DESTROY all SysWatcher infrastructure"
    warn "EC2 instances, EIPs, VPC, keys  all deleted"
    echo ""
    read -rp "Type DESTROY to confirm: " CONFIRM
    if [ "$CONFIRM" != "DESTROY" ]; then
      echo "Aborted"
      exit 0
    fi
    terraform destroy -auto-approve
    ok "All resources destroyed"
    ;;

  #  outputs 
  outputs)
    terraform output
    ;;

  #  refresh 
  refresh)
    terraform refresh
    terraform output summary
    ;;

  *)
    echo "Usage: ./deploy.sh [init|plan|apply|destroy|outputs|refresh]"
    echo "Default: apply"
    ;;
esac
