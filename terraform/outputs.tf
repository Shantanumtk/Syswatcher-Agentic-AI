# 
# IPs
# 
output "jump_public_ip" {
  description = "Public IP of jump/monitoring server (stable EIP)"
  value       = aws_eip.jump.public_ip
}

output "jump_private_ip" {
  description = "Private IP of jump server (used in prometheus.yml)"
  value       = aws_instance.jump.private_ip
}

output "dev_public_ip" {
  description = "Public IP of dev server"
  value       = aws_eip.dev.public_ip
}

output "dev_private_ip" {
  description = "Private IP of dev server (used in prometheus.yml)"
  value       = aws_instance.dev.private_ip
}

output "test_public_ip" {
  description = "Public IP of test server"
  value       = aws_eip.test.public_ip
}

output "test_private_ip" {
  description = "Private IP of test server (used in prometheus.yml)"
  value       = aws_instance.test.private_ip
}

# 
# SSH connection commands
# 
output "ssh_jump" {
  description = "SSH command to connect to jump server"
  value       = "ssh -i keys/syswatcher-jump.pem ubuntu@${aws_eip.jump.public_ip}"
}

output "ssh_dev" {
  description = "SSH command to connect to dev server"
  value       = "ssh -i keys/syswatcher-dev.pem ubuntu@${aws_eip.dev.public_ip}"
}

output "ssh_test" {
  description = "SSH command to connect to test server"
  value       = "ssh -i keys/syswatcher-test.pem ubuntu@${aws_eip.test.public_ip}"
}

# 
# Key file paths
# 
output "key_jump" {
  description = "Path to jump server SSH private key"
  value       = "keys/syswatcher-jump.pem"
}

output "key_dev" {
  description = "Path to dev server SSH private key"
  value       = "keys/syswatcher-dev.pem"
}

output "key_test" {
  description = "Path to test server SSH private key"
  value       = "keys/syswatcher-test.pem"
}

# 
# SysWatcher URLs (on jump server)
# 
output "syswatcher_ui" {
  description = "SysWatcher Chat UI"
  value       = "http://${aws_eip.jump.public_ip}:3001"
}

output "grafana_url" {
  description = "Grafana dashboard"
  value       = "http://${aws_eip.jump.public_ip}:3000"
}

output "prometheus_url" {
  description = "Prometheus"
  value       = "http://${aws_eip.jump.public_ip}:9090"
}

output "api_url" {
  description = "SysWatcher FastAPI"
  value       = "http://${aws_eip.jump.public_ip}:8000"
}

output "api_docs" {
  description = "SysWatcher API docs"
  value       = "http://${aws_eip.jump.public_ip}:8000/docs"
}

# 
# syswatcher.conf block  ready to paste
# 
output "syswatcher_conf_servers_block" {
  description = "Paste this into syswatcher.conf [servers] section"
  value       = <<-CONF
    # Paste into syswatcher.conf:
    jump = ${aws_eip.jump.public_ip}   ubuntu   keys/syswatcher-jump.pem
    dev  = ${aws_eip.dev.public_ip}   ubuntu   keys/syswatcher-dev.pem
    test = ${aws_eip.test.public_ip}   ubuntu   keys/syswatcher-test.pem
  CONF
}

# 
# prometheus.yml servers block  ready to paste
# 
output "prometheus_scrape_targets" {
  description = "Prometheus scrape targets for all 3 servers"
  value       = <<-PROM
    # Add to prometheus/prometheus.yml scrape_configs:

    - job_name: jump
      static_configs:
        - targets: ["${aws_instance.jump.private_ip}:9100"]
          labels:
            server_name: jump

    - job_name: dev
      static_configs:
        - targets: ["${aws_instance.dev.private_ip}:9100"]
          labels:
            server_name: dev

    - job_name: test
      static_configs:
        - targets: ["${aws_instance.test.private_ip}:9100"]
          labels:
            server_name: test
  PROM
}

# 
# AMI used
# 
output "ami_id" {
  description = "Ubuntu 22.04 AMI used for all instances"
  value       = data.aws_ami.ubuntu.id
}

output "ami_name" {
  description = "AMI name"
  value       = data.aws_ami.ubuntu.name
}

# 
# Summary table
# 
output "summary" {
  description = "Full infrastructure summary"
  value       = <<-SUMMARY
    
                  SysWatcher AWS Infrastructure                  
    
      Server   Role        Public IP                Private IP   
                                    
      jump     monitoring  ${aws_eip.jump.public_ip}  ${aws_instance.jump.private_ip}  
      dev      development ${aws_eip.dev.public_ip}  ${aws_instance.dev.private_ip}  
      test     testing     ${aws_eip.test.public_ip}  ${aws_instance.test.private_ip}  
    
      SysWatcher UI     http://${aws_eip.jump.public_ip}:3001       
      Grafana           http://${aws_eip.jump.public_ip}:3000       
      Prometheus        http://${aws_eip.jump.public_ip}:9090       
      API docs          http://${aws_eip.jump.public_ip}:8000/docs  
    
  SUMMARY
}
