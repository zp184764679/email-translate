# 共享模块使用指南

本目录包含所有子系统共享的基础设施代码和配置模板。

## 目录结构

```
shared/
├── auth_middleware.py      # 统一认证授权中间件
├── logging_config.py       # 统一日志配置
├── validators.py           # 数据验证模块（Flask用）
├── cache_config.py         # Redis缓存配置
├── api-config.js           # 前端API配置（JavaScript）
├── .env.template           # 后端环境变量模板
├── frontend.env.template   # 前端环境变量模板
└── README.md               # 本文件
```

---

## 1. 认证授权中间件 (`auth_middleware.py`)

### 后端使用示例（Flask）

```python
import sys
sys.path.insert(0, '../shared')

from auth_middleware import requires_auth, requires_role, success_response, error_response

@app.route('/api/v1/users', methods=['GET'])
@requires_auth
def get_users():
    # g.current_user 包含当前用户信息
    users = User.query.all()
    return jsonify(success_response(data=[u.to_dict() for u in users]))

@app.route('/api/v1/admin/settings', methods=['PUT'])
@requires_role('admin')
def update_settings():
    # 仅管理员可访问
    pass
```

### 生成Token

```python
from auth_middleware import generate_token

token = generate_token(
    user_id=user.id,
    username=user.username,
    role=user.role
)
```

---

## 2. 统一日志配置 (`logging_config.py`)

### 使用示例

```python
import sys
sys.path.insert(0, '../shared')

from logging_config import get_system_logger, log_api_request, log_external_api_call

# 初始化系统日志
logger = get_system_logger('crm')

# 记录API请求
logger.info("处理客户查询请求")

# 记录外部API调用
log_external_api_call(logger, 'HR系统', '/api/employees', 200, 150)
```

### 环境变量配置

```bash
LOG_LEVEL=INFO        # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT=standard   # standard, json, simple
LOG_DIR=./logs        # 日志存储目录
```

---

## 3. 数据验证模块 (`validators.py`)

### Flask请求验证

```python
import sys
sys.path.insert(0, '../shared')

from validators import Schema, String, Integer, Email, validate_request

@app.route('/api/v1/customers', methods=['POST'])
@validate_request(Schema(
    name=String(min_length=2, max_length=100),
    email=Email(required=False),
    age=Integer(min_value=0, max_value=200, required=False)
))
def create_customer(validated_data):
    # validated_data 已经过验证和类型转换
    customer = Customer(**validated_data)
    db.session.add(customer)
    db.session.commit()
    return jsonify(success_response(data=customer.to_dict()))
```

### 可用验证器

- `String(min_length, max_length, pattern, choices)`
- `Integer(min_value, max_value)`
- `Float(min_value, max_value, precision)`
- `Boolean()`
- `Date(date_format='%Y-%m-%d')`
- `DateTime(datetime_format='%Y-%m-%d %H:%M:%S')`
- `Email()`
- `Phone()` - 中国大陆手机号
- `List(item_validator, min_items, max_items)`

---

## 4. Redis缓存 (`cache_config.py`)

### 基本使用

```python
import sys
sys.path.insert(0, '../shared')

from cache_config import cache_get, cache_set, cached, CacheManager

# 简单缓存操作
cache_set('user:1', {'id': 1, 'name': '张三'}, ttl=3600)
user = cache_get('user:1')

# 函数结果缓存装饰器
@cached(ttl=300)
def get_expensive_data(product_id):
    # 耗时操作
    return db.query(Product).get(product_id)

# 缓存管理器（带命名空间）
product_cache = CacheManager('product')
product_cache.set('123', data, ttl=600)
```

### 环境变量

```bash
REDIS_URL=redis://localhost:6379/0
CACHE_DEFAULT_TTL=3600
CACHE_PREFIX=app
```

---

## 5. 前端API配置 (`api-config.js`)

### 使用示例

```javascript
import { API_BASE_URL, SYSTEM_APIS, getApiUrl, createApiClient } from '../shared/api-config'

// 获取当前系统API地址
const url = getApiUrl('/api/customers')  // 使用默认API_BASE_URL

// 跨系统调用
const hrUrl = getApiUrl('/api/employees', 'hr')  // 使用HR系统URL

// 创建axios客户端（已配置认证拦截器）
const api = createApiClient()
const response = await api.get('/customers')
```

---

## 6. API版本控制迁移指南

### 为什么需要API版本控制？

1. **向后兼容** - 允许旧客户端继续工作
2. **平滑升级** - 新功能可以在新版本中添加
3. **清晰的API契约** - 明确API的稳定性

### 迁移步骤

#### Flask系统（CRM/HR/SCM/EAM/SHM/MES）

**步骤1: 创建版本化蓝图**

```python
# routes/v1/__init__.py
from flask import Blueprint

v1_bp = Blueprint('v1', __name__, url_prefix='/api/v1')

# 导入所有路由模块
from . import customers, orders
```

**步骤2: 更新路由注册**

```python
# app.py 或 __init__.py
from routes.v1 import v1_bp

# 旧版路由（保留兼容性）
app.register_blueprint(customers_bp, url_prefix='/api/customers')

# 新版路由
app.register_blueprint(v1_bp)  # 所有v1路由在 /api/v1/* 下
```

**步骤3: 添加版本重定向（可选）**

```python
@app.route('/api/customers', methods=['GET'])
def customers_redirect():
    # 重定向到v1
    return redirect(url_for('v1.get_customers'), code=307)
```

#### FastAPI系统（报价系统）

```python
# main.py
from fastapi import APIRouter

# 创建v1路由器
v1_router = APIRouter(prefix="/api/v1")

# 导入并注册子路由
from api import drawings, materials
v1_router.include_router(drawings.router, prefix="/drawings", tags=["图纸管理"])
v1_router.include_router(materials.router, prefix="/materials", tags=["材料库"])

# 注册到主应用
app.include_router(v1_router)

# 保留旧路由兼容性（可选）
app.include_router(drawings.router, prefix="/api/drawings", tags=["图纸管理"], deprecated=True)
```

---

## 7. 数据库连接池配置

### Flask-SQLAlchemy

```python
# config.py 或 app.py
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,           # 连接池大小
    'max_overflow': 20,        # 超出pool_size后最多可创建的连接数
    'pool_recycle': 1200,      # 连接回收时间（秒）
    'pool_pre_ping': True,     # 每次取连接时检查连接是否有效
}
```

### SQLAlchemy（FastAPI）

```python
from sqlalchemy import create_engine

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1200
)
```

---

## 8. 统一错误响应格式

所有系统应使用以下响应格式：

### 成功响应

```json
{
  "success": true,
  "data": { ... },
  "message": "操作成功"
}
```

### 错误响应

```json
{
  "success": false,
  "error": "错误描述",
  "code": "ERROR_CODE",
  "field": "字段名（可选）"
}
```

### 分页响应

```json
{
  "success": true,
  "data": [...],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5
  }
}
```

---

## 9. 环境变量配置

复制模板文件到各系统后端目录：

```bash
cp shared/.env.template CRM/backend/.env
cp shared/.env.template HR/backend/.env
# ... 其他系统
```

然后修改系统特定的配置，特别是：

- `JWT_SECRET` - **必须修改为安全的随机字符串**
- `MYSQL_PASSWORD` - 数据库密码
- `ALLOWED_ORIGINS` - 允许的前端域名

---

## 10. 安装依赖

确保各系统安装了必要的依赖：

```bash
# 后端通用依赖
pip install PyJWT python-dotenv redis

# Flask系统
pip install Flask-Migrate

# 前端
npm install axios
```

---

## 端口分配表

| 系统 | 后端端口 | 前端端口 |
|------|----------|----------|
| 报价 | 8001 | 3000/8000 |
| CRM | 8002 | 3001 |
| HR | 8003 | 3002 |
| SCM | 8004 | 3003 |
| EAM | 8005 | 3004 |
| SHM | 8006 | 3005 |
| MES | 8007 | 3006 |
| 采购 | 5001 | 3007 |

---

## 常见问题

### Q: 如何在系统间共享用户认证？

使用相同的 `JWT_SECRET` 配置，token在各系统间通用。

### Q: Redis不可用时怎么办？

缓存模块会自动降级，直接执行函数不使用缓存。

### Q: 如何自定义验证错误消息？

```python
String(min_length=5, error_message='名称长度不能少于5个字符')
```
