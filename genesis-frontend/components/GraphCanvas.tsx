'use client'

import { useRef, useEffect, useState } from 'react'
import { useGenesisStore } from '@/lib/store'
import { PhysicsEngine } from '@/lib/physics'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'

const DOMAIN_COLORS = {
  'Computer Vision': '#FF6B6B',
  'Natural Language Processing': '#4ECDC4',
  'Machine Learning': '#45B7D1',
  'Reinforcement Learning': '#96CEB4',
  'Robotics': '#FECA57',
  'Speech & Audio': '#FF9FF3',
  'Graph Neural Networks': '#54A0FF',
  'Generative AI': '#5F27CD',
  'Multimodal': '#00D2D3',
  'AI/ML': '#C8D6E5'
}

export default function GraphCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const physicsRef = useRef<PhysicsEngine | null>(null)
  const animationRef = useRef<number>()
  
  const {
    graphData,
    addGraphData,
    setSelectedPaper,
    setHoveredNode,
    hoveredNode,
    selectedPaper,
    isExpandingNode,
    setIsExpandingNode,
    expandingNodeId,
    setExpandingNodeId,
    setCameraTarget
  } = useGenesisStore()
  
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [view, setView] = useState({ k: 1, tx: 0, ty: 0 })
  const isPanningRef = useRef(false)
  const lastPosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 })
  const hoveredNodeIdRef = useRef<string | null>(null)
  const viewRef = useRef(view)
  const isInteractingRef = useRef(false)
  
  // 悬停工具提示状态
  const [tooltip, setTooltip] = useState<{
    visible: boolean
    x: number
    y: number
    title: string
    domain: string
    summary?: string
  }>({
    visible: false,
    x: 0,
    y: 0,
    title: '',
    domain: '',
    summary: ''
  })
  
  // 触摸手势支持
  const touchesRef = useRef<{ [key: number]: { x: number; y: number } }>({})
  const lastPinchDistanceRef = useRef(0)
  
  // 缩放性能优化
  const wheelTimeoutRef = useRef<number>()
  const pendingWheelDeltaRef = useRef(0)
  const rafIdRef = useRef<number>()
  
  // 保持viewRef同步，并通知小地图
  useEffect(() => {
    viewRef.current = view
    // 发送视图变化事件给小地图
    const event = new CustomEvent('graphViewChange', { detail: view })
    window.dispatchEvent(event)
  }, [view])
  
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight
        })
      }
    }
    
    updateDimensions()
    window.addEventListener('resize', updateDimensions)
    
    // 监听小地图瞬移事件
    const handleMinimapTeleport = (event: CustomEvent) => {
      const { newView } = event.detail
      
      if (newView) {
        // 瞬移到新位置
        viewRef.current = newView
        setView(newView)
        
        // 暂停物理引擎，避免瞬移时的动画冲突
        if (physicsRef.current) {
          physicsRef.current.stop()
          setTimeout(() => {
            if (physicsRef.current) {
              physicsRef.current.restart()
            }
          }, 100)
        }
      }
    }
    
    window.addEventListener('minimapTeleport', handleMinimapTeleport as EventListener)
    
    return () => {
      window.removeEventListener('resize', updateDimensions)
      window.removeEventListener('minimapTeleport', handleMinimapTeleport as EventListener)
    }
  }, [dimensions])
  
  useEffect(() => {
    if (!canvasRef.current) return
    
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    
    // 设置高DPI
    const dpr = window.devicePixelRatio || 1
    canvas.width = dimensions.width * dpr
    canvas.height = dimensions.height * dpr
    canvas.style.width = `${dimensions.width}px`
    canvas.style.height = `${dimensions.height}px`
    ctx.scale(dpr, dpr)
    
    // 初始化物理引擎
    if (!physicsRef.current) {
      physicsRef.current = new PhysicsEngine()
    }
    
    const physics = physicsRef.current
    
    // 渲染函数 - 优化性能
    const render = () => {
      ctx.clearRect(0, 0, dimensions.width, dimensions.height)
      
      const centerX = dimensions.width / 2
      const centerY = dimensions.height / 2
      const { k, tx, ty } = viewRef.current
      
      // 交互时降低渲染质量以提高性能
      const isZooming = isInteractingRef.current && !isPanningRef.current
      const skipDetails = isZooming || k < 0.5
      
      // 渲染连线 - 缩放时简化
      if (!skipDetails || k > 0.8) {
        graphData.links.forEach(link => {
          const source = typeof link.source === 'string' 
            ? graphData.nodes.find(n => n.id === link.source) 
            : link.source
          const target = typeof link.target === 'string' 
            ? graphData.nodes.find(n => n.id === link.target) 
            : link.target
          
          if (!source || !target || source.x === undefined || source.y === undefined || 
              target.x === undefined || target.y === undefined) return
          
          const sourceX = centerX + tx + (source.x || 0) * k
          const sourceY = centerY + ty + (source.y || 0) * k
          const targetX = centerX + tx + (target.x || 0) * k
          const targetY = centerY + ty + (target.y || 0) * k
          
          // 缩放时使用简单颜色，否则使用渐变
          if (isZooming) {
            ctx.strokeStyle = 'rgba(0, 246, 255, 0.3)'
          } else {
            const gradient = ctx.createLinearGradient(sourceX, sourceY, targetX, targetY)
            gradient.addColorStop(0, 'rgba(0, 246, 255, 0.6)')
            gradient.addColorStop(1, 'rgba(255, 0, 229, 0.3)')
            ctx.strokeStyle = gradient
          }
          
          ctx.lineWidth = 1.5
          ctx.globalAlpha = selectedPaper && 
            (source.id === selectedPaper || target.id === selectedPaper) ? 1 : 0.4
          
          ctx.beginPath()
          ctx.moveTo(sourceX, sourceY)
          ctx.lineTo(targetX, targetY)
          ctx.stroke()
        })
      }
      
      // 渲染节点
      graphData.nodes.forEach(node => {
        if (node.x === undefined || node.y === undefined) return
        
        const x = centerX + tx + (node.x || 0) * k
        const y = centerY + ty + (node.y || 0) * k
        
        // 节点大小基于类型和作者数量
        let radius = 8
        if (node.type === 'today') radius = 15
        else if (node.type === 'center') radius = 20
        if (node.author_count) radius += Math.min(node.author_count * 0.5, 8)
        const radiusScaled = radius * (0.6 + 0.4 * Math.max(0.5, Math.min(2, k)))
        
        // 节点颜色基于领域
        const domainColor = DOMAIN_COLORS[node.domain as keyof typeof DOMAIN_COLORS] || DOMAIN_COLORS['AI/ML']
        
        // 绘制外圈光晕 - 缩放时跳过以提高性能
        if (!skipDetails) {
          const glowRadius = radiusScaled * 2
          const glowGradient = ctx.createRadialGradient(x, y, 0, x, y, glowRadius)
          glowGradient.addColorStop(0, `${domainColor}80`)
          glowGradient.addColorStop(0.5, `${domainColor}40`)
          glowGradient.addColorStop(1, 'transparent')
          
          ctx.fillStyle = glowGradient
          ctx.globalAlpha = node.id === hoveredNode ? 0.8 : 0.4
          ctx.beginPath()
          ctx.arc(x, y, glowRadius, 0, Math.PI * 2)
          ctx.fill()
        }
        
        // 绘制主节点
        ctx.globalAlpha = 1
        ctx.fillStyle = domainColor
        ctx.beginPath()
        ctx.arc(x, y, radiusScaled, 0, Math.PI * 2)
        ctx.fill()
        
        // 节点边框
        ctx.strokeStyle = '#FFFFFF'
        ctx.lineWidth = node.id === selectedPaper ? 3 : 1
        ctx.globalAlpha = node.id === hoveredNode ? 1 : 0.8
        ctx.stroke()
        
        // 特殊效果 - 缩放时跳过
        if (!skipDetails && node.type === 'today') {
          // 今日论文的脉冲效果
          const time = Date.now() * 0.005
          const pulseAlpha = 0.3 + 0.3 * Math.sin(time)
          ctx.globalAlpha = pulseAlpha
          ctx.strokeStyle = '#00F6FF'
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.arc(x, y, radiusScaled + 5, 0, Math.PI * 2)
          ctx.stroke()
        }
        
        // 显示节点标题 - 缩放时跳过
        if (!skipDetails && radiusScaled > 12 && node.title) {
          ctx.globalAlpha = 1
          ctx.fillStyle = '#FFFFFF'
          ctx.font = '12px Roboto Mono'
          ctx.textAlign = 'center'
          ctx.fillText(
            node.title.length > 20 ? node.title.substring(0, 20) + '...' : node.title,
            x,
            y + radiusScaled + 15
          )
        }
      })
      
      ctx.globalAlpha = 1
    }
    
    // 设置物理引擎回调 - 交互时暂停以提高性能
    physics.onTick(() => {
      if (!isInteractingRef.current) {
        render()
      }
    })
    physics.updateData(graphData.nodes, graphData.links)
    
    const animate = () => {
      if (isInteractingRef.current) {
        render() // 交互时直接渲染，不依赖物理引擎
      }
      animationRef.current = requestAnimationFrame(animate)
    }
    animate()
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current)
      }
      if (wheelTimeoutRef.current) {
        clearTimeout(wheelTimeoutRef.current)
      }
    }
  }, [graphData, dimensions, hoveredNode, selectedPaper])
  
  // 处理鼠标交互（悬停冻结、点击展开、滚轮缩放、拖拽平移）
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    
    const getNodeAt = (clientX: number, clientY: number) => {
      const rect = canvas.getBoundingClientRect()
      const px = clientX - rect.left
      const py = clientY - rect.top
      const centerX = dimensions.width / 2
      const centerY = dimensions.height / 2
      const { k, tx, ty } = viewRef.current

      return graphData.nodes.find(node => {
        if (node.x === undefined || node.y === undefined) return false
        const nx = centerX + tx + node.x * k
        const ny = centerY + ty + node.y * k
        let baseR = 8
        if (node.type === 'today') baseR = 15
        else if (node.type === 'center') baseR = 20
        const r = baseR * (0.6 + 0.4 * Math.max(0.5, Math.min(2, k)))
        const dx = px - nx
        const dy = py - ny
        return Math.sqrt(dx * dx + dy * dy) < r + 5
      })
    }
    
    const handleMouseMove = (e: MouseEvent) => {
      if (isPanningRef.current) {
        // 高性能拖拽 - 直接更新viewRef并触发重绘
        const dx = e.clientX - lastPosRef.current.x
        const dy = e.clientY - lastPosRef.current.y
        lastPosRef.current = { x: e.clientX, y: e.clientY }
        
        viewRef.current = {
          ...viewRef.current,
          tx: viewRef.current.tx + dx,
          ty: viewRef.current.ty + dy
        }
        setView(viewRef.current) // 同步状态
        
        // 拖拽时隐藏工具提示
        setTooltip(prev => ({ ...prev, visible: false }))
        return
      }
      
      const node = getNodeAt(e.clientX, e.clientY)
      const newHoveredId = node?.id || null
      
      if (newHoveredId !== hoveredNode) {
        setHoveredNode(newHoveredId)
        canvas.style.cursor = newHoveredId ? 'pointer' : 'default'

        // 改进的悬停稳定机制
        if (physicsRef.current) {
          // 释放之前悬停节点
          if (hoveredNodeIdRef.current) {
            physicsRef.current.releaseNode(hoveredNodeIdRef.current)
          }
          hoveredNodeIdRef.current = newHoveredId
          if (node) {
            // 使用新的稳定方法，更温和的固定
            physicsRef.current.stabilizeNode(node.id, node.x, node.y)
          }
        }
        
        // 工具提示逻辑
        if (node && node.title) {
          // 计算是否需要显示工具提示
          // 当缩放小于0.8或节点半径小于12时显示工具提示
          let baseRadius = 8
          if (node.type === 'today') baseRadius = 15
          else if (node.type === 'center') baseRadius = 20
          if (node.author_count) baseRadius += Math.min(node.author_count * 0.5, 8)
          const currentRadius = baseRadius * (0.6 + 0.4 * Math.max(0.5, Math.min(2, viewRef.current.k)))
          
          const shouldShowTooltip = viewRef.current.k < 0.8 || currentRadius < 12
          
          if (shouldShowTooltip) {
            const rect = canvas.getBoundingClientRect()
            setTooltip({
              visible: true,
              x: e.clientX - rect.left,
              y: e.clientY - rect.top,
              title: node.title,
              domain: node.domain || 'AI/ML',
              summary: node.summary
            })
          } else {
            setTooltip(prev => ({ ...prev, visible: false }))
          }
        } else {
          setTooltip(prev => ({ ...prev, visible: false }))
        }
      } else if (node && tooltip.visible) {
        // 更新工具提示位置（跟随鼠标）
        const rect = canvas.getBoundingClientRect()
        setTooltip(prev => ({
          ...prev,
          x: e.clientX - rect.left,
          y: e.clientY - rect.top
        }))
      }
    }
    
    const handleClick = async (e: MouseEvent) => {
      const node = getNodeAt(e.clientX, e.clientY)
      if (node && !isExpandingNode) {
        setSelectedPaper(node.id)
        setCameraTarget({ x: node.x || 0, y: node.y || 0 })
        
        if (physicsRef.current) {
          physicsRef.current.centerNode(node.id)
        }
        
        // 展开节点
        try {
          setIsExpandingNode(true)
          setExpandingNodeId(node.id)
          const expandData = await api.expandNode(node.id)
          addGraphData(expandData)
        } catch (error) {
          console.error('Failed to expand node:', error)
        } finally {
          setIsExpandingNode(false)
          setExpandingNodeId(null)
        }
      }
    }

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault()
      
      // 累积滚轮增量
      pendingWheelDeltaRef.current += e.deltaY
      
      // 开始缩放时暂停物理引擎
      if (!isInteractingRef.current) {
        isInteractingRef.current = true
        if (physicsRef.current) physicsRef.current.stop()
      }
      
      // 清除之前的超时
      if (wheelTimeoutRef.current) {
        window.clearTimeout(wheelTimeoutRef.current)
      }
      
      // 取消之前的动画帧
      if (rafIdRef.current) {
        window.cancelAnimationFrame(rafIdRef.current)
      }
      
      // 使用 requestAnimationFrame 批量处理缩放
      rafIdRef.current = window.requestAnimationFrame(() => {
        const rect = canvas.getBoundingClientRect()
        const px = e.clientX - rect.left - dimensions.width / 2
        const py = e.clientY - rect.top - dimensions.height / 2
        
        // Mac触摸板双指缩放检测
        const isTouchpadPinch = e.ctrlKey || Math.abs(e.deltaX) > 0
        
        let factor
        if (isTouchpadPinch) {
          // 触摸板缩放，更敏感
          factor = Math.exp(-pendingWheelDeltaRef.current * 0.01)
        } else {
          // 鼠标滚轮缩放
          factor = Math.exp(-pendingWheelDeltaRef.current * 0.002)
        }
        
        const currentView = viewRef.current
        const newK = Math.max(0.3, Math.min(5, currentView.k * factor))
        const scale = newK / currentView.k
        const newTx = currentView.tx + px * (1 - scale)
        const newTy = currentView.ty + py * (1 - scale)
        
        viewRef.current = { k: newK, tx: newTx, ty: newTy }
        setView(viewRef.current)
        
        // 清零累积值
        pendingWheelDeltaRef.current = 0
      })
      
      // 缩放结束后恢复物理引擎
      wheelTimeoutRef.current = window.setTimeout(() => {
        isInteractingRef.current = false
        if (physicsRef.current) physicsRef.current.restart()
      }, 150)
    }

    const handleMouseDown = (e: MouseEvent) => {
      // 左键且不点到节点时，开始平移
      if (e.button !== 0) return
      const node = getNodeAt(e.clientX, e.clientY)
      if (!node) {
        isPanningRef.current = true
        isInteractingRef.current = true // 暂停物理引擎
        lastPosRef.current = { x: e.clientX, y: e.clientY }
        canvas.style.cursor = 'grabbing'
        if (physicsRef.current) physicsRef.current.stop()
      }
    }

    const handleMouseUp = () => {
      if (isPanningRef.current) {
        isPanningRef.current = false
        isInteractingRef.current = false // 恢复物理引擎
        canvas.style.cursor = 'default'
        if (physicsRef.current) physicsRef.current.restart()
      }
    }
    
    const handleMouseLeave = () => {
      // 鼠标离开画布时隐藏工具提示
      setTooltip(prev => ({ ...prev, visible: false }))
      setHoveredNode(null)
      
      // 释放悬停节点
      if (physicsRef.current && hoveredNodeIdRef.current) {
        physicsRef.current.releaseNode(hoveredNodeIdRef.current)
        hoveredNodeIdRef.current = null
      }
    }
    
    // 触摸事件支持（Mac触摸板和移动设备）
    const handleTouchStart = (e: TouchEvent) => {
      e.preventDefault()
      const touches = Array.from(e.touches)
      touches.forEach(touch => {
        touchesRef.current[touch.identifier] = { x: touch.clientX, y: touch.clientY }
      })
      
      if (touches.length === 2) {
        // 双指捏合开始
        const [t1, t2] = touches
        const distance = Math.sqrt((t1.clientX - t2.clientX) ** 2 + (t1.clientY - t2.clientY) ** 2)
        lastPinchDistanceRef.current = distance
        isInteractingRef.current = true
        if (physicsRef.current) physicsRef.current.stop()
      } else if (touches.length === 1) {
        // 单指平移
        const node = getNodeAt(touches[0].clientX, touches[0].clientY)
        if (!node) {
          isPanningRef.current = true
          isInteractingRef.current = true
          lastPosRef.current = { x: touches[0].clientX, y: touches[0].clientY }
          if (physicsRef.current) physicsRef.current.stop()
        }
      }
    }

    const handleTouchMove = (e: TouchEvent) => {
      e.preventDefault()
      const touches = Array.from(e.touches)
      
      // 取消之前的动画帧
      if (rafIdRef.current) {
        window.cancelAnimationFrame(rafIdRef.current)
      }
      
      // 使用 requestAnimationFrame 优化触摸移动
      rafIdRef.current = window.requestAnimationFrame(() => {
        if (touches.length === 2) {
          // 双指捏合缩放
          const [t1, t2] = touches
          const distance = Math.sqrt((t1.clientX - t2.clientX) ** 2 + (t1.clientY - t2.clientY) ** 2)
          const centerX = (t1.clientX + t2.clientX) / 2
          const centerY = (t1.clientY + t2.clientY) / 2
          
          const rect = canvas.getBoundingClientRect()
          const px = centerX - rect.left - dimensions.width / 2
          const py = centerY - rect.top - dimensions.height / 2
          
          const factor = distance / lastPinchDistanceRef.current
          const currentView = viewRef.current
          const newK = Math.max(0.3, Math.min(5, currentView.k * factor))
          const scale = newK / currentView.k
          const newTx = currentView.tx + px * (1 - scale)
          const newTy = currentView.ty + py * (1 - scale)
          
          viewRef.current = { k: newK, tx: newTx, ty: newTy }
          setView(viewRef.current)
          lastPinchDistanceRef.current = distance
        } else if (touches.length === 1 && isPanningRef.current) {
          // 单指平移
          const dx = touches[0].clientX - lastPosRef.current.x
          const dy = touches[0].clientY - lastPosRef.current.y
          lastPosRef.current = { x: touches[0].clientX, y: touches[0].clientY }
          
          viewRef.current = {
            ...viewRef.current,
            tx: viewRef.current.tx + dx,
            ty: viewRef.current.ty + dy
          }
          setView(viewRef.current)
        }
      })
    }

    const handleTouchEnd = (e: TouchEvent) => {
      e.preventDefault()
      const remainingTouches = Array.from(e.touches)
      
      // 清理已结束的触摸
      Array.from(e.changedTouches).forEach(touch => {
        delete touchesRef.current[touch.identifier]
      })
      
      if (remainingTouches.length === 0) {
        // 所有触摸结束
        isPanningRef.current = false
        isInteractingRef.current = false
        if (physicsRef.current) physicsRef.current.restart()
      } else if (remainingTouches.length === 1 && Object.keys(touchesRef.current).length === 2) {
        // 从双指切换到单指
        const [t1] = remainingTouches
        const distance = 0
        lastPinchDistanceRef.current = distance
      }
    }

    canvas.addEventListener('mousemove', handleMouseMove)
    canvas.addEventListener('click', handleClick)
    canvas.addEventListener('wheel', handleWheel, { passive: false })
    canvas.addEventListener('mousedown', handleMouseDown)
    window.addEventListener('mouseup', handleMouseUp)
    canvas.addEventListener('mouseleave', handleMouseLeave)
    
    // 触摸事件
    canvas.addEventListener('touchstart', handleTouchStart, { passive: false })
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false })
    canvas.addEventListener('touchend', handleTouchEnd, { passive: false })
    
    return () => {
      canvas.removeEventListener('mousemove', handleMouseMove)
      canvas.removeEventListener('click', handleClick)
      canvas.removeEventListener('wheel', handleWheel as any)
      canvas.removeEventListener('mousedown', handleMouseDown)
      window.removeEventListener('mouseup', handleMouseUp)
      canvas.removeEventListener('mouseleave', handleMouseLeave)
      canvas.removeEventListener('touchstart', handleTouchStart as any)
      canvas.removeEventListener('touchmove', handleTouchMove as any)
      canvas.removeEventListener('touchend', handleTouchEnd as any)
    }
  }, [graphData.nodes, hoveredNode, dimensions, view, setHoveredNode, setSelectedPaper, setCameraTarget, isExpandingNode, addGraphData, setIsExpandingNode, setExpandingNodeId])
  
  return (
    <div ref={containerRef} className="w-full h-full relative">
      <canvas
        ref={canvasRef}
        className="w-full h-full"
      />
      
      {/* 展开节点加载指示器 */}
      {isExpandingNode && expandingNodeId && (
        <motion.div
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div className="holographic-glass px-6 py-3 rounded-lg text-center">
            <div className="star-rings mx-auto mb-2">
              <div className="star-ring"></div>
              <div className="star-ring"></div>
              <div className="star-ring"></div>
            </div>
            <p className="text-cyber-blue font-roboto-mono">超空间跃迁中...</p>
          </div>
        </motion.div>
      )}
      
      {/* 性能模式指示器 */}
      {isInteractingRef.current && (
        <div className="absolute top-2 right-2 px-2 py-1 bg-electric-green/20 border border-electric-green/50 rounded text-xs text-electric-green font-roboto-mono">
          🚀 性能模式
        </div>
      )}
      
      {/* 悬停工具提示 */}
      {tooltip.visible && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.15 }}
          className="absolute z-50 pointer-events-none"
          style={{
            left: Math.min(tooltip.x + 15, dimensions.width - 280),
            top: Math.max(tooltip.y - 80, 10)
          }}
        >
          <div className="holographic-glass p-3 rounded-lg border border-cyber-blue/50 shadow-lg max-w-xs">
            {/* 领域标签 */}
            <div className="flex items-center mb-2">
              <div 
                className="w-3 h-3 rounded-full mr-2"
                style={{ 
                  backgroundColor: DOMAIN_COLORS[tooltip.domain as keyof typeof DOMAIN_COLORS] || DOMAIN_COLORS['AI/ML'],
                  boxShadow: `0 0 8px ${DOMAIN_COLORS[tooltip.domain as keyof typeof DOMAIN_COLORS] || DOMAIN_COLORS['AI/ML']}40`
                }}
              ></div>
              <span className="text-xs text-starlight/70 font-roboto-mono">
                {tooltip.domain}
              </span>
            </div>
            
            {/* 论文标题 */}
            <div className="text-sm font-semibold text-cyber-blue mb-1 leading-tight">
              {tooltip.title}
            </div>
            
            {/* 摘要预览（如果有） */}
            {tooltip.summary && (
              <div className="text-xs text-starlight/80 font-roboto-mono leading-relaxed">
                {tooltip.summary.length > 80 
                  ? `${tooltip.summary.substring(0, 80)}...` 
                  : tooltip.summary
                }
              </div>
            )}
            
            {/* 提示文字 */}
            <div className="text-xs text-electric-green/60 mt-2 font-roboto-mono">
              💡 点击查看详情
            </div>
          </div>
          
          {/* 工具提示箭头 */}
          <div 
            className="absolute w-3 h-3 bg-deep-space/90 border-l border-b border-cyber-blue/50 transform rotate-45"
            style={{
              left: '12px',
              bottom: '-6px'
            }}
          ></div>
        </motion.div>
      )}
    </div>
  )
}
