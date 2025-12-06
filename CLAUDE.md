# 供应商邮件翻译系统

独立的桌面端(Electron)邮件翻译管理系统，帮助采购人员处理多语言供应商邮件往来。

## 登录方式

**使用公司邮箱直接登录**（仅限 `@jingzhicheng.com.cn`）
- 输入公司邮箱和密码
- 系统通过IMAP验证后自动拉取邮件
- 邮箱服务器：21cn 企业邮箱

### 21cn 企业邮箱设置

首次使用前，需要在 21cn 企业邮箱后台开启 SMTP 服务：

1. 登录 https://mail.21cn.net
2. 进行手机号码绑定或验证
3. **新用户默认未开启 SMTP 服务**，登录网页版进行身份验证后将自动开启
4. IMAP 服务一般默认开启

### IMAP/SMTP 服务器配置

| 服务 | 服务器地址 | 端口 | 加密方式 |
|------|-----------|------|----------|
| IMAP | imap-ent.21cn.com | 993 | SSL |
| POP3 | pop-ent.21cn.com | 995 | SSL |
| SMTP | smtp-ent.21cn.com | 465 | SSL |

## 项目架构

```
供应商邮件翻译系统/
├── backend/                 # FastAPI 后端
│   ├── main.py             # 应用入口
│   ├── config.py           # 配置管理
│   ├── database/           # 数据库层
│   │   ├── database.py     # SQLite 异步连接
│   │   ├── models.py       # SQLAlchemy 数据模型
│   │   └── crud.py         # 数据操作函数
│   ├── routers/            # API 路由
│   │   ├── users.py        # 邮箱登录认证
│   │   ├── emails.py       # 邮件管理
│   │   ├── translate.py    # 翻译服务
│   │   ├── approval.py     # 草稿管理
│   │   └── suppliers.py    # 供应商管理
│   └── services/           # 业务服务
│       ├── email_service.py    # IMAP/SMTP 邮件收发
│       └── translate_service.py # 翻译引擎
├── frontend/               # Vue3 + Electron 前端
│   ├── electron/           # Electron 主进程
│   ├── src/
│   │   ├── views/          # 页面组件
│   │   ├── api/            # API 封装
│   │   ├── stores/         # Pinia 状态管理
│   │   └── router/         # Vue Router
│   └── package.json        # 依赖与构建配置
└── data/                   # 数据目录（SQLite数据库）
```

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | FastAPI (Python 3.10+) |
| 数据库 | SQLite (aiosqlite) |
| ORM | SQLAlchemy 2.0 (async) |
| 认证 | JWT (邮箱IMAP验证) |
| 前端 | Vue 3 + Vite + Element Plus |
| 桌面端 | Electron 28 |
| 翻译 | DeepL API / Ollama |

## 核心功能

1. **邮箱登录** - 使用公司邮箱密码验证IMAP连接
2. **邮件收取** - IMAP协议拉取邮件，自动检测语言
3. **智能翻译** - 外语邮件翻译为中文（DeepL/Ollama）
4. **回复撰写** - 中文撰写，翻译为目标语言发送
5. **术语表** - 按供应商维护专业术语翻译

## 开发命令

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev              # 浏览器开发
npm run electron:dev     # Electron 开发
npm run electron:build   # 打包 Windows 安装包
```

## 打包发布

### 一键打包

双击项目根目录的 `build.bat` 即可自动完成打包，生成独立安装程序。

### 手动打包步骤

```bash
# 1. 打包后端 (生成 backend/dist/backend.exe)
cd backend
pip install pyinstaller
python -m PyInstaller backend.spec --noconfirm

# 2. 构建前端资源
cd frontend
npm install
npm run build

# 3. 打包 Electron 应用
npx electron-builder --win
```

### 打包产物

- **安装程序**: `frontend/dist_electron/供应商邮件翻译系统 Setup 1.0.0.exe`
- **免安装版**: `frontend/dist_electron/win-unpacked/`

### 打包配置文件

| 文件 | 说明 |
|------|------|
| `backend/backend.spec` | PyInstaller 打包配置 |
| `frontend/package.json` (build字段) | electron-builder 配置 |
| `build.bat` | 一键打包脚本 |

### 运行机制

安装后的软件启动流程：
1. 用户点击快捷方式启动 Electron 应用
2. Electron 主进程自动启动内置的后端服务 (backend.exe)
3. 等待后端健康检查通过后显示主界面
4. 关闭应用时自动停止后端服务

### 数据存储位置

安装版软件的数据保存在：
```
%APPDATA%\supplier-email-translator\data\
```

## 端口配置

| 服务 | 默认端口 | 环境变量 |
|------|----------|----------|
| 后端 API | 8000 | `BACKEND_PORT` |
| 前端开发 | 4567 | `VITE_PORT` |

## 启动安全机制

前端启动脚本包含以下安全措施：
- `vite.config.js` 设置 `strictPort: true`：端口被占用时直接失败，不会自动切换端口
- `package.json` 的 `electron:dev` 使用 `--kill-others-on-fail`：vite 启动失败时自动终止 electron
- 启动前应确保端口未被占用，否则整个启动过程会失败并退出

## 环境配置

创建 `backend/.env`：

```env
# 端口
BACKEND_PORT=8000

# 翻译引擎 - 切换方式
# ollama: 本地测试（免费）
# claude: Claude API（正式使用，半价 Batch）
# deepl: DeepL API
TRANSLATE_PROVIDER=ollama

# Claude API (Anthropic) - 正式使用
CLAUDE_API_KEY=your-claude-api-key
CLAUDE_MODEL=claude-sonnet-4-20250514

# DeepL API
DEEPL_API_KEY=your-deepl-key
DEEPL_FREE_API=true

# Ollama 本地模型 - 本地测试用
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b

# JWT 密钥
SECRET_KEY=your-secret-key
```

### 翻译引擎切换

| Provider | 说明 | 切换方式 |
|----------|------|----------|
| `ollama` | 本地测试，免费 | `TRANSLATE_PROVIDER=ollama` |
| `claude` | Claude API，支持 Batch | `TRANSLATE_PROVIDER=claude` |
| `deepl` | DeepL API | `TRANSLATE_PROVIDER=deepl` |

测试流程：
1. 先用 `ollama` 测试功能
2. 测试通过后改为 `claude`
3. 只需修改 `.env` 中的 `TRANSLATE_PROVIDER`

创建 `frontend/.env`（可选）：

```env
VITE_PORT=3456
VITE_API_URL=http://localhost:8000/api
```

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | /api/users/login | 邮箱登录 |
| GET | /api/users/me | 获取当前账户 |
| GET | /api/emails | 邮件列表（支持 search/sort_by/supplier_id/direction 参数） |
| GET | /api/emails/{id} | 邮件详情 |
| POST | /api/emails/fetch | 拉取新邮件 |
| PATCH | /api/emails/{id}/read | 标记已读 |
| PATCH | /api/emails/{id}/unread | 标记未读 |
| PATCH | /api/emails/{id}/flag | 添加星标 |
| PATCH | /api/emails/{id}/unflag | 取消星标 |
| POST | /api/emails/{id}/translate | 翻译单个邮件 |
| DELETE | /api/emails/{id} | 删除邮件 |
| GET | /api/emails/stats/summary | 邮件统计 |
| POST | /api/translate | 翻译文本 |
| POST | /api/translate/reverse | 回复翻译（中→外） |
| GET | /api/drafts | 获取草稿 |
| POST | /api/drafts | 创建草稿 |
| POST | /api/drafts/{id}/send | 发送草稿 |
| GET | /api/suppliers | 供应商列表 |
| GET | /api/translate/glossary/{id} | 术语表 |

## 数据模型

- **EmailAccount** - 邮箱账户（IMAP/SMTP配置，登录后自动创建）
- **Email** - 邮件（原文、译文、语言检测、is_read、is_flagged）
- **Supplier** - 供应商（域名、联系邮箱）
- **Glossary** - 术语表（原文→译文）
- **Draft** - 回复草稿（中文、译文、状态）

### 数据库迁移

如果数据库已存在，需要运行迁移脚本添加新字段：
```bash
cd backend
python -m migrations.add_email_flags
```

## 注意事项

- 首次运行自动创建 SQLite 数据库
- 仅允许 `@jingzhicheng.com.cn` 邮箱登录
- 邮箱密码存储在本地数据库（建议实现加密）
- Windows 打包产物在 `frontend/dist_electron/`

## 翻译优化机制

为节省翻译 API 调用，系统实现了两级缓存机制：

### 1. 翻译缓存表 (TranslationCache)

对翻译结果进行缓存，相同文本只翻译一次：

```
TranslationCache
├── text_hash      # 原文 SHA256（唯一索引）
├── source_text    # 原文
├── translated_text # 译文
├── source_lang    # 源语言
├── target_lang    # 目标语言
└── hit_count      # 缓存命中次数
```

**工作流程**：
1. 翻译请求 → 计算原文 hash
2. 查询缓存表 → 有缓存直接返回（hit_count++）
3. 无缓存 → 调用 API → 存入缓存

**效果**：签名、姓名、常用语句等重复内容只翻译一次

### 2. 邮件翻译共享表 (SharedEmailTranslation)

基于邮件 Message-ID 共享翻译结果，同一封邮件在公司内只翻译一次：

```
SharedEmailTranslation
├── message_id          # 邮件 RFC Message-ID（唯一）
├── subject_translated  # 主题译文
├── body_translated     # 正文译文
├── translated_by       # 翻译触发者
└── translated_at       # 翻译时间
```

**工作流程**：
1. 用户 A 翻译邮件 → 存入共享表
2. 用户 B 查看同一封邮件 → 检查共享表 → 有译文直接复用

**效果**：`@jingzhicheng.com.cn` 的所有用户共享翻译结果

### 缓存统计 API

| 端点 | 说明 |
|------|------|
| GET /api/translate/cache/stats | 获取缓存命中统计 |
| DELETE /api/translate/cache | 清空翻译缓存 |

### 3. 自动翻译触发

邮件拉取时自动翻译非中文邮件，流程：

```
POST /api/emails/fetch
       ↓
fetch_emails_background() 后台任务
       ↓
拉取邮件 → 检测语言 → 非中文? → 自动翻译 → 存入共享表
                          ↓
              所有用户直接看到翻译结果
```

**自动翻译逻辑**：
1. 邮件拉取后检测语言
2. 非中文邮件自动调用翻译 API
3. 翻译结果存入 `shared_email_translations` 表
4. 后续其他用户拉取同一封邮件时直接复用翻译

**触发时机**：
- 用户点击"拉取邮件"按钮
- 定时任务自动拉取（见下方批量翻译策略）

### 4. 批量翻译策略（计划中）

为进一步优化 API 成本，计划使用 Claude API Batch 进行批量翻译：

```
定时任务（每分钟）
       ↓
收集所有未翻译邮件
       ↓
立即提交 Batch API（提交要及时）
       ↓
后台轮询检查结果（返回随意，几分钟到几小时）
       ↓
结果写入 shared_email_translations
       ↓
用户刷新时看到翻译结果
```

**Batch API 优势**：
| 特性 | 普通 API | Batch API |
|------|----------|-----------|
| 价格 | 100% | 50%（半价） |
| 响应 | 实时 | 异步 |
| 适用 | 用户交互 | 后台批量 |

**数据模型**：

```
translation_batches 表（新增）
├── id                # 主键
├── batch_id          # Claude 返回的 Batch ID
├── status            # pending / submitted / completed / failed
├── email_count       # 包含邮件数量
├── submitted_at      # 提交时间
└── completed_at      # 完成时间

emails 表（新增字段）
├── translation_status  # pending / submitted / completed
└── batch_id           # 关联的 Batch ID
```

**混合策略**：
- 用户主动查看邮件详情 → 实时翻译（立即显示）
- 后台未读邮件 → 加入批量队列 → Batch API 处理

**实现步骤**：
1. 添加 `translation_batches` 表
2. 添加定时任务（APScheduler，每分钟提交）
3. 添加轮询任务（每 5 分钟检查 Batch 状态）
4. 集成 Claude Batch API

**当前测试**：先用本地 Ollama 模型测试定时任务流程，确认无误后再切换到 Claude Batch API

---

## 生产环境部署

### 服务器信息

- **服务器地址**: 61.145.212.28 (jzchardware.cn)
- **用户**: aaa
- **代码目录**: `/www/email-translate/`
- **访问地址**: `https://jzchardware.cn:8888/email/`
- **GitHub**: https://github.com/zp184764679/email-translate

### 端口配置

| 环境 | 后端端口 | 前端端口 | 前端路径 | API路径 |
|------|----------|----------|----------|---------|
| 开发 | 8000 | 4567 | - | /api/ |
| 生产 | 8007 | - | /email/ | /email/api/ |

**PM2服务名**: email-backend

### 部署命令

```bash
# Git 自动部署
git add . && git commit -m "更新说明" && git push origin main
# GitHub Actions 自动触发部署

# 手动部署
cd /www/email-translate
git pull origin main
cd backend && source venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm install && npm run build
pm2 restart email-backend

# 健康检查
curl http://127.0.0.1:8007/health
```

### 配置文件

| 文件 | 说明 |
|------|------|
| `ecosystem.config.js` | PM2 开发配置 (Windows) |
| `ecosystem.prod.config.js` | PM2 生产配置 (Linux) |
| `.github/workflows/deploy.yml` | GitHub Actions 自动部署 |
| `nginx.conf.example` | Nginx 配置示例 |
| `deploy.sh` | Linux 部署脚本 |

### Nginx 路由

```nginx
# 前端静态文件
location /email/ {
    alias /www/email-translate/frontend/dist/;
    try_files $uri $uri/ /email/index.html;
}

# API 代理
location /email/api/ {
    rewrite ^/email/api/(.*)$ /$1 break;
    proxy_pass http://127.0.0.1:8007;
}
```

**注意**: Nginx 会去掉 `/email/api/` 前缀，后端路由不需要包含此前缀

### GitHub Actions Secrets

需要在 GitHub 仓库设置以下 Secrets:

| Secret | 说明 |
|--------|------|
| SERVER_HOST | 服务器 IP (61.145.212.28) |
| SERVER_USER | SSH 用户名 (aaa) |
| SSH_PRIVATE_KEY | SSH 私钥 |
| SERVER_PORT | SSH 端口 (默认 22) |
