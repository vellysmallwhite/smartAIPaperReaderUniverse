/** @type {import('next').NextConfig} */
const nextConfig = {
  // Netlify 部署使用 export 模式
  output: 'export',
  trailingSlash: true,
  images: {
    unoptimized: true
  },
  
  // 环境变量配置
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
  },
  
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: process.env.NODE_ENV === 'production' 
          ? `${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080'}/api/:path*`
          : 'http://127.0.0.1:8080/api/:path*'
      }
    ]
  },
  
  // 性能优化
  compress: true,
  poweredByHeader: false,
  
  // 生产环境优化
  experimental: {}
}

module.exports = nextConfig
