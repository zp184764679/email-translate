#!/bin/bash
# 邮件系统健康检查脚本
# 用法: bash /www/email-translate/deploy/health-check.sh

set -e

echo "=== 邮件系统健康检查 ==="
echo "时间: $(date)"
echo ""

ERRORS=0

# 1. 检查前端文件
echo -n "[1/5] 检查前端文件... "
if [ -f "/www/email-translate/frontend-web/index.html" ]; then
    echo "✓ 存在"
else
    echo "✗ 缺失！"
    ERRORS=$((ERRORS + 1))
fi

# 2. 检查 Nginx 配置
echo -n "[2/5] 检查 Nginx 配置... "
if grep -q "location /email/" /etc/nginx/conf.d/jzc.conf 2>/dev/null; then
    echo "✓ 正确"
else
    echo "✗ 缺少 /email/ 配置！"
    ERRORS=$((ERRORS + 1))
fi

# 3. 检查后端服务
echo -n "[3/5] 检查后端服务... "
if curl -s --connect-timeout 5 http://127.0.0.1:2000/api/health 2>/dev/null | grep -q "healthy"; then
    echo "✓ 正常"
else
    echo "✗ 异常！"
    ERRORS=$((ERRORS + 1))
fi

# 4. 检查 PM2 进程
echo -n "[4/5] 检查 PM2 进程... "
if pm2 list 2>/dev/null | grep -q "email-backend.*online"; then
    echo "✓ 运行中"
else
    echo "✗ 未运行！"
    ERRORS=$((ERRORS + 1))
fi

# 5. 检查外部访问
echo -n "[5/5] 检查外部访问... "
TITLE=$(curl -s --connect-timeout 10 https://jzchardware.cn/email/ 2>/dev/null | grep -o "<title>.*</title>" | head -1)
if echo "$TITLE" | grep -q "供应商邮件翻译系统"; then
    echo "✓ 正常"
else
    echo "✗ 异常！返回: $TITLE"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "=== 检查完成 ==="

if [ $ERRORS -eq 0 ]; then
    echo "状态: 全部正常"
    exit 0
else
    echo "状态: 发现 $ERRORS 个问题"
    exit 1
fi
