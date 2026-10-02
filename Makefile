# Mindawaker 项目管理
.PHONY: help install dev test format lint clean run

# 默认显示帮助
help:
	@echo "Mindawaker 项目管理命令:"
	@echo ""
	@echo "  make install    - 安装依赖"
	@echo "  make dev        - 安装开发依赖"
	@echo "  make test       - 运行测试"
	@echo "  make format     - 格式化代码 (black + ruff)"
	@echo "  make lint       - 代码检查 (ruff + mypy)"
	@echo "  make clean      - 清理缓存文件"
	@echo "  make run        - 启动服务"
	@echo ""

# 安装依赖
install:
	pip install -r requirements.txt

# 安装开发依赖
dev:
	pip install -r requirements.txt
	pip install black ruff mypy pytest pytest-asyncio httpx

# 运行测试
test:
	pytest tests/ -v --tb=short

# 格式化代码
format:
	black app/ tests/ --line-length 100
	ruff check app/ tests/ --fix

# 代码检查
lint:
	ruff check app/ tests/
	mypy app/ --ignore-missing-imports

# 清理缓存文件
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +

# 启动服务
run:
	python start.py --reload

# 生产环境启动
run-prod:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
