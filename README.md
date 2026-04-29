# AlphaTrader - AI Agent 自动化交易平台

基于大语言模型的智能量化交易系统，支持多 AI 模型适配、多券商对接、模拟/实盘交易。

## 架构概览

```
                         +------------------+
                         |   React Frontend  |
                         |   (Port 3000)     |
                         +--------+---------+
                                  |
                         Nginx Reverse Proxy
                                  |
                         +--------+---------+
                         |  FastAPI Backend  |
                         |   (Port 8000)     |
                         +--------+---------+
                                  |
              +-------------------+-------------------+
              |          |          |          |        |
        +-----+---+ +---+----+ +--+-----+ +--+----+ +-+-----+
        | Trading | | AI     | | Account| | Log   | |Config |
        | Engine  | | Agent  | | Service| | Service| |API    |
        +---------+ +--------+ +--------+ +-------+ +-------+
              |          |
        +-----+---+ +---+----+
        | Broker  | | Market |
        | Adapters| | Data   |
        +---------+ +--------+
              |          |
        +-----+---+ +---+----+
        | Futu/   | | Yahoo/ |
        | Tiger/  | | Tushare|
        | Huobi   | | Binance|
        +---------+ +--------+

        +---------+ +---------+
        |PostgreSQL| |  Redis  |
        | (Port    | | (Port   |
        |  5432)   | |  6379)  |
        +---------+ +---------+
```

## 快速启动 (Docker Compose)

```bash
# 1. 克隆项目
git clone <repo-url> alphatrader
cd alphatrader

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key 等配置

# 3. 启动所有服务
cd docker
docker-compose up -d

# 4. 查看日志
docker-compose logs -f

# 5. 停止服务
docker-compose down
```

启动后可访问:
- 前端界面: http://localhost:3000
- API 文档 (Swagger): http://localhost:8000/docs
- API 文档 (ReDoc): http://localhost:8000/redoc
- 健康检查: http://localhost:8000/health

## 开发环境设置

### 后端

```bash
# 安装依赖
pip install -r requirements.txt

# 或使用 pyproject.toml
pip install -e ".[dev]"

# 启动开发服务器 (热重载)
cd backend
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

### 运行测试

```bash
pytest tests/ -v
```

## API 文档

启动后端服务后，访问以下地址获取完整 API 文档:

| 文档类型 | 地址 |
|---------|------|
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| OpenAPI JSON | http://localhost:8000/openapi.json |

### 认证 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 注册新用户 |
| POST | `/api/v1/auth/login` | 用户登录，获取 JWT 令牌 |
| POST | `/api/v1/auth/refresh` | 刷新访问令牌 |
| GET | `/api/v1/auth/me` | 获取当前用户信息 |

## 环境变量

| 变量名 | 说明 | 默认值 | 必填 |
|--------|------|--------|------|
| `DATABASE_URL` | 数据库连接字符串 | `sqlite+aiosqlite:///./data/alphatrader.db` | 否 |
| `SECRET_KEY` | JWT 签名密钥 | `dev-secret-key-change-in-production` | 是 |
| `ENCRYPTION_KEY` | 数据加密密钥 | `dev-encryption-key-change-in-production` | 是 |
| `TRADING_MODE` | 交易模式 (paper/live/backtest) | `paper` | 否 |
| `DEBUG` | 调试模式 | `false` | 否 |
| `LOG_LEVEL` | 日志级别 | `INFO` | 否 |
| `API_HOST` | API 服务监听地址 | `0.0.0.0` | 否 |
| `API_PORT` | API 服务端口 | `8000` | 否 |
| `API_KEY_ENABLED` | 是否启用 API Key 认证 | `true` | 否 |
| `REDIS_URL` | Redis 连接字符串 | `redis://localhost:6379/0` | 否 |
| `REDIS_ENABLED` | 是否启用 Redis | `false` | 否 |
| `OPENAI_API_KEY` | OpenAI API Key | - | 否 |
| `ANTHROPIC_API_KEY` | Anthropic API Key | - | 否 |
| `DASHSCOPE_API_KEY` | 通义千问 API Key | - | 否 |
| `BROKER_DEFAULT` | 默认券商 | `simulated` | 否 |

完整环境变量列表请参考 `.env.example` 文件。

## 项目结构

```
alphatrader/
├── backend/                 # 后端 Python 代码
│   ├── adapters/            # 外部服务适配器
│   │   ├── ai_models/       # AI 模型适配器 (OpenAI, Claude, Qwen 等)
│   │   ├── brokers/         # 券商适配器 (富途, 老虎, 火币)
│   │   └── market_data/     # 行情数据适配器 (Yahoo, Tushare, Binance)
│   ├── api/                 # API 层
│   │   ├── routes/          # 路由模块
│   │   ├── schemas/         # 请求/响应模型
│   │   ├── auth.py          # JWT 认证模块
│   │   └── main.py          # FastAPI 应用入口
│   ├── core/                # 核心引擎
│   ├── database/            # 数据库层
│   ├── models/              # 数据模型
│   ├── services/            # 业务服务层
│   └── utils/               # 工具模块
├── frontend/                # React 前端
├── config/                  # 配置文件
├── tests/                   # 测试
├── docker/                  # Docker 部署配置
│   ├── docker-compose.yaml
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── .dockerignore
├── .env                     # 环境变量 (不提交到 Git)
├── .env.example             # 环境变量示例
├── requirements.txt         # Python 依赖
└── pyproject.toml           # 项目元数据
```

## 技术栈

- **后端**: Python 3.11, FastAPI, SQLAlchemy (async), Pydantic
- **前端**: React 18, TypeScript, Ant Design, ECharts, Zustand
- **AI**: OpenAI, Anthropic Claude, 通义千问, 豆包, MiniMax, 智谱 GLM, 千帆, Moonshot, Ollama
- **数据库**: PostgreSQL 16, SQLite (开发), Redis 7
- **部署**: Docker, Docker Compose, Nginx
- **认证**: JWT (python-jose), bcrypt (passlib)

## License

MIT
