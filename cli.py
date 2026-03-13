#!/usr/bin/env python3
"""AgentOS CLI 入口"""
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentos.app.cli.cli_client import main

if __name__ == "__main__":
    main()
