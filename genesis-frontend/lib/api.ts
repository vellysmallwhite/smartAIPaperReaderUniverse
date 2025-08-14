import { GraphData, PaperDetail } from './store'

// API配置：生产环境直接连接外部API，开发环境使用本地代理
const API_BASE = process.env.NODE_ENV === 'production' 
  ? process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080'
  : ''

// Fetch helper with error handling and timeout
const fetchWithTimeout = async (url: string, options: RequestInit = {}, timeout = 10000) => {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    })
    
    clearTimeout(timeoutId)
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    
    return response
  } catch (error) {
    clearTimeout(timeoutId)
    console.error('API fetch error:', error)
    throw error
  }
}

export const api = {
  async getGraphDaily(): Promise<GraphData> {
    const response = await fetchWithTimeout(`${API_BASE}/api/graph/daily`)
    return response.json()
  },

  async expandNode(arxivId: string): Promise<GraphData> {
    const response = await fetchWithTimeout(`${API_BASE}/api/graph/expand/${arxivId}`)
    return response.json()
  },

  async getPaperDetail(arxivId: string): Promise<PaperDetail> {
    const response = await fetchWithTimeout(`${API_BASE}/api/papers/${arxivId}/detail`)
    return response.json()
  },

  async getPaperInsight(arxivId: string): Promise<{ arxiv_id: string; insight: string }> {
    const response = await fetchWithTimeout(`${API_BASE}/api/papers/${arxivId}/insight`, {}, 30000) // 30s timeout for AI generation
    return response.json()
  },

  // Health check endpoint
  async healthCheck(): Promise<{ status: string }> {
    const response = await fetchWithTimeout(`${API_BASE}/health`, {}, 5000)
    return response.json()
  }
}
