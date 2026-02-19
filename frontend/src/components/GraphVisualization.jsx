import { useCallback, useRef, useState, useMemo } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import './GraphVisualization.css'

/* ── Pattern → Color mapping ──────────────────────────────── */
const PATTERN_COLORS = {
  cycle_length_3:  '#f43f5e',
  cycle_length_4:  '#fb7185',
  cycle_length_5:  '#fda4af',
  fan_in:          '#a78bfa',
  fan_out:         '#8b5cf6',
  shell_chain:     '#fb923c',
  round_trip:      '#f59e0b',
  amount_anomaly:  '#ef4444',
  rapid_movement:  '#f97316',
  structuring:     '#eab308',
  high_velocity:   '#f59e0b',
  multi_ring:      '#fbbf24',
}

const PATTERN_LABELS = {
  cycle_length_3:  'Cycle (3)',
  cycle_length_4:  'Cycle (4)',
  cycle_length_5:  'Cycle (5)',
  fan_in:          'Fan-in',
  fan_out:         'Fan-out',
  shell_chain:     'Shell Chain',
  round_trip:      'Round Trip',
  amount_anomaly:  'Anomaly',
  rapid_movement:  'Rapid Move',
  structuring:     'Structuring',
  high_velocity:   'High Velocity',
  multi_ring:      'Multi Ring',
}

/* ── Node styling helpers ─────────────────────────────────── */
function getNodeColor(node) {
  if (!node.suspicious) return '#10b981'
  const p = node.detected_patterns || []
  if (p.some(x => x.startsWith('cycle')))    return '#f43f5e'
  if (p.includes('fan_in'))                   return '#a78bfa'
  if (p.includes('fan_out'))                  return '#8b5cf6'
  if (p.includes('shell_chain'))              return '#fb923c'
  if (p.includes('round_trip'))               return '#f59e0b'
  if (p.includes('amount_anomaly'))           return '#ef4444'
  if (p.includes('rapid_movement'))           return '#f97316'
  if (p.includes('structuring'))              return '#eab308'
  if (p.includes('high_velocity'))            return '#f59e0b'
  return '#fbbf24'
}

function getNodeSize(node) {
  if (!node.suspicious) return 3.5
  const score = node.suspicion_score || 0
  return 4 + (score / 100) * 14
}

/* ── Legend items ──────────────────────────────────────────── */
const LEGEND = [
  { color: '#10b981',  label: 'Safe' },
  { color: '#f43f5e',  label: 'Cycle' },
  { color: '#a78bfa',  label: 'Fan-in' },
  { color: '#8b5cf6',  label: 'Fan-out' },
  { color: '#fb923c',  label: 'Shell' },
  { color: '#f59e0b',  label: 'Round Trip' },
  { color: '#ef4444',  label: 'Anomaly' },
  { color: '#f97316',  label: 'Rapid Move' },
  { color: '#eab308',  label: 'Structuring' },
  { color: '#f59e0b',  label: 'Velocity' },
]

export default function GraphVisualization({ graphData, rings }) {
  const fgRef = useRef()
  const [selected, setSelected] = useState(null)
  const [hovered, setHovered] = useState(null)
  const [filter, setFilter] = useState('all') // all | suspicious | safe
  const [highlightRing, setHighlightRing] = useState(null)

  // Build ring member lookup
  const ringMembers = useMemo(() => {
    if (!rings) return new Set()
    if (!highlightRing) return new Set()
    const ring = rings.find(r => r.ring_id === highlightRing)
    return ring ? new Set(ring.member_accounts) : new Set()
  }, [rings, highlightRing])

  // Filter visible nodes
  const processedData = useMemo(() => {
    if (!graphData?.nodes?.length) return { nodes: [], links: [] }

    let nodes = graphData.nodes.map(n => ({ ...n }))
    if (filter === 'suspicious') nodes = nodes.filter(n => n.suspicious)
    else if (filter === 'safe') nodes = nodes.filter(n => !n.suspicious)

    const visibleIds = new Set(nodes.map(n => n.id))
    const links = graphData.edges
      .filter(e => visibleIds.has(e.source) && visibleIds.has(e.target))
      .map(e => ({
        source: e.source,
        target: e.target,
        total_amount: e.total_amount,
        tx_count: e.tx_count,
      }))

    return { nodes, links }
  }, [graphData, filter])

  const handleNodeClick = useCallback((node) => {
    setSelected(node)
    if (fgRef.current) {
      fgRef.current.centerAt(node.x, node.y, 600)
      fgRef.current.zoom(4, 600)
    }
  }, [])

  const handleNodeHover = useCallback((node) => {
    setHovered(node)
    document.body.style.cursor = node ? 'pointer' : 'default'
  }, [])

  const handleBgClick = useCallback(() => setSelected(null), [])

  const paintNode = useCallback((node, ctx, globalScale) => {
    const size = getNodeSize(node)
    const color = getNodeColor(node)
    const isHighlighted = hovered?.id === node.id || selected?.id === node.id
    const isRingMember  = highlightRing && ringMembers.has(node.id)
    const isDimmed      = highlightRing && !isRingMember

    ctx.save()

    if (isDimmed) ctx.globalAlpha = 0.12

    // Glow 
    if (node.suspicious && !isDimmed) {
      ctx.shadowColor = color
      ctx.shadowBlur  = isHighlighted ? 24 : 12
    }

    // Ring highlight outer ring
    if (isRingMember) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 4, 0, 2 * Math.PI)
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 0.6
      ctx.setLineDash([2, 2])
      ctx.stroke()
      ctx.setLineDash([])
    }

    // Node circle
    ctx.beginPath()
    ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()

    // Border for highlighted
    if (isHighlighted && !isDimmed) {
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 1.8
      ctx.stroke()
    }

    ctx.shadowBlur = 0

    // Label
    if ((globalScale > 1.8 || node.suspicious || isRingMember) && !isDimmed) {
      const label = node.label || node.id
      const fontSize = Math.max(11 / globalScale, 5)
      const isLight = document.documentElement.getAttribute('data-theme') === 'light'
      ctx.font = `500 ${fontSize}px Inter, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      if (isLight) {
        ctx.fillStyle = isRingMember ? '#1a1030' : 'rgba(26, 16, 48, 0.85)'
      } else {
        ctx.fillStyle = isRingMember ? '#fff' : 'rgba(241, 245, 249, 0.8)'
      }
      ctx.fillText(label, node.x, node.y + size + 3)
    }

    ctx.restore()
  }, [hovered, selected, highlightRing, ringMembers])

  // Link color
  const linkColor = useCallback((link) => {
    const isLight = document.documentElement.getAttribute('data-theme') === 'light'
    if (!highlightRing) return isLight ? 'rgba(80,60,140,0.25)' : 'rgba(148,163,184,0.12)'
    const s = typeof link.source === 'object' ? link.source.id : link.source
    const t = typeof link.target === 'object' ? link.target.id : link.target
    if (ringMembers.has(s) && ringMembers.has(t)) return isLight ? 'rgba(80,60,140,0.7)' : 'rgba(255,255,255,0.4)'
    return isLight ? 'rgba(80,60,140,0.06)' : 'rgba(148,163,184,0.04)'
  }, [highlightRing, ringMembers])

  if (!graphData?.nodes?.length) {
    return (
      <div className="graph-empty">
        <div className="empty-icon">◉</div>
        <p>No graph data available</p>
      </div>
    )
  }

  const suspiciousCount = graphData.nodes.filter(n => n.suspicious).length
  const safeCount = graphData.nodes.length - suspiciousCount

  return (
    <div className="graph-container">
      {/* ── Toolbar ───────────────────────────────────────── */}
      <div className="graph-toolbar">
        <div className="graph-toolbar-left">
          {/* Legend */}
          <div className="legend-group">
            {LEGEND.map(l => (
              <div key={l.label} className="legend-item">
                <span className="legend-dot" style={{ background: l.color }} />
                <span>{l.label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="graph-toolbar-right">
          {/* Ring filter */}
          {rings && rings.length > 0 && (
            <select
              className="graph-select"
              value={highlightRing || ''}
              onChange={e => setHighlightRing(e.target.value || null)}
            >
              <option value="">All Rings</option>
              {rings.map(r => (
                <option key={r.ring_id} value={r.ring_id}>
                  {r.ring_id} — {r.pattern_type} ({r.member_accounts.length})
                </option>
              ))}
            </select>
          )}

          {/* Node filter */}
          <div className="filter-pills">
            {[
              { key: 'all', label: `All (${graphData.nodes.length})` },
              { key: 'suspicious', label: `Flagged (${suspiciousCount})` },
              { key: 'safe', label: `Safe (${safeCount})` },
            ].map(f => (
              <button
                key={f.key}
                className={`filter-pill ${filter === f.key ? 'active' : ''}`}
                onClick={() => setFilter(f.key)}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Zoom controls */}
          <div className="zoom-controls">
            <button className="zoom-btn" onClick={() => fgRef.current?.zoom(fgRef.current.zoom() * 1.4, 300)} title="Zoom in">+</button>
            <button className="zoom-btn" onClick={() => fgRef.current?.zoom(fgRef.current.zoom() * 0.7, 300)} title="Zoom out">−</button>
            <button className="zoom-btn" onClick={() => fgRef.current?.zoomToFit(400, 40)} title="Fit view">⊞</button>
          </div>
        </div>
      </div>

      {/* ── Graph Canvas ──────────────────────────────────── */}
      <div className="graph-canvas">
        <ForceGraph2D
          ref={fgRef}
          graphData={processedData}
          nodeCanvasObject={paintNode}
          nodeCanvasObjectMode={() => 'replace'}
          onNodeClick={handleNodeClick}
          onNodeHover={handleNodeHover}
          onBackgroundClick={handleBgClick}
          linkColor={linkColor}
          linkWidth={0.6}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkDirectionalParticles={1}
          linkDirectionalParticleSpeed={0.003}
          linkDirectionalParticleWidth={1.5}
          linkDirectionalParticleColor={() => 'rgba(168,85,247,0.5)'}
          backgroundColor="transparent"
          width={undefined}
          height={580}
          cooldownTicks={100}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
        />
      </div>

      {/* ── Hover tooltip ─────────────────────────────────── */}
      {hovered && !selected && (
        <div className="hover-tooltip">
          <span className="tooltip-dot" style={{ background: getNodeColor(hovered) }} />
          <span className="tooltip-id">{hovered.id}</span>
          {hovered.suspicious && (
            <span className="tooltip-score">Score: {hovered.suspicion_score}</span>
          )}
        </div>
      )}

      {/* ── Node Detail Panel ─────────────────────────────── */}
      {selected && (
        <div className="node-panel">
          <div className="node-panel-header">
            <div className="panel-title-row">
              <span className="panel-dot" style={{ background: getNodeColor(selected) }} />
              <h3>{selected.id}</h3>
            </div>
            <button className="close-btn" onClick={() => setSelected(null)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>

          {selected.suspicious && (
            <div className="panel-score-bar">
              <div className="score-track">
                <div
                  className="score-fill"
                  style={{
                    width: `${selected.suspicion_score}%`,
                    background: selected.suspicion_score >= 70 ? 'var(--danger)' :
                                selected.suspicion_score >= 40 ? 'var(--warning)' : 'var(--safe)',
                  }}
                />
              </div>
              <span className="score-label">{selected.suspicion_score}/100</span>
            </div>
          )}

          <div className="node-panel-body">
            <div className="meta-grid">
              <div className="meta-item">
                <span className="meta-label">Transactions</span>
                <span className="meta-value">{selected.tx_count}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Total Sent</span>
                <span className="meta-value">${Number(selected.total_sent || 0).toLocaleString()}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Total Received</span>
                <span className="meta-value">${Number(selected.total_received || 0).toLocaleString()}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Net Flow</span>
                <span className={`meta-value ${(selected.net_flow || 0) >= 0 ? 'positive' : 'negative'}`}>
                  {(selected.net_flow || 0) >= 0 ? '+' : ''}${Number(selected.net_flow || 0).toLocaleString()}
                </span>
              </div>
              {selected.sent_count !== undefined && (
                <div className="meta-item">
                  <span className="meta-label">Sent Count</span>
                  <span className="meta-value">{selected.sent_count}</span>
                </div>
              )}
              {selected.received_count !== undefined && (
                <div className="meta-item">
                  <span className="meta-label">Recv Count</span>
                  <span className="meta-value">{selected.received_count}</span>
                </div>
              )}
              {selected.first_tx && (
                <div className="meta-item full">
                  <span className="meta-label">First Transaction</span>
                  <span className="meta-value mono">{selected.first_tx}</span>
                </div>
              )}
              {selected.last_tx && (
                <div className="meta-item full">
                  <span className="meta-label">Last Transaction</span>
                  <span className="meta-value mono">{selected.last_tx}</span>
                </div>
              )}
            </div>

            {/* Suspicious details */}
            {selected.suspicious && (
              <>
                {selected.risk_explanation && (
                  <div className="panel-section">
                    <span className="meta-label">Risk Explanation</span>
                    <p className="risk-explanation-text">{selected.risk_explanation}</p>
                  </div>
                )}
                {selected.ring_ids?.length > 0 && (
                  <div className="panel-section">
                    <span className="meta-label">Ring Membership</span>
                    <div className="ring-tags">
                      {selected.ring_ids.map(rid => (
                        <button
                          key={rid}
                          className={`ring-tag ${highlightRing === rid ? 'active' : ''}`}
                          onClick={() => setHighlightRing(highlightRing === rid ? null : rid)}
                        >
                          {rid}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {selected.detected_patterns?.length > 0 && (
                  <div className="panel-section">
                    <span className="meta-label">Detected Patterns</span>
                    <div className="pattern-tags">
                      {selected.detected_patterns.map(p => (
                        <span
                          key={p}
                          className="pattern-tag"
                          style={{
                            background: (PATTERN_COLORS[p] || '#a855f7') + '18',
                            color: PATTERN_COLORS[p] || '#a855f7',
                            border: `1px solid ${(PATTERN_COLORS[p] || '#a855f7')}33`,
                          }}
                        >
                          {PATTERN_LABELS[p] || p}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {selected.temporal_profile && (
                  <div className="panel-section">
                    <span className="meta-label">Temporal Profile</span>
                    <div className="temporal-bar-chart">
                      {selected.temporal_profile.hourly_distribution.map((count, hour) => {
                        const maxCount = Math.max(...selected.temporal_profile.hourly_distribution, 1)
                        const heightPct = (count / maxCount) * 100
                        const isPeak = hour === selected.temporal_profile.peak_hour
                        return (
                          <div
                            key={hour}
                            className={`temporal-bar ${isPeak ? 'peak' : ''}`}
                            style={{ '--bar-height': `${Math.max(heightPct, 2)}%` }}
                            title={`${hour}:00 — ${count} tx${isPeak ? ' (peak)' : ''}`}
                          />
                        )
                      })}
                    </div>
                    <div className="temporal-meta">
                      <span>Peak: {selected.temporal_profile.peak_hour}:00</span>
                      <span>{selected.temporal_profile.active_hours}/24h active</span>
                    </div>
                  </div>
                )}
              </>
            )}

            {selected.community_id != null && (
              <div className="panel-section">
                <span className="meta-label">Community</span>
                <span className="community-badge">Community #{selected.community_id}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Stats footer ──────────────────────────────────── */}
      <div className="graph-footer">
        <span>{processedData.nodes.length} nodes</span>
        <span className="graph-footer-sep">•</span>
        <span>{processedData.links.length} edges</span>
        <span className="graph-footer-sep">•</span>
        <span className="text-danger">{suspiciousCount} flagged</span>
        {highlightRing && (
          <>
            <span className="graph-footer-sep">•</span>
            <span className="text-accent">Highlighting: {highlightRing}</span>
          </>
        )}
      </div>
    </div>
  )
}
