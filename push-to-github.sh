#!/bin/bash

# 🌌 智能论文阅读宇宙 - GitHub推送脚本
# 将整个services目录推送到GitHub仓库

set -e  # 遇到错误立即退出

echo "🚀 开始推送到GitHub仓库..."

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检查是否在正确的目录
if [ ! -f "README.md" ]; then
    echo -e "${RED}❌ 错误：请在services目录下运行此脚本${NC}"
    exit 1
fi

# 检查git是否已初始化
if [ ! -d ".git" ]; then
    echo -e "${BLUE}📦 初始化Git仓库...${NC}"
    git init
    git branch -M main
fi

# 检查远程仓库
REMOTE_URL="https://github.com/vellysmallwhite/smartAIPaperReaderUniverse.git"
if ! git remote get-url origin >/dev/null 2>&1; then
    echo -e "${BLUE}🔗 添加远程仓库...${NC}"
    git remote add origin $REMOTE_URL
else
    # 更新远程仓库URL
    git remote set-url origin $REMOTE_URL
fi

# 检查.gitignore是否存在
if [ ! -f ".gitignore" ]; then
    echo -e "${YELLOW}⚠️  警告：.gitignore文件不存在${NC}"
fi

# 显示将要提交的文件
echo -e "${BLUE}📄 将要提交的文件：${NC}"
git add . --dry-run

echo -e "${YELLOW}⚠️  确认提交? (y/N)${NC}"
read -r response
if [[ ! "$response" =~ ^[Yy]$ ]]; then
    echo -e "${RED}❌ 操作已取消${NC}"
    exit 1
fi

# 添加所有文件到暂存区
echo -e "${BLUE}📦 添加文件到暂存区...${NC}"
git add .

# 检查是否有文件要提交
if git diff --cached --quiet; then
    echo -e "${YELLOW}⚠️  没有需要提交的更改${NC}"
    exit 0
fi

# 提交更改
COMMIT_MESSAGE="🌌 智能论文阅读宇宙 - $(date '+%Y-%m-%d %H:%M:%S')

✨ 功能特性:
- 🤖 AI驱动的论文分析和智能摘要
- 🕸️ 基于引用的知识图谱构建
- 🎨 交互式3D可视化界面
- 🔍 多模态RAG检索系统
- 📊 每日自动论文抓取
- 🚀 高性能物理引擎和边界约束
- 💡 悬停工具提示和智能导航

🛠️ 技术栈:
- Backend: Python + FastAPI + LangGraph
- Frontend: Next.js + React + D3.js
- Database: Neo4j + Qdrant
- AI: Groq LLM + Multi-modal Embeddings"

echo -e "${BLUE}💾 提交更改...${NC}"
git commit -m "$COMMIT_MESSAGE"

# 推送到GitHub
echo -e "${BLUE}🚀 推送到GitHub...${NC}"
git push -u origin main

echo -e "${GREEN}✅ 成功推送到GitHub！${NC}"
echo -e "${GREEN}📁 仓库地址: ${REMOTE_URL}${NC}"
echo -e "${BLUE}🌐 在线查看: https://github.com/vellysmallwhite/smartAIPaperReaderUniverse${NC}"

# 显示推送统计
echo -e "${BLUE}📊 推送统计:${NC}"
git log --oneline -5 --graph --all
