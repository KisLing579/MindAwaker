#!/usr/bin/env python3
"""
启动脚本 - 统一入口
用法: python start.py [--reload] [--port PORT]
"""
import argparse
import uvicorn
import os
from pathlib import Path

# 确保 cache 目录存在
def setup_directories():
    """创建必要的目录"""
    base_dir = Path(__file__).parent
    dirs = [
        base_dir / "cache" / "huggingface",
        base_dir / "app" / "assets" / "projects",
        base_dir / "app" / "assets" / "temp",
        base_dir / "app" / "assets" / "voices",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"✓ 确保目录存在: {d}")

def main():
    parser = argparse.ArgumentParser(description="启动 Mindawaker 后端服务")
    parser.add_argument("--reload", action="store_true", help="启用热重载 (开发模式)")
    parser.add_argument("--port", type=int, default=8000, help="服务端口 (默认: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    args = parser.parse_args()

    print("=" * 50)
    print("🚀 Mindawaker 启动中...")
    print("=" * 50)

    setup_directories()

    # 加载环境变量
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ 加载环境变量: {env_path}")
    else:
        print("⚠ 未找到 .env 文件，使用默认配置")
        print("  建议: cp .env.example .env 并配置你的 API 密钥")

    print("-" * 50)
    print(f"📡 服务地址: http://{args.host}:{args.port}")
    print(f"📚 API 文档: http://{args.host}:{args.port}/docs")
    print("-" * 50)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )

if __name__ == "__main__":
    main()
