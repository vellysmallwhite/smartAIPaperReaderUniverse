import * as d3 from 'd3-force'
import { Node, Link } from './store'

export class PhysicsEngine {
  private simulation: d3.Simulation<Node, Link>
  private nodes: Node[] = []
  private links: Link[] = []
  private boundaryRadius: number = 800
  
  constructor() {
    this.simulation = d3.forceSimulation<Node>()
      // 更紧凑的链接布局：减小距离，增加强度
      .force('link', d3.forceLink<Node, Link>().id(d => d.id).distance(60).strength(0.8))
      // 减小斥力，让节点更紧密，同时保持性能
      .force('charge', d3.forceManyBody().strength(-200).theta(0.9))
      // 增强中心力，防止小组件无限飞行
      .force('center', d3.forceCenter(0, 0).strength(0.2))
      // 碰撞检测半径稍微减小，允许更紧密排列
      .force('collision', d3.forceCollide().radius(25).iterations(1))
      // 添加边界约束力，防止节点飞得太远
      .force('boundary', this.createBoundaryForce())
      // 增加阻尼，减少节点"抖动"
      .alphaDecay(0.03)
      .velocityDecay(0.9)
  }
  
  // 创建边界约束力，防止节点无限飞行
  private createBoundaryForce() {
    return (alpha: number) => {
      this.nodes.forEach(node => {
        if (node.x === undefined || node.y === undefined) return
        
        const distance = Math.sqrt(node.x * node.x + node.y * node.y)
        
        if (distance > this.boundaryRadius) {
          // 计算向中心的拉力
          const strength = (distance - this.boundaryRadius) * alpha * 0.1
          const angle = Math.atan2(node.y, node.x)
          
          // 应用向心力
          if (node.vx !== undefined) node.vx -= Math.cos(angle) * strength
          if (node.vy !== undefined) node.vy -= Math.sin(angle) * strength
        }
      })
    }
  }
  
  updateData(nodes: Node[], links: Link[]) {
    this.nodes = nodes
    this.links = links
    
    // 根据节点数量动态调整力参数和边界
    const nodeCount = nodes.length
    let linkDistance = 60
    let chargeStrength = -200
    let centerStrength = 0.2
    
    // 动态调整边界半径
    this.boundaryRadius = Math.max(500, Math.min(1200, nodeCount * 8))
    
    if (nodeCount > 50) {
      // 大图：更紧凑，增强中心力
      linkDistance = 45
      chargeStrength = -150
      centerStrength = 0.25
    } else if (nodeCount > 100) {
      // 超大图：非常紧凑，强中心力
      linkDistance = 35
      chargeStrength = -120
      centerStrength = 0.3
    }
    
    this.simulation
      .nodes(this.nodes)
    
    // 更新链接力的参数
    const linkForce = this.simulation.force<d3.ForceLink<Node, Link>>('link')
    if (linkForce) {
      linkForce.links(this.links).distance(linkDistance)
    }
    
    // 更新电荷力的参数
    const chargeForce = this.simulation.force<d3.ForceManyBody<Node>>('charge')
    if (chargeForce) {
      chargeForce.strength(chargeStrength)
    }
    
    // 更新中心力的参数
    const centerForce = this.simulation.force<d3.ForceCenter<Node>>('center')
    if (centerForce) {
      centerForce.strength(centerStrength)
    }
    
    // 更新边界力（重新创建以使用新的边界半径）
    this.simulation.force('boundary', this.createBoundaryForce())
    
    this.simulation.alpha(0.5).restart()
  }
  
  onTick(callback: (nodes: Node[], links: Link[]) => void) {
    this.simulation.on('tick', () => {
      callback(this.nodes, this.links)
    })
  }
  
  onEnd(callback: () => void) {
    this.simulation.on('end', callback)
  }
  
  centerNode(nodeId: string) {
    const node = this.nodes.find(n => n.id === nodeId)
    if (node) {
      node.fx = 0
      node.fy = 0
      this.simulation.alpha(0.3).restart()
      
      // 短暂固定后释放
      setTimeout(() => {
        if (node) {
          node.fx = null
          node.fy = null
        }
      }, 1000)
    }
  }
  
  // 增强节点稳定性：悬停时更温和的固定
  stabilizeNode(nodeId: string, x?: number, y?: number) {
    const node = this.nodes.find(n => n.id === nodeId)
    if (node) {
      // 使用当前位置或指定位置
      node.fx = x ?? node.x ?? null
      node.fy = y ?? node.y ?? null
      // 轻微重启，避免大幅抖动
      this.simulation.alpha(Math.min(0.1, this.simulation.alpha()))
    }
  }
  
  releaseNode(nodeId: string) {
    const node = this.nodes.find(n => n.id === nodeId)
    if (node) {
      node.fx = null
      node.fy = null
    }
  }
  
  // 获取图的边界框，用于小地图
  getBounds() {
    if (this.nodes.length === 0) {
      return { minX: -100, maxX: 100, minY: -100, maxY: 100, width: 200, height: 200 }
    }
    
    const xs = this.nodes.map(n => n.x ?? 0)
    const ys = this.nodes.map(n => n.y ?? 0)
    
    const minX = Math.min(...xs) - 50
    const maxX = Math.max(...xs) + 50
    const minY = Math.min(...ys) - 50
    const maxY = Math.max(...ys) + 50
    
    return {
      minX, maxX, minY, maxY,
      width: maxX - minX,
      height: maxY - minY
    }
  }
  
  highlightConnections(nodeId: string) {
    const connectedIds = new Set<string>()
    this.links.forEach(link => {
      const sourceId = typeof link.source === 'string' ? link.source : link.source.id
      const targetId = typeof link.target === 'string' ? link.target : link.target.id
      
      if (sourceId === nodeId) connectedIds.add(targetId)
      if (targetId === nodeId) connectedIds.add(sourceId)
    })
    
    return connectedIds
  }
  
  stop() {
    this.simulation.stop()
  }
  
  restart() {
    this.simulation.restart()
  }
}
