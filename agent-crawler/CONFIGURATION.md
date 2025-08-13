# DigitalPaperAgent 配置说明

## 环境变量配置

### API 配置（必需）
```bash
# GROQ API Key（必需）
GROQ_API_KEY=your_groq_api_key_here

# 可选：如果使用 OpenAI 作为后备
OPENAI_API_KEY=your_openai_api_key_here
```

### 数据库配置
```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j_password
QDRANT_URL=http://localhost:6333
```

### 模型配置
```bash
# 使用的语言模型（默认：openai/gpt-oss-20b）
MODEL_NAME=openai/gpt-oss-20b
```

### 每日抓取配置
```bash
# 每日抓取论文数量（默认：8）
DAILY_PAPER_COUNT=8

# 智能模式：启用递归引用处理（默认：true）
DAILY_SMART_MODE=true

# 定时任务执行时间（默认：10:00）
DAILY_SCHEDULE_TIME=10:00
```

## 🔧 并发处理配置

### 基本配置
```bash
# 是否启用并发处理（默认：false，避免API rate limit）
ENABLE_CONCURRENT_PROCESSING=false

# 并发线程数（默认：3，仅在启用并发时生效）
MAX_CONCURRENT_WORKERS=3
```

### 资源限制
```bash
# 最大图片处理数量（默认：30）
MAX_IMAGE_CHUNKS=30
```

## 📊 并发模式对比

| 模式 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **顺序处理** | - 安全稳定<br>- 避免 rate limit<br>- 资源消耗低 | - 处理速度较慢 | - 日常使用<br>- API 配额有限<br>- 稳定性优先 |
| **并发处理** | - 3-5倍速度提升<br>- 高效资源利用 | - 可能触发 rate limit<br>- 资源消耗高 | - 大批量处理<br>- API 配额充足<br>- 效率优先 |

## 🚀 如何启用并发处理

### 前提条件
1. 确保有足够的 GROQ API 配额
2. 系统资源充足（内存、网络）

### 配置步骤
1. 设置环境变量：
   ```bash
   export ENABLE_CONCURRENT_PROCESSING=true
   export MAX_CONCURRENT_WORKERS=3
   ```

2. 或在 `.env` 文件中：
   ```
   ENABLE_CONCURRENT_PROCESSING=true
   MAX_CONCURRENT_WORKERS=3
   ```

### 推荐配置
- **小规模处理**（1-5篇论文）：顺序模式
- **中等规模处理**（5-20篇论文）：2-3个并发线程
- **大规模处理**（20+篇论文）：考虑分批处理

## ⚠️ 注意事项

### API Rate Limit
- GROQ 免费版：200,000 tokens/day
- 并发处理会快速消耗配额
- 建议监控 API 使用量

### 错误处理
- 系统自动回退到基础模式
- 单个论文失败不影响整体
- 向量库超时不影响图数据库

### 性能优化
- 图片数量限制：`MAX_IMAGE_CHUNKS=10-30`
- 智能模式递归深度：默认1层
- 超时设置：PDF下载60秒，向量库60秒

## 🔍 测试命令

### 测试顺序处理
```bash
python test_concurrent_processing.py
```

### 测试并发处理
```bash
export ENABLE_CONCURRENT_PROCESSING=true
python test_concurrent_processing.py
```

### 测试日常抓取
```bash
python cli.py fetch-daily --max-papers 3
```
