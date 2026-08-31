# 商场AI经营分析系统 — Code Wiki

> 本文档是对 `mall-ai-analyst` 项目仓库的结构化技术说明，涵盖整体架构、模块职责、关键类与函数、依赖关系及运行方式。

---

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构](#2-整体架构)
3. [目录结构](#3-目录结构)
4. [后端模块详解（FastAPI）](#4-后端模块详解fastapi)
5. [前端模块详解（Vue 3）](#5-前端模块详解vue-3)
6. [AI 服务集成（Ollama + LangChain）](#6-ai-服务集成ollama--langchain)
7. [依赖关系](#7-依赖关系)
8. [API 接口说明](#8-api-接口说明)
9. [数据模型与流转](#9-数据模型与流转)
10. [项目运行方式](#10-项目运行方式)
11. [部署架构（Docker Compose）](#11-部署架构docker-compose)
12. [已知设计要点与注意事项](#12-已知设计要点与注意事项)

---

## 1. 项目概述

**商场AI经营分析系统** 是一套面向商场日常经营的本地化分析平台，核心能力包括：

- 从旧 POS 系统导出的 **Excel/CSV** 文件导入销售流水
- 自动统计每日销售额、成本、毛利、毛利率
- 按品类聚合销售与毛利表现
- 基于本地大模型（**qwen2.5:14b**）生成 3 条可执行的中文运营改进建议
- 提供领导看板，支持 **Excel / PDF** 报表导出
- **完全本地化部署**，可断网运行，数据不外泄

技术栈定位：前后端分离 + 本地大模型推理，全部通过 Docker Compose 编排。

---

## 2. 整体架构

系统采用经典三层架构，由 3 个独立服务组成：

```
┌──────────────────────────────────────────────────────────────┐
│                        浏览器（用户）                          │
│              Vue 3 + Element Plus + ECharts                   │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP (80 / 5173 dev)
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              Frontend 容器（Nginx 托管静态资源）               │
│  - 静态站点由 Vite 构建产物提供                                │
│  - /api 请求反向代理至后端                                     │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP (8000)
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              Backend 容器（FastAPI + Uvicorn）                 │
│  - REST API：上传 / 汇总 / AI建议 / 日期列表                   │
│  - SQLAlchemy ORM + SQLite（mall_sales.db）                   │
│  - pandas 解析 Excel/CSV                                      │
└──────────┬───────────────────────────────┬───────────────────┘
           │                               │
           ▼                               ▼
┌─────────────────────┐         ┌──────────────────────────────┐
│  SQLite 数据文件     │         │   Ollama 容器（GPU 推理）      │
│  mall_sales.db      │         │   模型：qwen2.5:14b           │
└─────────────────────┘         │   端口：11434                 │
                                └──────────────────────────────┘
```

**关键架构特征：**

| 特征 | 说明 |
|------|------|
| 前后端分离 | 前端 Vue 3 SPA，后端 FastAPI RESTful |
| 本地 AI 推理 | 通过 Ollama 运行 qwen2.5:14b，无需调用云端 API |
| 容器化部署 | 3 个服务由 docker-compose 统一编排 |
| 轻量持久化 | 使用 SQLite 单文件数据库，便于本地化 |
| GPU 加速 | Ollama 容器启用 NVIDIA runtime |

---

## 3. 目录结构

```
mall-ai-analyst/
├── backend/                       # 后端服务（FastAPI）
│   ├── main.py                    # 应用入口 & 路由定义
│   ├── database.py                # 数据库连接与会话管理
│   ├── models.py                  # SQLAlchemy ORM 模型
│   ├── schemas.py                 # Pydantic 数据校验模型
│   ├── crud.py                    # 数据库 CRUD 操作
│   ├── ai_service.py              # LLM 运营建议生成
│   ├── init_db.py                 # 数据库初始化脚本
│   ├── requirements.txt           # Python 依赖
│   └── Dockerfile                 # 后端容器镜像
├── frontend/                      # 前端服务（Vue 3）
│   ├── src/
│   │   ├── main.js                # 应用入口
│   │   ├── App.vue                # 根组件（侧边栏布局）
│   │   ├── router/index.js        # 路由配置
│   │   ├── api/index.js           # Axios API 封装
│   │   └── views/
│   │       ├── Dashboard.vue      # 经营仪表盘
│   │       └── Import.vue         # 数据导入页
│   ├── index.html                 # HTML 模板
│   ├── package.json               # Node 依赖
│   ├── vite.config.js             # Vite 构建配置
│   └── Dockerfile                 # 前端容器镜像（多阶段构建）
├── docker-compose.yml             # 容器编排
└── 使用说明.md                     # 部署使用文档
```

---

## 4. 后端模块详解（FastAPI）

### 4.1 `database.py` — 数据库连接与会话

负责 SQLAlchemy 引擎、会话工厂与 Base 声明。

| 成员 | 类型 | 说明 |
|------|------|------|
| `DATABASE_URL` | str | `"sqlite:///./mall_sales.db"`，SQLite 数据库路径 |
| `engine` | Engine | SQLAlchemy 引擎，`check_same_thread=False` 以适配 FastAPI 多线程 |
| `SessionLocal` | sessionmaker | 会话工厂，`autocommit=False, autoflush=False` |
| `Base` | DeclarativeBase | ORM 模型基类 |
| `get_db()` | generator | FastAPI 依赖注入函数，提供请求级数据库会话并自动关闭 |

### 4.2 `models.py` — ORM 数据模型

#### `SaleRecord(Base)` — 销售记录表

表名：`sales`，对应一条商品销售流水。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer, PK | 主键，自增 |
| `date` | Date, indexed | 销售日期（建索引以加速按日查询） |
| `product_name` | String | 商品名称 |
| `category` | String | 品类 |
| `unit_price` | Float | 售价（单价） |
| `cost_price` | Float | 成本价 |
| `quantity` | Integer | 销售数量 |
| `total_sales` | Float | 销售额 = 售价 × 数量（入库时自动计算） |
| `profit` | Float | 毛利 = (售价 − 成本) × 数量（入库时自动计算） |

### 4.3 `schemas.py` — Pydantic 校验模型

| 类 | 用途 | 关键字段 |
|----|------|----------|
| `SaleCreate` | 创建销售记录的入参 schema | `date, product_name, category, unit_price, cost_price, quantity` |
| `SaleOut` | 输出 schema，继承自 `SaleCreate` | 额外含 `id, total_sales, profit`；`Config.from_attributes=True` 支持 ORM 转 Pydantic |
| `DailySummary` | 每日汇总响应 schema | `date, total_sales, total_cost, total_profit, margin, record_count` |

### 4.4 `crud.py` — 数据库操作层

封装所有数据库读写逻辑，与路由层解耦。

| 函数 | 入参 | 返回 | 说明 |
|------|------|------|------|
| `create_sale(db, sale_data)` | Session, SaleCreate | SaleRecord | 计算并写入 `total_sales` 与 `profit`，提交并刷新 |
| `get_daily_summary(db, query_date)` | Session, date | dict \| None | 聚合当日总销售额、总成本、毛利、毛利率、记录数 |
| `get_category_summary(db, query_date)` | Session, date | list[tuple] | 按 `category` 分组，返回 (品类, 销售额合计, 毛利合计) |
| `get_latest_dates(db, limit=30)` | Session, int | list[date] | 倒序返回最近 30 个有数据的日期 |

**关键计算逻辑（`get_daily_summary`）：**

- 总成本 = `SUM(cost_price * quantity)`（按数量加权）
- 毛利 = 总销售额 − 总成本
- 毛利率 = 毛利 / 总销售额 × 100（百分比，保留两位小数）

### 4.5 `ai_service.py` — AI 运营建议生成

详见 [第 6 节](#6-ai-服务集成ollama--langchain)。

### 4.6 `main.py` — 应用入口与路由

创建 FastAPI 应用、配置 CORS、初始化数据表、定义 4 个 API 端点。

| 成员/路由 | 说明 |
|-----------|------|
| `app` | FastAPI 实例，`title="商场AI经营分析系统"` |
| CORS 中间件 | `allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]`，全开放（开发友好） |
| `Base.metadata.create_all(bind=engine)` | 启动时自动建表 |
| `POST /upload` | 上传 Excel/CSV，逐行解析入库 |
| `GET /summary/{query_date}` | 获取某日汇总 |
| `GET /advice/{query_date}` | 获取某日 AI 建议 |
| `GET /dates` | 获取有数据的日期列表 |

### 4.7 `init_db.py` — 数据库初始化脚本

独立脚本，显式调用 `Base.metadata.create_all` 建表。

> 注：该脚本导入路径为 `from backend.database import ...`，需在**项目根目录**执行；而 `main.py` 内部导入无 `backend.` 前缀，需在 `backend/` 目录下执行。两套导入路径不一致，运行时需注意工作目录。

---

## 5. 前端模块详解（Vue 3）

### 5.1 `main.js` — 应用入口

创建 Vue 应用实例，注册 `ElementPlus` 组件库与 `router` 路由，挂载至 `#app`。

### 5.2 `App.vue` — 根组件（布局）

使用 Element Plus 的 `el-container` 布局：

- `el-aside`（宽 200px，深色背景 `#304156`）：左侧导航菜单
- `el-menu` 开启 `router` 模式，菜单项直接对应路由
- 菜单项：**经营仪表盘**（`/dashboard`）、**数据导入**（`/import`）
- `el-main`：通过 `<router-view />` 渲染子页面

### 5.3 `router/index.js` — 路由配置

| 路径 | 行为 |
|------|------|
| `/` | 重定向至 `/dashboard` |
| `/dashboard` | 加载 `Dashboard.vue` |
| `/import` | 加载 `Import.vue` |

采用 `createWebHistory`（HTML5 History 模式）。

### 5.4 `api/index.js` — API 封装层

基于 `axios` 创建统一客户端，集中管理所有后端请求。

**客户端配置：**

| 配项 | 值 | 说明 |
|------|----|------|
| `baseURL` | `/api` | 开发环境由 Vite proxy 转发，生产环境由 Nginx 反代 |
| `timeout` | `60000` (60s) | AI 建议生成较慢，需较长超时 |

**响应拦截器：** 统一提取 `response.data`，错误时从 `error.response.data.detail` 提取信息并 reject。

**封装方法：**

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `uploadSalesFile(file)` | POST | `/upload` | 以 `multipart/form-data` 上传文件 |
| `getDailySummary(date)` | GET | `/summary/{date}` | 获取某日汇总 |
| `getDailyAdvice(date)` | GET | `/advice/{date}` | 获取某日 AI 建议 |
| `getAvailableDates()` | GET | `/dates` | 获取有数据的日期列表 |

### 5.5 `views/Dashboard.vue` — 经营仪表盘

核心展示页面，职责：

- 按日期选择加载数据（`loadData`）
- 调用 `api.getDailySummary` 与 `api.getDailyAdvice`
- 通过 `echarts` 渲染图表（`initChart`）
- 引入 `xlsx`（Excel 导出）、`jspdf` + `html2canvas`（PDF 导出）

**关键响应式状态：**

| 变量 | 用途 |
|------|------|
| `selectedDate` | 当前选中日期（默认今天） |
| `summary` | 当日汇总数据 |
| `suggestions` | AI 建议列表 |
| `chartDom` | ECharts 容器引用 |

### 5.6 `views/Import.vue` — 数据导入页

使用 `el-upload` 拖拽上传组件：

- `:http-request="handleUpload"` 自定义上传逻辑（调用 `api.uploadSalesFile`）
- `accept=".xlsx,.csv"` 限制文件类型
- 上传结果通过 `el-alert` 反馈

### 5.7 `vite.config.js` — 构建配置

- 插件：`@vitejs/plugin-vue`
- 开发代理：`/api` → `http://localhost:8000`（解决跨域，对接本地后端）

### 5.8 前端 `Dockerfile` — 多阶段构建

```
阶段1: node:18  → npm install + npm run build → 生成 dist/
阶段2: nginx:alpine → 拷贝 dist/ 至 /usr/share/nginx/html → 暴露 80
```

---

## 6. AI 服务集成（Ollama + LangChain）

### 6.1 `ai_service.py` 核心实现

```python
llm = Ollama(model="qwen2.5:14b", base_url="http://ollama:11434")
```

| 要素 | 说明 |
|------|------|
| LLM 后端 | Ollama 本地推理服务 |
| 模型 | `qwen2.5:14b`（通义千问 14B 参数量） |
| 连接地址 | `http://ollama:11434`（Docker 内部服务名） |
| 编排框架 | LangChain（`PromptTemplate` + LCEL 管道 `prompt | llm`） |

### 6.2 `generate_advice(daily_data, category_data)`

| 参数 | 类型 | 说明 |
|------|------|------|
| `daily_data` | dict | 当日汇总（含 `date, total_sales, total_profit, margin`） |
| `category_data` | str | 各品类销售额/毛利拼接字符串 |

**Prompt 模板要求模型扮演"资深商场运营专家"，输出 3 条建议，每条包含：**

1. `title` — 策略名称
2. `reason` — 针对问题/机会
3. `action` — 执行措施
4. `effect` — 预期效果

**输出处理：** 清洗可能包裹的 ` ```json ` markdown 标记后，`json.loads` 解析为列表返回。

---

## 7. 依赖关系

### 7.1 后端依赖（`requirements.txt`）

| 依赖 | 版本 | 用途 |
|------|------|------|
| fastapi | 0.115.0 | Web 框架 |
| uvicorn | 0.30.6 | ASGI 服务器 |
| sqlalchemy | 2.0.35 | ORM |
| pandas | 2.2.2 | Excel/CSV 解析与数据处理 |
| openpyxl | 3.1.5 | xlsx 引擎（pandas 依赖） |
| python-multipart | 0.0.9 | 文件上传支持 |
| langchain | 0.3.0 | LLM 编排框架 |
| langchain-community | 0.3.0 | Ollama 集成 |

> 隐性依赖：SQLite（Python 标准库自带）、`pydantic`（随 FastAPI 安装）。

### 7.2 前端依赖（`package.json`）

**运行时依赖：**

| 依赖 | 版本 | 用途 |
|------|------|------|
| vue | ^3.4.0 | 前端框架 |
| vue-router | ^4.3.0 | 路由 |
| pinia | ^2.1.0 | 状态管理（已声明，当前未使用） |
| axios | ^1.7.0 | HTTP 客户端 |
| element-plus | ^2.8.0 | UI 组件库 |
| echarts | ^5.5.0 | 图表库 |
| xlsx | ^0.18.5 | Excel 导出 |
| jspdf | ^2.5.1 | PDF 导出 |
| html2canvas | ^1.4.1 | DOM 截图（PDF 导出辅助） |

**开发依赖：**

| 依赖 | 版本 | 用途 |
|------|------|------|
| @vitejs/plugin-vue | ^5.0.0 | Vite Vue 插件 |
| vite | ^5.4.0 | 构建工具 |

### 7.3 外部服务依赖

- **Ollama**：本地大模型推理服务，需拉取 `qwen2.5:14b` 模型
- **NVIDIA GPU + NVIDIA Container Toolkit**：14B 模型推理需 16GB 显存（推荐 RTX 5070+）

### 7.4 模块间依赖关系图

```
main.py ──► database.py (engine, get_db, Base)
        ──► models.py    (SaleRecord)
        ──► schemas.py   (SaleCreate, SaleOut, DailySummary)
        ──► crud.py      (create_sale, get_daily_summary, ...)
        ──► ai_service.py (generate_advice)

crud.py ──► models.py (SaleRecord)
ai_service.py ──► LangChain / Ollama (外部)

前端:
App.vue ──► router ──► Dashboard.vue / Import.vue
所有视图 ──► api/index.js ──► axios ──► 后端 API
Dashboard.vue ──► echarts / xlsx / jspdf / html2canvas
```

---

## 8. API 接口说明

| 方法 | 路径 | 入参 | 返回 | 说明 |
|------|------|------|------|------|
| POST | `/upload` | `file`（multipart） | `{message: "成功导入 N 条记录"}` | 上传 Excel/CSV，逐行解析入库；仅支持 `.xlsx/.csv` |
| GET | `/summary/{query_date}` | 路径参数 `query_date`（date） | DailySummary dict | 当日销售汇总；无数据返回 404 |
| GET | `/advice/{query_date}` | 路径参数 `query_date`（date） | `{date, suggestions: [...]}` | 当日 AI 运营建议；无数据返回 404 |
| GET | `/dates` | 无 | `list[date]` | 最近 30 个有数据的日期 |

**上传文件期望列格式：**

| 列名 | 类型 | 说明 |
|------|------|------|
| `date` | 日期 | 销售日期 |
| `product_name` | 字符串 | 商品名称 |
| `category` | 字符串 | 品类 |
| `unit_price` | 数值 | 售价 |
| `cost_price` | 数值 | 成本价 |
| `quantity` | 整数 | 销售数量 |

> 上传时单行解析失败会被静默跳过（`except: continue`），不影响其他行导入。

---

## 9. 数据模型与流转

### 9.1 数据流转链路

```
POS 系统导出 Excel/CSV
        │
        ▼
前端 Import.vue (el-upload)
        │  multipart/form-data
        ▼
POST /upload (main.py)
        │  pandas 解析
        ▼
crud.create_sale()  ──计算──►  total_sales, profit
        │  写入
        ▼
SQLite mall_sales.db (sales 表)
        │
        ├─► GET /summary/{date}  ──► crud.get_daily_summary()  ──► Dashboard 图表
        │
        └─► GET /advice/{date}   ──► crud.get_daily_summary()
                                       + crud.get_category_summary()
                                       ──► ai_service.generate_advice()
                                       ──► Ollama qwen2.5:14b
                                       ──► JSON 建议列表 ──► Dashboard 展示
```

### 9.2 关键派生字段计算

- `total_sales = unit_price × quantity`（入库时由 `create_sale` 计算）
- `profit = (unit_price − cost_price) × quantity`（入库时计算）
- 日毛利率 `margin = (总销售额 − 总成本) / 总销售额 × 100`（查询时由 `get_daily_summary` 计算）

---

## 10. 项目运行方式

### 10.1 方式一：Docker Compose 一键部署（生产推荐）

**前置条件：** Linux 服务器 + NVIDIA GPU + Docker + NVIDIA Container Toolkit

```bash
# 1. 安装 Docker（Ubuntu 示例）
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 2. 安装 NVIDIA Container Toolkit
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker

# 3. 启动全部服务
docker-compose up -d
```

启动后：

- 前端：`http://localhost`（80 端口）
- 后端：`http://localhost:8000`
- Ollama：`http://localhost:11434`（首次启动会自动拉取 `qwen2.5:14b` 模型）

### 10.2 方式二：本地开发模式

**后端开发：**

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

> 本地开发时 `ai_service.py` 中 `base_url="http://ollama:11434"` 需改为 `http://localhost:11434`，或单独运行 Ollama 服务。

**前端开发：**

```bash
cd frontend
npm install
npm run dev
```

Vite 启动后默认 `http://localhost:5173`，`/api` 请求自动代理至 `http://localhost:8000`。

### 10.3 数据库初始化

- **自动建表：** 后端启动时 `main.py` 会执行 `Base.metadata.create_all`，无需手动建表
- **手动建表：** 在项目根目录执行 `python -m backend.init_db`（注意导入路径需带 `backend.` 前缀）

---

## 11. 部署架构（Docker Compose）

`docker-compose.yml` 定义 3 个服务 + 1 个数据卷：

| 服务 | 镜像 | 端口 | 依赖 | 说明 |
|------|------|------|------|------|
| `ollama` | `ollama/ollama:latest` | 11434 | — | GPU 推理，启用 `nvidia` runtime；启动时自动 `ollama pull qwen2.5:14b` |
| `backend` | 构建 `./backend` | 8000 | `ollama` | FastAPI 服务；挂载 `mall_sales.db` 持久化数据 |
| `frontend` | 构建 `./frontend` | 80 | `backend` | Nginx 托管 Vue 静态站点 |

**数据卷：** `ollama_data` 持久化 Ollama 模型文件至 `/root/.ollama`，避免重复拉取模型。

**Ollama 容器 entrypoint 逻辑：**

```
ollama serve &            # 启动推理服务（后台）
sleep 5                   # 等待服务就绪
ollama pull qwen2.5:14b   # 拉取模型
tail -f /dev/null         # 保持容器运行
```

---

## 12. 已知设计要点与注意事项

| 要点 | 说明 |
|------|------|
| CORS 全开放 | `allow_origins=["*"]`，适合内网/开发，公网部署需收紧 |
| SQLite 单文件 | 通过 volume 挂载持久化；高并发场景需考虑迁移至 PostgreSQL |
| 上传静默跳过 | `/upload` 单行解析失败 `continue` 跳过，不返回失败明细 |
| 导入路径不一致 | `init_db.py` 使用 `backend.` 前缀导入，`main.py` 无前缀，运行目录不同 |
| Pinia 未启用 | `package.json` 声明了 pinia，但 `main.js` 未注册，状态管理尚未使用 |
| AI 连接地址硬编码 | `ai_service.py` 中 `base_url="http://ollama:11434"` 为 Docker 服务名，本地开发需调整 |
| 无环境变量配置 | 数据库路径、模型名、端口等均硬编码，未抽离为配置项 |
| 无认证机制 | API 无鉴权，依赖网络隔离保障安全 |

---

*本文档基于仓库当前代码生成，后续代码变更请同步更新。*
