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
├── backend/                 # FastAPI 后端（服务器部署）
│   ├── main.py             # 应用入口
│   ├── config.py           # 配置管理
│   ├── celery_app.py       # Celery 异步任务配置
│   ├── websocket.py        # WebSocket 连接管理
│   ├── database/           # 数据库层
│   │   ├── database.py     # MySQL 异步连接
│   │   ├── models.py       # SQLAlchemy 数据模型
│   │   └── crud.py         # 数据操作函数
│   ├── routers/            # API 路由
│   │   ├── users.py        # 邮箱登录认证
│   │   ├── emails.py       # 邮件管理（含批量操作）
│   │   ├── translate.py    # 翻译服务
│   │   ├── approval.py     # 草稿管理
│   │   ├── suppliers.py    # 供应商管理
│   │   └── tasks.py        # 异步任务状态
│   ├── tasks/              # Celery 任务
│   │   ├── translate_tasks.py  # 翻译任务
│   │   ├── email_tasks.py      # 邮件任务
│   │   ├── ai_tasks.py         # AI 提取任务
│   │   └── maintenance_tasks.py # 定时维护
│   └── services/           # 业务服务
│       ├── email_service.py        # IMAP/SMTP 邮件收发
│       ├── translate_service.py    # 翻译引擎
│       ├── language_service.py     # Ollama 语言检测
│       └── notification_service.py # WebSocket 推送
├── frontend/               # Vue3 + Electron 前端（桌面客户端）
│   ├── electron/           # Electron 主进程
│   ├── src/
│   │   ├── views/          # 页面组件
│   │   ├── api/            # API 封装
│   │   ├── stores/         # Pinia 状态管理
│   │   ├── utils/          # 工具函数
│   │   │   └── websocket.js # WebSocket 客户端
│   │   └── router/         # Vue Router
│   └── package.json        # 依赖与构建配置
└── backend/.env            # 后端配置（MySQL、翻译API等）
```

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | FastAPI (Python 3.10+) |
| 数据库 | MySQL (服务器共享) |
| 缓存 | Redis (L1缓存 + 消息队列) |
| ORM | SQLAlchemy 2.0 (async) + aiomysql |
| 异步任务 | Celery + Redis |
| 实时推送 | WebSocket (FastAPI + 前端) |
| 认证 | JWT (邮箱IMAP验证) |
| 前端 | Vue 3 + Vite + Element Plus |
| 桌面端 | Electron 28 |
| 翻译 | Ollama (本地) / Claude API |

## 核心功能

1. **邮箱登录** - 使用公司邮箱密码验证IMAP连接
2. **邮件收取** - IMAP协议拉取邮件，Ollama智能检测语言
3. **智能翻译** - 外语邮件翻译为中文（Ollama/Claude）
4. **回复撰写** - 中文撰写，翻译为目标语言发送
5. **审批流程** - 草稿提交审批，审批人审核后发送
6. **术语表** - 按供应商维护专业术语翻译

## 审批功能

### 审批流程

```
作者撰写草稿 → 翻译 → 提交审批（选择审批人/组）
                           ↓
                    审批人收到待审批列表
                           ↓
              ┌────────────┼────────────┐
              ↓            ↓            ↓
           直接通过    修改后通过      驳回
           (发送邮件)  (修改+发送)  (返回修改)
```

### 审批方式

支持两种审批方式：

1. **单人审批** - 选择单个审批人，只有该人可以审批
2. **组审批** - 选择审批人组，组内任一成员都可以审批

### 审批人组管理

在 **设置页面 → 审批人组** 中可以：
- 创建审批人组（如"采购组"、"销售组"）
- 添加/移除组成员
- 编辑组名称和描述

### 设置默认审批人

在 **设置页面 → 审批设置** 中可以配置默认审批人，提交审批时会自动选择。

### 审批相关 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/drafts` | POST | 创建草稿 |
| `/api/drafts/{id}/send` | POST | 提交审批（支持 approver_id 或 approver_group_id） |
| `/api/drafts/{id}/approve` | POST | 审批通过并发送 |
| `/api/drafts/{id}/reject` | POST | 驳回 |
| `/api/drafts/pending` | GET | 获取待审批列表 |
| `/api/users/approvers` | GET | 获取可选审批人 |
| `/api/users/me/default-approver` | PUT | 设置默认审批人 |

### 审批人组 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/approval-groups` | GET | 获取我创建的组 |
| `/api/approval-groups/available` | GET | 获取可用组（我创建的+我所在的） |
| `/api/approval-groups` | POST | 创建审批人组 |
| `/api/approval-groups/{id}` | PUT | 更新组信息 |
| `/api/approval-groups/{id}` | DELETE | 删除组 |
| `/api/approval-groups/{id}/members` | POST | 添加组成员 |
| `/api/approval-groups/{id}/members/{member_id}` | DELETE | 移除组成员 |

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

**服务器统一部署架构**（2024年12月更新）：
1. 后端服务部署在服务器 `jzchardware.cn`（标准 HTTPS 443 端口）
2. 用户点击快捷方式启动 Electron 应用
3. Electron 显示启动画面，等待服务器健康检查通过
4. 检查通过后显示主界面，直接连接服务器 API
5. 所有用户共享同一个后端服务

**API 地址**：
- 开发环境：`http://127.0.0.1:2000/api`
- 生产环境：`https://jzchardware.cn/email/api`

## 端口配置

| 服务 | 默认端口 | 环境变量 |
|------|----------|----------|
| 后端 API（开发） | 2000 | `BACKEND_PORT` |
| 后端 API（生产） | 443 | 标准 HTTPS |
| 前端开发 | 4567 | `VITE_PORT` |

## 启动安全机制

前端启动脚本包含以下安全措施：
- `vite.config.js` 设置 `strictPort: true`：端口被占用时直接失败，不会自动切换端口
- `package.json` 的 `electron:dev` 使用 `--kill-others-on-fail`：vite 启动失败时自动终止 electron
- 启动前应确保端口未被占用，否则整个启动过程会失败并退出

**⚠️ 重要：不要随意更改端口配置！**

如果端口被占用（如 4567 或 8000），正确的做法是：
1. 查找占用端口的进程：`netstat -ano | findstr :4567`
2. 终止该进程：`taskkill /PID <进程ID> /F`
3. 重新启动应用

**错误做法**：修改端口号（如改成 5678）—— 这会导致配置混乱，前后端端口不一致

## 环境配置

创建 `backend/.env`：

```env
# ===== MySQL 数据库配置（服务器共享）=====
MYSQL_HOST=61.145.212.28
MYSQL_PORT=3306
MYSQL_USER=email_user
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=email_translate

# ===== 翻译引擎配置 =====
# ollama: 本地大模型（主力，免费）
# claude: Claude API（复杂邮件备用）
TRANSLATE_PROVIDER=ollama

# Ollama 本地模型 - 主力翻译引擎
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b

# Claude API (Anthropic) - 复杂邮件备用
CLAUDE_API_KEY=your-claude-api-key
CLAUDE_MODEL=claude-sonnet-4-20250514

# JWT 密钥
SECRET_KEY=your-secret-key
```

### 翻译引擎配置

| Provider | 说明 | 费用 | 用量统计 |
|----------|------|------|----------|
| `ollama` | 本地大模型（主力） | 免费 | 不统计 |
| `claude` | Claude API（复杂邮件备用） | 按量付费 | ✓ 自动记录 |

### 智能路由模式（推荐）

设置 `SMART_ROUTING_ENABLED=true`（默认启用），系统基于邮件复杂度自动选择最优引擎：

```
邮件进入
    ↓
Ollama 评估复杂度（规则优先，必要时用LLM打分）
    ↓
┌─────────────────┬─────────────────────┬─────────────────────┐
│ 简单(≤50分)     │ 中等(51-70)          │ 复杂(>70)           │
│                 │                      │                     │
│ Ollama直接翻译  │ Ollama拆分邮件结构   │ Ollama拆分邮件结构  │
│ (免费快速)      │ ├─ 正文 → Ollama     │ ├─ 正文 → Claude    │
│                 │ └─ 签名 → Ollama     │ └─ 签名 → Ollama    │
└─────────────────┴─────────────────────┴─────────────────────┘
    ↓ 失败时自动回退
Ollama → Claude
```

**智能拆分翻译**：
- Ollama 使用 `/think` 模式分析邮件结构，识别问候语、正文、签名
- 复杂邮件正文使用 Claude（理解能力强）
- 问候语、签名等固定格式内容使用 Ollama（免费、格式保持好）
- Ollama 超时 600 秒，num_predict=4096 支持长文本

**复杂度判断标准**：
- 简单：<500字符，无表格/列表，日常问候确认
- 中等：一般业务邮件，多个事项
- 复杂：技术文档、合同条款、表格数据、多层嵌套

**用量保护**：
- 80% 用量时发出警告
- 95% 用量时自动禁用（防止超额收费）
- 每月1日自动重置

### 用量统计 API

| 端点 | 说明 |
|------|------|
| GET /api/translate/usage-stats | 获取所有引擎用量 |
| GET /api/translate/usage-stats/{provider} | 获取指定引擎用量 |
| POST /api/translate/usage-stats/{provider}/reset | 重新启用被禁用的引擎 |

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
| POST | /api/emails/batch/read | 批量标记已读 |
| POST | /api/emails/batch/unread | 批量标记未读 |
| POST | /api/emails/batch/delete | 批量删除 |
| GET | /api/emails/stats/summary | 邮件统计 |
| GET | /api/emails/thread/{thread_id} | 获取邮件线程 |
| GET | /api/emails/contacts | 获取历史联系人（按频率排序） |
| POST | /api/translate | 翻译文本 |
| POST | /api/translate/reverse | 回复翻译（中→外） |
| GET | /api/drafts | 获取草稿 |
| POST | /api/drafts | 创建草稿 |
| POST | /api/drafts/{id}/send | 发送草稿 |
| GET | /api/suppliers | 供应商列表 |
| GET | /api/translate/glossary/{id} | 术语表 |
| GET | /api/labels | 获取标签列表 |
| POST | /api/labels | 创建标签 |
| PUT | /api/labels/{id} | 更新标签 |
| DELETE | /api/labels/{id} | 删除标签 |
| POST | /api/labels/emails/{email_id} | 为邮件添加标签 |
| DELETE | /api/labels/emails/{email_id} | 移除邮件标签 |
| GET | /api/folders | 获取文件夹树 |
| POST | /api/folders | 创建文件夹 |
| PUT | /api/folders/{id} | 更新文件夹 |
| DELETE | /api/folders/{id} | 删除文件夹 |
| POST | /api/folders/{id}/emails | 添加邮件到文件夹 |
| DELETE | /api/folders/{id}/emails/{email_id} | 从文件夹移除邮件 |
| GET | /api/folders/{id}/emails | 获取文件夹中的邮件 |
| GET | /api/calendar/events | 获取日历事件（支持 start/end 时间过滤） |
| POST | /api/calendar/events | 创建日历事件 |
| GET | /api/calendar/events/{id} | 获取单个事件详情 |
| PUT | /api/calendar/events/{id} | 更新日历事件 |
| DELETE | /api/calendar/events/{id} | 删除日历事件 |
| POST | /api/calendar/events/from-email/{email_id} | 从邮件创建事件 |
| GET | /api/calendar/events/by-email/{email_id} | 获取邮件关联的事件 |
| POST | /api/ai/extract/{email_id} | AI 提取邮件信息（force=true 强制重新提取） |
| GET | /api/ai/extract/{email_id} | 获取已提取的信息 |
| DELETE | /api/ai/extract/{email_id} | 删除提取结果 |
| WS | /ws/{account_id} | WebSocket 实时推送连接 |

## 数据模型

- **EmailAccount** - 邮箱账户（IMAP/SMTP配置，登录后自动创建）
- **Email** - 邮件（原文、译文、语言检测、is_read、is_flagged、labels、folders）
- **Supplier** - 供应商（域名、联系邮箱）
- **Glossary** - 术语表（原文→译文）
- **Draft** - 回复草稿（中文、译文、状态、approver_id、approver_group_id）
- **ApproverGroup** - 审批人组（name、description、owner_id）
- **ApproverGroupMember** - 审批人组成员（group_id、member_id）
- **EmailLabel** - 邮件标签（name、color、account_id）
- **EmailFolder** - 自定义文件夹（支持嵌套，parent_id）
- **CalendarEvent** - 日历事件（title、start_time、end_time、可关联邮件）
- **EmailExtraction** - AI 提取结果（summary、dates、amounts、contacts、action_items）

### 数据库迁移

如果数据库已存在，需要运行迁移脚本添加新字段：
```bash
cd backend
# 基础功能
python -m migrations.add_email_flags
python -m migrations.add_email_labels
python -m migrations.add_email_folders
python -m migrations.add_translation_cache
python -m migrations.add_draft_recipient_fields
python -m migrations.add_email_rules

# 日历功能
python -m migrations.add_calendar_events
python -m migrations.add_event_reminder
python -m migrations.add_recurrence_fields

# 审批和翻译
python -m migrations.add_approval_fields
python -m migrations.add_translation_status
python -m migrations.add_sent_email_mapping
python -m migrations.add_attachment_hash
python -m migrations.add_batch_account_id

# 数据清理（可选）
python -m migrations.remove_shared_translation_originals
python -m migrations.encrypt_passwords
```

**注意**：CI/CD 部署流程会自动执行所有迁移脚本，见 `.github/workflows/deploy.yml`

## 安全机制

### 登录状态存储

登录状态通过 JWT token 保存在 Electron 的 localStorage 中：

```
%APPDATA%\supplier-email-translator\
├── Local Storage/          # localStorage 数据（包含 JWT token）
├── data/                   # 应用数据
└── ...
```

**重要说明**：
- Token 有效期为 7 天
- 卸载软件时，用户数据会被自动清理（`deleteAppDataOnUninstall: true`）
- 用户可通过左下角"退出登录"按钮主动清除登录状态

### 退出登录

点击左侧导航栏底部的"退出登录"按钮：
1. 清除 localStorage 中的 token、email、accountId
2. 停止自动拉取邮件定时器
3. 跳转到登录页面

### 安全建议

| 风险 | 说明 | 缓解措施 |
|------|------|----------|
| 本机共享 | 同一台电脑的其他 Windows 用户可能访问 AppData | 使用 Windows 账户隔离 |
| 设备丢失 | 电脑丢失后无需密码即可访问 | 启用 Windows 登录密码 + 硬盘加密 |
| 公共电脑 | 在公共电脑上使用后忘记退出 | 使用完毕后点击"退出登录" |

### 相关配置

```json
// frontend/package.json - NSIS 配置
"nsis": {
  "deleteAppDataOnUninstall": true  // 卸载时清理用户数据
}
```

## 注意事项

- 首次运行自动创建数据库表
- 仅允许 `@jingzhicheng.com.cn` 邮箱登录
- 邮箱密码存储在数据库（建议实现加密）
- Windows 打包产物在 `frontend/dist_electron/`

## 数据库架构

所有桌面端连接服务器上的 MySQL，实现翻译结果共享：

```
用户 A 电脑                      服务器 (61.145.212.28)
┌──────────────┐                ┌─────────────────┐
│ Electron 应用 │                │     MySQL       │
│ + backend.exe │ ────────────→ │ email_translate │
└──────────────┘                └─────────────────┘
                                        ↑
用户 B 电脑                              │
┌──────────────┐                        │
│ Electron 应用 │ ──────────────────────┘
│ + backend.exe │
└──────────────┘
```

**共享的数据表**：
| 表 | 说明 |
|---|------|
| `translation_cache` | 翻译缓存（相同文本只翻译一次） |
| `shared_email_translations` | 邮件翻译共享（同一封邮件只翻译一次） |
| `email_accounts` | 用户邮箱账户 |
| `emails` | 邮件数据 |
| `suppliers` | 供应商信息 |
| `glossaries` | 术语表 |
| `drafts` | 草稿 |

## MySQL 服务器部署

### 服务器信息

- **服务器地址**: 61.145.212.28 (jzchardware.cn)
- **MySQL 端口**: 3306
- **数据库名**: email_translate

### 初始化数据库

```sql
-- 创建数据库
CREATE DATABASE email_translate CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建用户并授权
CREATE USER 'email_user'@'%' IDENTIFIED BY 'your-secure-password';
GRANT ALL PRIVILEGES ON email_translate.* TO 'email_user'@'%';
FLUSH PRIVILEGES;
```

### 防火墙配置

确保服务器开放 3306 端口供内网访问：

```bash
# 如果使用 firewalld
firewall-cmd --permanent --add-port=3306/tcp
firewall-cmd --reload
```

### 验证连接

```bash
mysql -h 61.145.212.28 -u email_user -p email_translate
```

## 翻译优化机制

为节省翻译 API 调用，系统实现了三级缓存机制：

```
翻译请求 → Redis(L1) → MySQL(L2) → 翻译API
              ↑            ↑           ↓
           ~1ms         ~10ms      ~500ms+
              └─ 热点数据 ─┘  ← 写入缓存
```

### 0. Redis 缓存 (L1)

内存级缓存，毫秒响应，适合热点数据：

```bash
# 服务器配置（宝塔面板安装或手动安装）
yum install redis -y && systemctl start redis && systemctl enable redis

# .env 配置
REDIS_URL=redis://localhost:6379/0
CACHE_DEFAULT_TTL=3600
CACHE_PREFIX=email_translate
```

**特性**：
- 使用 `shared/cache_config.py` 模块
- **Graceful 降级**：Redis 不可用时自动回退到 MySQL 缓存
- TTL 默认 1 小时

### 1. 翻译缓存表 - TranslationCache (L2)

对翻译结果进行持久化缓存，相同文本只翻译一次：

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
2. 查 Redis(L1) → 命中直接返回
3. 未命中 → 查 MySQL(L2) → 命中则写回 Redis 并返回
4. 都未命中 → 调用翻译 API → 同时写入 Redis + MySQL

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
3. **智能翻译**：检测邮件中的引用内容，只翻译新增部分
4. 翻译结果存入 `shared_email_translations` 表
5. 后续其他用户拉取同一封邮件时直接复用翻译

**智能翻译（回复邮件优化）**：
- 自动检测引用标记（`On ... wrote:`, `From:`, `>` 等）
- 只翻译新增内容，跳过引用部分
- 尝试复用引用邮件的已有翻译（通过 `in_reply_to` 查找）
- 显著减少 API 调用次数，降低翻译成本

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

## Celery 异步任务系统

使用 Celery + Redis 实现后台异步任务，提升用户体验。

### 架构

```
用户操作 → FastAPI（立即返回任务ID）→ 前端显示"处理中"
                    ↓
            Redis（消息队列）
                    ↓
            Celery Worker（后台执行）
                    ↓
            完成 → 更新数据库 → WebSocket 推送前端刷新
```

### 核心文件

| 文件 | 说明 |
|------|------|
| `backend/celery_app.py` | Celery 配置和实例 |
| `backend/tasks/translate_tasks.py` | 翻译任务（单个、批量、Batch轮询） |
| `backend/tasks/email_tasks.py` | 邮件任务（拉取、发送、导出） |
| `backend/tasks/ai_tasks.py` | AI 提取任务 |
| `backend/tasks/maintenance_tasks.py` | 定时维护任务 |
| `backend/websocket.py` | WebSocket 连接管理 |
| `backend/services/notification_service.py` | 推送通知服务 |
| `frontend/src/utils/websocket.js` | WebSocket 客户端 |

### 任务列表

| 任务 | 说明 | 原耗时 | 优化后 |
|------|------|--------|--------|
| `translate_email_task` | 翻译单封邮件 | 3-10s | 100ms响应 |
| `batch_translate_task` | 批量翻译 | 400-500s | 30s响应 |
| `fetch_emails_task` | 拉取邮件 | 50-100s | 15s响应 |
| `send_email_task` | 发送邮件 | 2-7s | 100ms响应 |
| `export_emails_task` | 导出邮件 | 5-15s | 100ms响应 |
| `extract_email_info_task` | AI 提取 | 5-20s | 100ms响应 |

### 定时任务

| 任务 | 周期 | 说明 |
|------|------|------|
| `warm_translation_cache` | 每小时 | 预热高频翻译到 Redis |
| `cleanup_old_translations` | 每天2点 | 清理30天未用缓存 |
| `cleanup_temp_files` | 每天3点 | 清理临时导出文件 |
| `rebuild_contacts_index` | 每天4点 | 重建联系人缓存 |
| `poll_batch_status` | 每30秒 | 轮询 Batch API 状态 |

### WebSocket 事件

| 事件 | 说明 |
|------|------|
| `translation_complete` | 翻译完成 |
| `translation_failed` | 翻译失败 |
| `email_sent` | 邮件发送成功 |
| `fetch_progress` | 拉取进度更新 |
| `fetch_complete` | 拉取完成 |
| `extraction_complete` | AI 提取完成 |
| `export_ready` | 导出完成，可下载 |
| `batch_translation_complete` | 批量翻译完成 |

### 部署命令

```bash
# 1. 安装依赖
pip install celery[redis] redis flower pymysql

# 2. 启动 Celery Worker
celery -A celery_app worker -l info

# 3. 启动 Celery Beat（定时任务）
celery -A celery_app beat -l info

# 4. 启动 Flower 监控（可选）
celery -A celery_app flower --port=5555

# PM2 配置
pm2 start "celery -A celery_app worker -l info" --name celery-worker
pm2 start "celery -A celery_app beat -l info" --name celery-beat
```

### 环境变量

```bash
# .env 添加
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

### 任务状态 API

| 端点 | 说明 |
|------|------|
| `GET /api/tasks/{task_id}` | 查询任务状态 |
| `DELETE /api/tasks/{task_id}` | 取消任务 |
| `POST /api/tasks/translate/email/{id}` | 提交翻译任务 |
| `POST /api/tasks/translate/batch` | 提交批量翻译 |
| `POST /api/tasks/fetch` | 提交拉取任务 |
| `POST /api/tasks/send/{draft_id}` | 提交发送任务 |
| `POST /api/tasks/extract/{email_id}` | 提交提取任务 |
| `POST /api/tasks/export` | 提交导出任务 |

## 功能实现状态

对比标准邮件客户端（Outlook、Gmail），以下是各功能的实现状态：

### 已完成功能 ✓

| 功能 | 说明 |
|------|------|
| 邮箱登录认证 | IMAP 验证 + JWT token |
| 记住登录状态 | localStorage 持久化，7天有效 |
| 邮件列表显示 | 双语对比视图（原文/译文） |
| 邮件详情查看 | 分栏显示原文和翻译 |
| 手动拉取邮件 | 点击"同步"按钮 |
| 自动定时拉取 | 每5分钟自动检查新邮件（前端定时器实现） |
| 新邮件桌面通知 | Electron Notification API |
| 智能翻译 | 支持 Ollama/Claude |
| 翻译后台化 | 翻译时不阻塞 UI，用户可继续操作 |
| 翻译缓存 | 相同文本只翻译一次 |
| 邮件翻译共享 | 同一封邮件跨用户只翻译一次 |
| 邮件标记 | 星标、已读/未读 |
| 邮件删除 | 单个删除 |
| 批量标记已读 | POST /api/emails/batch/read |
| 批量标记未读 | POST /api/emails/batch/unread |
| 批量删除 | POST /api/emails/batch/delete |
| 回复邮件 | 中文撰写 → 翻译 → 发送 |
| 草稿保存 | 保存回复草稿 |
| 供应商管理 | 按域名分类供应商 |
| 邮件搜索 | 按主题、发件人搜索 |
| 邮件排序 | 按时间、发件人排序 |
| 语言检测 | Ollama 智能识别邮件语言（替代 langdetect，解决英德混淆） |
| 附件存储 | 保存到服务器 |
| 附件下载 | 单个下载、批量下载 |
| 登录后自动拉取 | 首次登录自动同步邮件 |
| 邮件线程显示 | 对话分组展示 |
| 未读计数 | 显示真正的未读邮件数 |
| 增量拉取 | 只拉取最新邮件，减少服务器负载 |
| 单实例锁定 | 防止多个实例同时运行 |
| 启动画面 | Electron 启动时显示加载画面 |
| 应用自动更新 | electron-updater 实现 |
| 邮件导出 | 导出为 EML 格式 |
| 邮件签名 | 自定义签名模板，支持多语言翻译 |
| 收件人自动补全 | 标签式输入，支持历史联系人搜索 |
| 邮件回复增强 | 全部回复、收件人/抄送去重、邮箱验证 |
| 快捷键系统 | 邮件列表和详情页完整快捷键支持 |
| 新邮件声音提示 | Web Audio API 播放提示音 |

### 快捷键一览

**邮件列表页**:
| 快捷键 | 功能 |
|--------|------|
| j / k | 上下选择邮件 |
| Enter | 打开邮件 |
| x | 选择/取消 |
| s | 切换星标 |
| d | 删除 |
| m / u | 标记已读/未读 |
| r | 回复 |
| f | 转发 |
| l | 添加标签 |
| Ctrl+a | 全选 |

**邮件详情页**:
| 快捷键 | 功能 |
|--------|------|
| r | 回复 |
| a | 全部回复 |
| f | 转发 |
| s | 切换星标 |
| d | 删除 |
| j / k | 线程中上下封 |
| l | 添加标签 |
| Escape | 返回列表 |
| Ctrl+Enter | 发送回复（撰写时）|

### 待实现功能

当前所有核心功能已实现，暂无高优先级待实现功能。

### 配置参数

```python
# backend/config.py
email_poll_interval: int = 300  # 自动拉取间隔（秒），默认5分钟
```

### 签名相关 API 端点

```
GET  /api/signatures            # 获取用户签名列表
GET  /api/signatures/default    # 获取默认签名
GET  /api/signatures/{id}       # 获取单个签名
POST /api/signatures            # 创建签名
PUT  /api/signatures/{id}       # 更新签名
DELETE /api/signatures/{id}     # 删除签名
POST /api/signatures/{id}/set-default  # 设为默认签名
```

## CI/CD 自动化部署

项目使用 GitHub Actions 实现自动化部署，包括后端部署和桌面端发布。

### 后端自动部署

推送到 `main` 分支时自动触发：

```
git push origin main
    ↓
GitHub Actions (.github/workflows/deploy.yml)
    ↓
SSH 连接服务器 → 拉取代码 → 安装依赖 → 重启 PM2
```

### 桌面端发布流程

两种方式触发发布：

#### 方式一：打 Tag 发布（推荐）

```bash
# 1. 修改版本号
cd frontend
npm version 1.0.1  # 自动更新 package.json 并创建 git tag

# 2. 推送代码和 tag
git push origin main --tags
```

#### 方式二：手动触发

1. 打开 GitHub 仓库 → Actions → "Build and Release Desktop App"
2. 点击 "Run workflow"
3. 输入版本号（如 1.0.1）
4. 点击运行

### 发布流程详情

```
触发发布（推送 v* 标签）
    ↓
GitHub Actions (Windows Runner)
    ↓
├── 打包后端 (PyInstaller)
├── 构建前端 (Vite)
├── 打包 Electron (electron-builder)
    ↓
上传到 GitHub Releases
├── 供应商邮件翻译系统 Setup x.x.x.exe
└── latest.yml
    ↓
用户端自动检测更新 → 从 GitHub 下载安装
```

### 更新托管配置

| 配置项 | 值 |
|--------|-----|
| 托管方式 | GitHub Releases |
| 仓库 | `zp184764679/email-translate` |
| electron-updater provider | `github` |

**为什么使用 GitHub Releases 而不是自建服务器：**
- GitHub Actions 在美国，上传到中国服务器跨国传输很慢（100MB+ 文件需要 20+ 分钟）
- GitHub CDN 全球分布，用户下载更快
- 无需维护文件服务器
- 发布记录自动保存，便于版本管理

### GitHub Secrets 配置

| Secret 名称 | 说明 | 用途 |
|-------------|------|------|
| `SERVER_HOST` | 服务器 IP (61.145.212.28) | 后端部署 |
| `SERVER_USER` | SSH 用户名 (root) | 后端部署 |
| `SSH_PRIVATE_KEY` | SSH 私钥 (email_deploy) | 后端部署 |
| `GITHUB_TOKEN` | 自动提供 | 发布到 GitHub Releases |

### 快速发布命令

```bash
# 发布新版本（一行命令）
git tag -a v1.0.5 -m "release: 新功能描述" && git push origin v1.0.5

# 查看所有版本
git tag -l

# 删除错误的标签（本地+远程）
git tag -d v1.0.5 && git push origin :refs/tags/v1.0.5
```

### 版本号规范

遵循语义化版本：`主版本.次版本.修订号`

| 类型 | 说明 | 示例 |
|------|------|------|
| 主版本 | 不兼容的大改动 | 1.0.0 → 2.0.0 |
| 次版本 | 新增功能（向后兼容） | 1.0.0 → 1.1.0 |
| 修订号 | Bug 修复 | 1.0.0 → 1.0.1 |

## 更新日志

### v1.0.44 (2025-12-18)

#### Bug 修复
- **Batch API 轮询任务修复**：修正 `poll_batch_status` 中的导入错误和异步调用问题
- **维护任务模型引用修复**：`reset_monthly_quota` 中 `UsageProvider` 改为 `TranslationUsage`
- **翻译状态字段修复**：移除不存在的 `translated_at` 字段引用，改用 `translation_status`

#### 新功能
- **新邮件声音提示**：使用 Web Audio API 播放提示音
- **TranslationBatch 账户关联**：添加 `account_id` 字段，支持批次完成通知

#### 架构优化
- **批处理轮询统一**：移除 main.py 中的重复轮询，统一由 Celery Beat 处理
- **月度配额重置**：在 Celery Beat 中注册定时任务，每月1日自动执行

#### CI/CD 改进
- **完整迁移脚本**：deploy.yml 现执行所有 17 个迁移脚本
- **环境变量补充**：.env.example 添加 Redis、Celery、智能路由等配置

#### 文档更新
- **快捷键文档**：完整记录邮件列表页和详情页的快捷键
- **迁移脚本列表**：更新为完整的 17 个迁移脚本

#### 数据库迁移
```bash
# 新增迁移（为 TranslationBatch 添加 account_id 字段）
python -m migrations.add_batch_account_id
```

### v1.0.35 (2025-12-15)

#### 安全修复
- **附件路径遍历漏洞修复**：添加 `_sanitize_filename()` 方法防止恶意文件名
- **附件大小限制**：添加 100MB 上传限制和磁盘空间检查
- **附件下载防护**：验证文件路径在允许目录内
- **草稿删除权限**：完善作者和审批人权限检查

#### 稳定性改进
- **翻译锁改用数据库**：从内存 `set` 改为 `translation_status` 字段，支持多进程
- **共享翻译表防重复**：使用 MySQL `ON DUPLICATE KEY UPDATE` 防止并发插入冲突
- **语言检测备用方案**：添加基于字符特征的快速检测（中/日/韩/俄），Ollama 作为备用
- **搜索长度限制**：限制搜索字符串最大 500 字符
- **文件夹删除确认**：检查子文件夹和关联邮件，添加 `force` 参数

#### 前端优化
- **列表加载竞态修复**：使用 `AbortController` 取消旧请求
- **翻译数据不覆盖**：只更新翻译字段，不覆盖整个邮件对象
- **全局变量清理**：`window.__selectedEmailIds` 改为 Pinia store
- **WebSocket 重连优化**：页面离开后正确取消重连
- **401 状态处理**：使用事件通知正确清理 store 状态
- **定时器清理**：登出时停止自动拉取定时器

#### 数据库迁移
```bash
# 需要执行的迁移（添加 translation_status 字段）
python -m migrations.add_translation_status

# 可选：清理冗余数据（移除共享翻译表中的原文字段，节省存储空间）
python -m migrations.remove_shared_translation_originals
```
