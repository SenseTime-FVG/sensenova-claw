# 部署指南

## 本地开发部署

### 快速启动

**一键启动脚本** (`start.sh`):
```bash
#!/bin/bash

# 检查配置文件
if [ ! -f ~/.SenseAssistant/config.yaml ]; then
    echo "配置文件不存在，正在创建..."
    mkdir -p ~/.SenseAssistant
    cp config.example.yaml ~/.SenseAssistant/config.yaml
    echo "请编辑 ~/.SenseAssistant/config.yaml 填入 API Keys"
    exit 1
fi

# 启动后端
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# 启动前端
cd ../frontend
npm run dev &
FRONTEND_PID=$!

echo "AgentOS 已启动"
echo "后端: http://localhost:8000"
echo "前端: http://localhost:3000"
echo "按 Ctrl+C 停止服务"

# 等待中断信号
trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
```

### 手动启动

**终端 1 - 后端**:
```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**终端 2 - 前端**:
```bash
cd frontend
npm run dev
```

## 监控和日志

### 日志配置

**后端日志** (`backend/logging_config.py`):
```python
import logging
from pathlib import Path

def setup_logging():
    log_dir = Path.home() / ".SenseAssistant" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "system.log"),
            logging.StreamHandler()
        ]
    )
```

### 健康检查

**后端健康检查端点**:
```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "0.1.0"
    }
```

## 备份策略

### 数据库备份

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR=~/.SenseAssistant/backups
mkdir -p $BACKUP_DIR

DATE=$(date +%Y%m%d_%H%M%S)
sqlite3 ~/.SenseAssistant/agentos.db ".backup $BACKUP_DIR/agentos_$DATE.db"

# 保留最近 7 天的备份
find $BACKUP_DIR -name "agentos_*.db" -mtime +7 -delete
```

添加到 crontab:
```bash
0 2 * * * /path/to/backup.sh
```
