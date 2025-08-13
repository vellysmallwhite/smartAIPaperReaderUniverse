# 前端Dockerfile - Next.js应用
FROM node:18-alpine AS base

# 安装依赖阶段
FROM base AS deps
WORKDIR /app

# 复制包管理文件
COPY package.json package-lock.json* ./

# 安装依赖
RUN npm ci --only=production && npm cache clean --force

# 构建阶段
FROM base AS builder
WORKDIR /app

# 复制依赖
COPY --from=deps /app/node_modules ./node_modules
# 复制源代码
COPY . .

# 构建应用
RUN npm run build

# 生产运行阶段
FROM base AS runner
WORKDIR /app

ENV NODE_ENV production

# 创建nextjs用户
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# 复制构建产物
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

CMD ["node", "server.js"]
