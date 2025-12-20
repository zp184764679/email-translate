#!/bin/bash
# 添加本地开发机的 SSH 公钥到服务器
# 运行方式: 在服务器上执行此脚本

PUBLIC_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOZu0HjNfnyKcyMYDnH1a4UpkOi5NI2HhodQzVik+TTe dev-server-access-20251220"

# 确保 .ssh 目录存在
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# 检查公钥是否已存在
if grep -q "dev-server-access-20251220" ~/.ssh/authorized_keys 2>/dev/null; then
    echo "公钥已存在，无需添加"
else
    echo "$PUBLIC_KEY" >> ~/.ssh/authorized_keys
    chmod 600 ~/.ssh/authorized_keys
    echo "公钥添加成功"
fi
