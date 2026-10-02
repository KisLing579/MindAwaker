# Mindawaker Studio

## 模型凭据配置

模型密钥仅从后端环境变量读取，不再在网页填写或通过系统设置保存。
复制根目录 `.env.example` 为 `.env`，按所选服务填写以下变量，然后重启后端。
系统环境变量优先于 `.env`，不要给这些变量添加 `NEXT_PUBLIC_` 前缀。

| 模型 / 服务 | 后端环境变量 |
| --- | --- |
| DeepSeek 文本 | `DEEPSEEK_API_KEY` |
| GPT 文本 | `OPENAI_API_KEY` |
| Claude 文本 | `ANTHROPIC_API_KEY` |
| Gemini 文本 | `GOOGLE_API_KEY` |
| Azure TTS | `AZURE_SPEECH_KEY`、`AZURE_SPEECH_REGION` |
| Flux 图像 | `FLUX_API_KEY` |
| 火山引擎 / 即梦图像 | `VOLC_ACCESS_KEY`、`VOLC_SECRET_KEY`；业务标识 `VOLC_REQ_KEY` 默认 `jimeng_t2i_v40` |
| 原 image model 密码框 | `IMAGE_MODEL_PASSWORD`，作为未配置服务专用密钥时的兼容输入 |

只需填写实际使用的服务。缺少必要密钥时，后端会提示对应环境变量名。
旧请求和旧项目中的模型密钥会被忽略，项目重新保存时清空旧密钥字段。
火山引擎优先使用独立的 `VOLC_ACCESS_KEY` 和 `VOLC_SECRET_KEY`。
也可以将旧 image model 密码框的 `AccessKey**SecretKey` 值填入 `IMAGE_MODEL_PASSWORD`，并将上述两个独立变量留空。
Flux 则优先使用 `FLUX_API_KEY`，未填写时读取 `IMAGE_MODEL_PASSWORD`。
当前火山 SDK 使用 AK/SK 签名，密码框不是第三种独立认证参数；`VOLC_REQ_KEY` 是业务标识。

端到端 AI 视频生成系统，提供视频、文本、音频和图像生成。
“视频检索生成”和“3D GUIDED”独立模块及其入口已移除。

## 项目结构

| 子项目 | 说明 | 核心技术 |
|--------|------|---------|
| `app/` + `mindawaker-web/` | **Mindawaker** 主应用 | FastAPI + Next.js + LangChain + FFmpeg |

## ✨ 核心能力

- **叙事一致性**: LLM 三阶段解析（角色→场景→镜头），结构化 prompt 注入
- **全链路合成**: 文本 → TTS 音频 → 图像生成 → FFmpeg 多轨合成

## 🚀 快速开始
apt-get install ffmpeg
apt-get install npm
### 1. 克隆项目

```bash
git clone <repository-url>
cd mindawaker
```

### 2. 配置环境

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的 API 密钥
```

### 3. 启动后端

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python start.py --reload

# 或使用 make
make run
```

后端服务将运行在 http://localhost:8000

API 文档: http://localhost:8000/docs

### 4. 启动前端

```bash
cd mindawaker-web

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端将运行在 http://localhost:3000

## 🧪 测试

```bash
# 运行所有测试
pytest tests/ -v

# 或使用 make
make test
```

## 🎨 代码格式化

```bash
# 格式化代码
black app/ tests/ --line-length 100
ruff check app/ tests/ --fix

# 代码检查
ruff check app/ tests/
mypy app/ --ignore-missing-imports

# 或使用 make
make format
make lint
```

## 📁 项目结构

```
mindawaker/
├── app/                      # 后端应用
│   ├── config/              # 配置文件
│   │   ├── logging_config.py    # 日志配置
│   │   ├── exceptions.py        # 异常处理
│   │   ├── paths.py             # 路径配置
│   │   └── settings.py          # 设置配置
│   ├── model/               # 数据模型 (Pydantic)
│   ├── router/              # API 路由
│   ├── service/             # 业务逻辑
│   │   ├── task_manager.py      # 任务管理器
│   │   ├── video_job.py         # 视频生成任务
│   │   └── ...
│   ├── tts_engine/          # TTS 引擎
│   ├── image_engine/        # 图像生成引擎
│   ├── langchain_pipeline/  # LangChain 管道
│   └── main.py              # 应用入口
├── mindawaker-web/          # React 前端
│   ├── src/
│   │   ├── app/             # Next.js 应用
│   │   ├── components/      # React 组件
│   │   ├── hooks/           # 自定义 Hooks
│   │   └── lib/             # 工具函数
│   └── package.json
├── tests/                   # 单元测试
├── requirements.txt         # Python 依赖
├── pyproject.toml          # Python 项目配置
├── Makefile                # 常用命令
└── start.py                # 启动脚本
```

## 🔌 API 接口

### 视频生成

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/video/compose` | 创建视频任务 |
| POST | `/video/cancel/{task_id}` | 取消任务 |
| GET | `/video/task/{task_id}` | 获取任务状态 |
| WS | `/video/ws/{task_id}` | WebSocket 实时进度 |

### 项目管理

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/project/create` | 创建项目 |
| POST | `/project/save` | 保存项目 |
| POST | `/project/load` | 加载项目 |

## 📝 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CORS_ORIGINS` | 允许的跨域域名 | `http://localhost:3000` |
| `HF_HOME` | HuggingFace 缓存路径 | `./cache/huggingface` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `LOG_DIR` | 日志目录 | `app/assets/logs` |

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License
