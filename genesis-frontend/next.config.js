/** @type {import('next').NextConfig} */
const nextConfig = {
  // 启用standalone输出用于Docker部署
  output: 'standalone',
  
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: process.env.NODE_ENV === 'production' 
          ? `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'}/api/:path*`
          : 'http://127.0.0.1:8080/api/:path*'
      }
    ]
  },
  
  // 性能优化
  compress: true,
  poweredByHeader: false,
  
  // 生产环境优化
  experimental: {
    optimizeCss: true,
  }
}

module.exports = nextConfig
