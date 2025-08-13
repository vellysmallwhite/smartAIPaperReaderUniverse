# 🚀 部署指南

## 📋 系统要求

### 最低配置
- **CPU**: 2核心
- **内存**: 4GB RAM
- **存储**: 10GB 可用空间
- **网络**: 稳定的互联网连接

### 推荐配置
- **CPU**: 4核心
- **内存**: 8GB RAM
- **存储**: 20GB+ SSD
- **GPU**: 可选，用于加速AI推理

## 🐳 Docker部署 (推荐)

### 1. 构建镜像
```bash
# 构建后端镜像
cd agent-crawler
docker build -t smart-paper-reader-backend .

# 构建前端镜像 (如需要)
cd ../genesis-frontend
docker build -t smart-paper-reader-frontend .
```

### 2. 使用Docker Compose
```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

## 🖥️ 本地开发部署

### 1. 环境准备
```bash
# 克隆项目
git clone https://github.com/vellysmallwhite/smartAIPaperReaderUniverse.git
cd smartAIPaperReaderUniverse

# 安装Node.js依赖
cd genesis-frontend
npm install

# 安装Python依赖
cd ../agent-crawler
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量
```bash
# 复制配置模板
cp ../config.example.env .env

# 编辑配置文件
nano .env  # 或使用其他编辑器
```

### 3. 启动数据库
```bash
# 启动Neo4j和Qdrant
docker-compose up -d neo4j qdrant
```

### 4. 启动服务
```bash
# 启动后端API (终端1)
python -m uvicorn server.main:app --host 0.0.0.0 --port 8080

# 启动前端 (终端2)
cd ../genesis-frontend
npm run dev

# 启动调度器 (终端3，可选)
cd ../agent-crawler
python daily_scheduler.py daemon
```

## ☁️ 云部署

### AWS部署
```bash
# 使用AWS ECS部署
aws ecs create-cluster --cluster-name smart-paper-reader

# 部署任务定义
aws ecs register-task-definition --cli-input-json file://aws-task-definition.json
```

### Google Cloud部署
```bash
# 使用Google Cloud Run
gcloud run deploy smart-paper-reader-backend \
  --image gcr.io/PROJECT-ID/smart-paper-reader-backend \
  --platform managed \
  --region us-central1
```

### Azure部署
```bash
# 使用Azure Container Instances
az container create \
  --resource-group myResourceGroup \
  --name smart-paper-reader \
  --image smart-paper-reader-backend
```

## 🔧 配置详解

### 数据库配置
```yaml
# docker-compose.yml
services:
  neo4j:
    image: neo4j:5.22
    environment:
      - NEO4J_AUTH=neo4j/your_secure_password
      - NEO4J_dbms_memory_heap_initial__size=512m
      - NEO4J_dbms_memory_heap_max__size=2G
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

  qdrant:
    image: qdrant/qdrant:v1.11.0
    environment:
      - QDRANT__SERVICE__HTTP_PORT=6333
      - QDRANT__SERVICE__GRPC_PORT=6334
    volumes:
      - qdrant_data:/qdrant/storage
```

### Nginx反向代理
```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 后端API
    location /api/ {
        proxy_pass http://localhost:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 📊 监控与日志

### 健康检查
```bash
# 检查服务状态
curl http://localhost:8080/health
curl http://localhost:3000

# 检查数据库连接
curl http://localhost:7474/db/data/
curl http://localhost:6333/dashboard/
```

### 日志管理
```bash
# 查看应用日志
tail -f agent-crawler/server.log
tail -f agent-crawler/daily_scheduler.log

# 查看Docker日志
docker-compose logs -f backend
docker-compose logs -f frontend
```

### 性能监控
```bash
# 系统资源监控
htop
df -h
free -h

# 数据库性能
docker exec neo4j cypher-shell -u neo4j -p password "CALL db.stats.retrieve('GRAPH COUNTS')"
```

## 🔒 安全配置

### 环境变量安全
```bash
# 生产环境建议使用密钥管理服务
export GROQ_API_KEY=$(aws ssm get-parameter --name "/app/groq-api-key" --with-decryption --query "Parameter.Value" --output text)
```

### 网络安全
```yaml
# docker-compose.yml 网络隔离
networks:
  internal:
    driver: bridge
    internal: true
  external:
    driver: bridge

services:
  backend:
    networks:
      - internal
      - external
  
  neo4j:
    networks:
      - internal
```

## 🔄 备份与恢复

### 数据备份
```bash
# Neo4j备份
docker exec neo4j neo4j-admin dump --database=neo4j --to=/var/backups/neo4j-backup.dump

# Qdrant备份
docker exec qdrant qdrant-backup --source /qdrant/storage --destination /backups/
```

### 数据恢复
```bash
# Neo4j恢复
docker exec neo4j neo4j-admin load --from=/var/backups/neo4j-backup.dump --database=neo4j --force

# Qdrant恢复
docker exec qdrant qdrant-restore --source /backups/ --destination /qdrant/storage
```

## 🚦 故障排除

### 常见问题

#### 1. 端口冲突
```bash
# 查看端口占用
lsof -i :3000
lsof -i :8080
lsof -i :7474
lsof -i :6333

# 停止占用进程
kill -9 PID
```

#### 2. 内存不足
```bash
# 检查内存使用
free -h
docker stats

# 优化配置
export NODE_OPTIONS="--max-old-space-size=4096"
```

#### 3. API密钥错误
```bash
# 验证API密钥
curl -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/openai/v1/models
```

#### 4. 数据库连接失败
```bash
# 检查数据库状态
docker-compose ps
docker-compose logs neo4j
docker-compose logs qdrant

# 重启数据库
docker-compose restart neo4j qdrant
```

### 日志分析
```bash
# 查找错误日志
grep -i error agent-crawler/server.log
grep -i "failed" agent-crawler/daily_scheduler.log

# 实时监控错误
tail -f agent-crawler/server.log | grep -i error
```

## 📈 性能优化

### 数据库优化
```cypher
// Neo4j索引优化
CREATE INDEX ON :Paper(arxiv_id);
CREATE INDEX ON :Paper(fetch_date);
CREATE FULLTEXT INDEX paperTitleIndex FOR (n:Paper) ON EACH [n.title];
```

### 应用优化
```python
# Python异步优化
import asyncio
from concurrent.futures import ThreadPoolExecutor

# 启用并发处理
ENABLE_CONCURRENT_PROCESSING=true
MAX_CONCURRENT_WORKERS=4
```

### 前端优化
```javascript
// Next.js构建优化
module.exports = {
  experimental: {
    outputStandalone: true,
  },
  compress: true,
  poweredByHeader: false,
}
```

## 📞 技术支持

遇到问题？请查看：
- [GitHub Issues](https://github.com/vellysmallwhite/smartAIPaperReaderUniverse/issues)
- [技术文档](./SMART_PIPELINE.md)
- [配置指南](./agent-crawler/CONFIGURATION.md)

---

**祝您部署顺利！** 🎉
