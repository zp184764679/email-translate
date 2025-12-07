# Email-Translate 服务器部署配置

## 服务器信息

- **服务器**: 61.145.212.28
- **用户**: aaa
- **域名**: jzchardware.cn

---

## 当前配置

### 1. 后端服务

| 配置项 | 值 |
|--------|-----|
| 端口 | 2000 |
| PM2 名称 | email-backend |
| 工作目录 | /www/email-translate/backend |
| Python 环境 | /www/email-translate/backend/venv |

### 2. 环境变量 (.env)

文件位置: `/www/email-translate/backend/.env`

```env
# Application
DEBUG=false

# MySQL 数据库配置
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=exak472008
MYSQL_DATABASE=email_translate

# 翻译引擎 - 使用 ollama
TRANSLATE_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b

# JWT
SECRET_KEY=jzchardware-sso-secret-key-change-in-production

# Email polling interval (seconds)
EMAIL_POLL_INTERVAL=300
```

### 3. Nginx 代理

已添加到 `/etc/nginx/nginx.conf`:

```nginx
# Email翻译系统 - Email Translate API (端口 2000)
location /email/api/ {
    limit_req zone=api_limit burst=20 nodelay;
    proxy_pass http://127.0.0.1:2000/api/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
}

location /email/api/health {
    proxy_pass http://127.0.0.1:2000/health;
}
```

### 4. API 访问地址

| 类型 | URL |
|------|-----|
| 本地直连 | http://127.0.0.1:2000/ |
| Nginx 代理 | https://jzchardware.cn:8888/email/api/ |
| 健康检查 | https://jzchardware.cn:8888/email/api/health |

---

## GitHub Actions 自动部署

### 需要配置的 Secrets

在 GitHub 仓库 Settings → Secrets and variables → Actions 添加:

| Secret 名称 | 值 |
|-------------|-----|
| SERVER_HOST | 61.145.212.28 |
| SERVER_USER | aaa |
| SSH_PRIVATE_KEY | (与 jzc_systems 相同的私钥) |

### 部署流程

1. Push 到 main 分支自动触发
2. SSH 连接服务器
3. 拉取最新代码
4. 安装 Python 依赖
5. 重启 PM2 服务
6. 健康检查

---

## 开发机需要注意

### 前端 API 配置

前端调用后端 API 时，需要使用以下基础路径:

```javascript
// 生产环境
const API_BASE_URL = '/email/api';

// 或完整 URL
const API_BASE_URL = 'https://jzchardware.cn:8888/email/api';
```

### 本地开发

如果本地开发需要连接服务器后端:

```javascript
// 开发环境 (直连服务器)
const API_BASE_URL = 'http://61.145.212.28:2000/api';
```

### 端口规划

| 系统 | 端口 |
|------|------|
| Portal | 3002 |
| HR | 8003 |
| Account | 8004 |
| Quotation | 8001 |
| Caigou | 5001 |
| SHM | 8006 |
| **Email-Translate** | **2000** |

---

## 常用命令

```bash
# 查看服务状态
pm2 status email-backend

# 查看日志
pm2 logs email-backend --lines 50

# 重启服务
pm2 restart email-backend

# 测试健康检查
curl http://127.0.0.1:2000/health

# 测试 Nginx 代理
curl -k https://127.0.0.1:8888/email/api/health
```

---

## 数据库

- **数据库名**: email_translate
- **字符集**: utf8mb4
- **用户**: root (密码: exak472008)

表结构由 SQLAlchemy 自动创建。

---

## 待办事项

- [ ] 如需使用 Claude 翻译，需要更新 .env 中的 CLAUDE_API_KEY
- [ ] 前端部署配置（如有前端）
- [ ] 配置 SSL 证书自动续期（已有 Let's Encrypt）
