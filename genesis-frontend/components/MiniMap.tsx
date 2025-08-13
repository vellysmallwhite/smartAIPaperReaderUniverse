'use client'

import { useRef, useEffect, useState } from 'react'
import { useGenesisStore } from '@/lib/store'
import { motion } from 'framer-motion'

interface MiniMapProps {
  className?: string
}

export default function MiniMap({ className = '' }: MiniMapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const { graphData, hoveredNode, selectedPaper } = useGenesisStore()
  
  const [bounds, setBounds] = useState({
    minX: -100, maxX: 100, minY: -100, maxY: 100, 
    width: 200, height: 200
  })
  
  const [isVisible, setIsVisible] = useState(false)
  const [isMinimized, setIsMinimized] = useState(false)
  const [view, setView] = useState({ k: 1, tx: 0, ty: 0 })
  
  // 固定的世界地图尺寸
  const WORLD_MAP_WIDTH = 320
  const WORLD_MAP_HEIGHT = 240
  
  // 缓存过滤结果，提高性能
  const [meaningfulNodes, setMeaningfulNodes] = useState<typeof graphData.nodes>([])
  const [meaningfulLinks, setMeaningfulLinks] = useState<typeof graphData.links>([])
  
  // 计算全局世界地图的边界 - 涵盖所有有标题节点的完整范围
  useEffect(() => {
    if (graphData.nodes.length === 0) return
    
    // 过滤出有标题的节点 - 构成世界地图的基础
    const filteredNodes = graphData.nodes.filter(n => n.title && n.title.trim() !== '')
    setMeaningfulNodes(filteredNodes)
    
    if (filteredNodes.length === 0) return
    
    // 计算所有有意义节点的完整边界
    const xs = filteredNodes.map(n => n.x ?? 0).filter(x => !isNaN(x))
    const ys = filteredNodes.map(n => n.y ?? 0).filter(y => !isNaN(y))
    
    if (xs.length === 0 || ys.length === 0) return
    
    // 确保世界地图涵盖整个知识宇宙 - 终极超广角视野
    const padding = 15000 // 终极大边距，让世界地图覆盖百倍于用户视野的范围
    const minX = Math.min(...xs) - padding
    const maxX = Math.max(...xs) + padding
    const minY = Math.min(...ys) - padding
    const maxY = Math.max(...ys) + padding
    
    setBounds({
      minX, maxX, minY, maxY,
      width: maxX - minX,
      height: maxY - minY
    })
    
    // 过滤有意义的连线
    const meaningfulNodeIds = new Set(filteredNodes.map(n => n.id))
    const filteredLinks = graphData.links.filter(link => {
      const sourceId = typeof link.source === 'string' ? link.source : link.source.id
      const targetId = typeof link.target === 'string' ? link.target : link.target.id
      return meaningfulNodeIds.has(sourceId) && meaningfulNodeIds.has(targetId)
    }).slice(0, 50) // 限制连线数量，保证性能
    
    setMeaningfulLinks(filteredLinks)
    
    // 显示世界地图
    setIsVisible(filteredNodes.length > 3)
  }, [graphData.nodes, graphData.links])
  
  // 监听主视图变化
  useEffect(() => {
    const handleViewChange = (event: CustomEvent) => {
      setView(event.detail)
    }
    
    window.addEventListener('graphViewChange', handleViewChange as EventListener)
    return () => {
      window.removeEventListener('graphViewChange', handleViewChange as EventListener)
    }
  }, [])
  
  // 渲染世界地图
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !isVisible) return
    
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    
    // 使用固定的世界地图尺寸
    const mapWidth = WORLD_MAP_WIDTH
    const mapHeight = WORLD_MAP_HEIGHT
    
    // 设置高DPI
    const dpr = window.devicePixelRatio || 1
    canvas.width = mapWidth * dpr
    canvas.height = mapHeight * dpr
    canvas.style.width = `${mapWidth}px`
    canvas.style.height = `${mapHeight}px`
    ctx.scale(dpr, dpr)
    
    // 清空画布
    ctx.clearRect(0, 0, mapWidth, mapHeight)
    
    // 绘制深空背景
    const gradient = ctx.createRadialGradient(mapWidth/2, mapHeight/2, 0, mapWidth/2, mapHeight/2, Math.max(mapWidth, mapHeight)/2)
    gradient.addColorStop(0, 'rgba(8, 15, 26, 0.98)')
    gradient.addColorStop(0.7, 'rgba(0, 10, 30, 0.98)')
    gradient.addColorStop(1, 'rgba(0, 5, 15, 0.98)')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, mapWidth, mapHeight)
    
    // 绘制世界地图边框
    ctx.strokeStyle = '#00F6FF'
    ctx.lineWidth = 3
    ctx.shadowColor = '#00F6FF'
    ctx.shadowBlur = 5
    ctx.strokeRect(2, 2, mapWidth - 4, mapHeight - 4)
    ctx.shadowBlur = 0
    
    // 计算固定的比例尺 - 世界地图总是显示所有有标题的节点
    const scaleX = (mapWidth - 8) / bounds.width  // 极小内边距，最大化显示超广角视野
    const scaleY = (mapHeight - 8) / bounds.height
    const scale = Math.min(scaleX, scaleY)
    
    // 居中偏移
    const offsetX = (mapWidth - bounds.width * scale) / 2
    const offsetY = (mapHeight - bounds.height * scale) / 2
    
    // 使用缓存的过滤结果，提高渲染性能
    
    // 绘制星系网格 - 类似星图的坐标系
    ctx.strokeStyle = 'rgba(0, 246, 255, 0.08)'
    ctx.lineWidth = 0.5
    ctx.setLineDash([1, 3])
    
    // 绘制经纬网格
    for (let i = 1; i < 8; i++) {
      const x = mapWidth * i / 8
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, mapHeight)
      ctx.stroke()
    }
    
    for (let i = 1; i < 6; i++) {
      const y = mapHeight * i / 6
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(mapWidth, y)
      ctx.stroke()
    }
    ctx.setLineDash([])
    
    // 绘制有意义的连线 - 简化效果提升性能
    ctx.strokeStyle = 'rgba(0, 246, 255, 0.3)'
    ctx.lineWidth = 1
    meaningfulLinks.forEach(link => {
      const source = typeof link.source === 'string' 
        ? meaningfulNodes.find(n => n.id === link.source) 
        : link.source
      const target = typeof link.target === 'string' 
        ? meaningfulNodes.find(n => n.id === link.target) 
        : link.target
      
      if (!source || !target || source.x === undefined || source.y === undefined || 
          target.x === undefined || target.y === undefined) return
      
      const sx = offsetX + (source.x - bounds.minX) * scale
      const sy = offsetY + (source.y - bounds.minY) * scale
      const tx = offsetX + (target.x - bounds.minX) * scale
      const ty = offsetY + (target.y - bounds.minY) * scale
      
      // 简化连线效果 - 无阴影
      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(tx, ty)
      ctx.stroke()
    })
    
    // 绘制有标题的节点 - 世界地图上的星系
    meaningfulNodes.forEach(node => {
      if (node.x === undefined || node.y === undefined) return
      
      const x = offsetX + (node.x - bounds.minX) * scale
      const y = offsetY + (node.y - bounds.minY) * scale
      
      // 节点大小和颜色
      let radius = 3
      let nodeColor = '#FFFFFF'
      let glowColor = '#FFFFFF'
      
      if (node.id === selectedPaper) {
        radius = 6
        nodeColor = '#FFD700'
        glowColor = '#FFD700'
      } else if (node.id === hoveredNode) {
        radius = 5
        nodeColor = '#FF69B4'
        glowColor = '#FF69B4'
      } else if (node.type === 'today') {
        radius = 4.5
        nodeColor = '#00F6FF'
        glowColor = '#00F6FF'
      } else if (node.type === 'center') {
        radius = 4
        nodeColor = '#96CEB4'
        glowColor = '#96CEB4'
      }
      
      // 简化节点效果 - 减少渲染负担
      ctx.fillStyle = nodeColor
      ctx.beginPath()
      ctx.arc(x, y, radius, 0, Math.PI * 2)
      ctx.fill()
      
      // 绘制节点边框
      ctx.strokeStyle = nodeColor
      ctx.lineWidth = 1.5
      ctx.stroke()
      
      // 简化今日论文效果 - 减少动画提升性能
      if (node.type === 'today') {
        ctx.strokeStyle = '#00F6FF'
        ctx.lineWidth = 1.5
        ctx.beginPath()
        ctx.arc(x, y, radius + 2, 0, Math.PI * 2)
        ctx.stroke()
      }
    })
    
    // 绘制用户当前视野框 - 在全局地图中显示"望远镜"的视野范围
    
    // 1. 计算用户屏幕中心在真实图谱坐标系中的位置
    const realWorldCenterX = -view.tx / view.k
    const realWorldCenterY = -view.ty / view.k
    
    // 2. 将真实坐标转换为世界地图上的像素位置
    const viewportCenterX = offsetX + (realWorldCenterX - bounds.minX) * scale
    const viewportCenterY = offsetY + (realWorldCenterY - bounds.minY) * scale
    
    // 3. 计算用户当前视野在真实图谱中覆盖的范围
    const realViewWidth = window.innerWidth / view.k  // 真实图谱中的宽度
    const realViewHeight = window.innerHeight / view.k // 真实图谱中的高度
    
    // 4. 将真实视野大小转换为世界地图上的像素大小
    const viewportWidth = realViewWidth * scale
    const viewportHeight = realViewHeight * scale
    
    // 5. 确保视窗框在地图边界内，但保持真实比例关系
    const rectX = viewportCenterX - viewportWidth / 2
    const rectY = viewportCenterY - viewportHeight / 2
    const rectWidth = Math.max(4, viewportWidth)  // 最小4像素，保证可见
    const rectHeight = Math.max(4, viewportHeight)
    
    // 绘制视窗框 - 静态金色虚线边框（性能优化）
    ctx.strokeStyle = '#FFD700'
    ctx.lineWidth = 2
    ctx.shadowColor = '#FFD700'
    ctx.shadowBlur = 3
    
    // 静态虚线效果
    ctx.setLineDash([6, 6])
    ctx.strokeRect(rectX, rectY, rectWidth, rectHeight)
    
    // 重置
    ctx.setLineDash([])
    ctx.shadowBlur = 0
    
    // 简化角落指示器 - 提升性能
    const cornerSize = 4
    const cornerOffset = 2
    ctx.fillStyle = '#FFD700'
    
    // 左上角
    ctx.fillRect(rectX - cornerOffset, rectY - cornerOffset, cornerSize, 1)
    ctx.fillRect(rectX - cornerOffset, rectY - cornerOffset, 1, cornerSize)
    
    // 右上角  
    ctx.fillRect(rectX + rectWidth - cornerSize + cornerOffset, rectY - cornerOffset, cornerSize, 1)
    ctx.fillRect(rectX + rectWidth + cornerOffset - 1, rectY - cornerOffset, 1, cornerSize)
    
  }, [meaningfulNodes, meaningfulLinks, bounds, isVisible, view, hoveredNode, selectedPaper])
  
  // 点击世界地图瞬移 - 高精度坐标转换
  const handleMapClick = (e: React.MouseEvent) => {
    if (!canvasRef.current) return
    
    const rect = canvasRef.current.getBoundingClientRect()
    const mapWidth = WORLD_MAP_WIDTH
    const mapHeight = WORLD_MAP_HEIGHT
    
    // 获取点击在画布上的精确位置
    const clickX = e.clientX - rect.left
    const clickY = e.clientY - rect.top
    
    // 重新计算世界地图的比例关系（与渲染时保持一致）
    const scaleX = (mapWidth - 8) / bounds.width  // 与渲染时的边距保持一致
    const scaleY = (mapHeight - 8) / bounds.height
    const scale = Math.min(scaleX, scaleY)
    
    const offsetX = (mapWidth - bounds.width * scale) / 2
    const offsetY = (mapHeight - bounds.height * scale) / 2
    
    // 将点击位置从世界地图坐标转换为真实图谱坐标
    const targetRealWorldX = (clickX - offsetX) / scale + bounds.minX
    const targetRealWorldY = (clickY - offsetY) / scale + bounds.minY
    
    // 计算新的视图变换：让目标位置居中显示
    const newTx = -targetRealWorldX * view.k + window.innerWidth / 2
    const newTy = -targetRealWorldY * view.k + window.innerHeight / 2
    
    const newView = {
      k: view.k, // 保持当前缩放级别
      tx: newTx,
      ty: newTy
    }
    
    // 立即更新本地状态以提供视觉反馈
    setView(newView)
    
    // 发送瞬移事件给主画布，实现同步
    const teleportEvent = new CustomEvent('minimapTeleport', {
      detail: { 
        targetX: targetRealWorldX,
        targetY: targetRealWorldY,
        newView: newView,
        source: 'minimap'
      }
    })
    window.dispatchEvent(teleportEvent)
  }
  
  if (!isVisible) return null
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={`fixed bottom-6 right-6 z-40 ${className}`}
    >
      <div className="holographic-glass rounded-lg overflow-hidden border border-cyber-blue/50">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-4 py-2 bg-deep-space/95 border-b border-cyber-blue/40">
          <div className="flex items-center space-x-2">
            <span className="text-xs font-roboto-mono text-cyber-blue font-semibold">🌌 知识星系</span>
            <span className="text-xs text-electric-green/60">世界地图</span>
          </div>
          <div className="flex space-x-2">
            <button
              onClick={() => setIsMinimized(!isMinimized)}
              className="w-5 h-5 rounded bg-electric-green/20 hover:bg-electric-green/40 transition-colors flex items-center justify-center"
              title={isMinimized ? '展开世界地图' : '最小化'}
            >
              <span className="text-xs text-electric-green font-bold">
                {isMinimized ? '+' : '−'}
              </span>
            </button>
          </div>
        </div>
        
        {/* 世界地图内容 */}
        {!isMinimized && (
          <div className="p-3">
            <canvas
              ref={canvasRef}
              onClick={handleMapClick}
              className="cursor-crosshair border border-cyber-blue/30 rounded hover:border-cyber-blue/60 transition-colors bg-deep-space/20"
              title="点击瞬移到目标位置"
            />
            
            <div className="mt-2 text-xs text-starlight/70 font-roboto-mono">
              <div className="flex justify-between mb-1">
                <span className="text-cyber-blue">星系: {meaningfulNodes.length}</span>
                <span className="text-electric-green">航道: {meaningfulLinks.length}</span>
              </div>
              <div className="text-center text-electric-green/80 text-xs">
                🌌 终极宇宙视野 | ⚡ 点击瞬移
              </div>
              <div className="text-center text-starlight/50 mt-1" style={{fontSize: '10px'}}>
                金色框=当前视野 | 青色=今日论文 | 粉色=悬停中
              </div>
              <div className="text-center text-cyber-blue/70 mt-1" style={{fontSize: '9px'}}>
                终极视野: {Math.round(bounds.width/1000)}K × {Math.round(bounds.height/1000)}K 像素
              </div>
              <div className="text-center text-electric-green/60 mt-1" style={{fontSize: '8px'}}>
                覆盖比例: 百倍于用户窗口 | 性能优化版
              </div>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  )
}
