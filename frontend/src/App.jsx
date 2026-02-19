import { useState, useEffect } from 'react'
import FileUpload from './components/FileUpload'
import GraphVisualization from './components/GraphVisualization'
import SummaryTable from './components/SummaryTable'
import DownloadButton from './components/DownloadButton'
import SummaryStats from './components/SummaryStats'
import './App.css'

const TABS = [
  { key: 'graph',    icon: '◉', label: 'Network Graph' },
  { key: 'rings',    icon: '⬡', label: 'Fraud Rings' },
  { key: 'accounts', icon: '⚑', label: 'Suspicious Accounts' },
]

export default function App() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('graph')
  const [theme, setTheme] = useState(() => localStorage.getItem('ffe-theme') || 'dark')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('ffe-theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

  const ringCount = result?.fraud_rings?.length ?? 0
  const accountCount = result?.suspicious_accounts?.length ?? 0

  return (
    <div className="app">
      {/* ── Ambient orbs ───────────────────────────────────── */}
      <div className="ambient-orb orb-1" />
      <div className="ambient-orb orb-2" />

      {/* ── Header ─────────────────────────────────────────── */}
      <header className="header">
        <div className="container header-inner">
          <div className="logo-group">
            <div className="logo-mark">
              <svg viewBox="0 0 32 32" fill="none" className="logo-svg">
                <rect x="2" y="2" width="28" height="28" rx="8" stroke="url(#grd)" strokeWidth="2" />
                <circle cx="11" cy="13" r="3" fill="#c084fc" />
                <circle cx="21" cy="13" r="3" fill="#f43f5e" />
                <circle cx="16" cy="22" r="3" fill="#f59e0b" />
                <line x1="13.5" y1="14.5" x2="18.5" y2="14.5" stroke="#c084fc" strokeWidth="1.2" />
                <line x1="12" y1="15.5" x2="14.5" y2="20" stroke="#f59e0b" strokeWidth="1.2" />
                <line x1="20" y1="15.5" x2="17.5" y2="20" stroke="#f43f5e" strokeWidth="1.2" />
                <defs><linearGradient id="grd" x1="0" y1="0" x2="32" y2="32"><stop stopColor="#a855f7"/><stop offset="1" stopColor="#f59e0b"/></linearGradient></defs>
              </svg>
            </div>
            <div className="logo-text">
              <h1 className="logo-title">Financial Forensics Engine</h1>
              <p className="logo-subtitle">Advanced Money Muling Network Detection</p>
            </div>
          </div>

          <div className="header-actions">
            {result && (
              <>
                <div className="header-badge">
                  <span className="badge-dot pulse" />
                  {ringCount} ring{ringCount !== 1 ? 's' : ''} detected
                </div>
                <DownloadButton result={result} />
              </>
            )}
            <button
              className="theme-toggle"
              onClick={toggleTheme}
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="5"/>
                  <line x1="12" y1="1" x2="12" y2="3"/>
                  <line x1="12" y1="21" x2="12" y2="23"/>
                  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                  <line x1="1" y1="12" x2="3" y2="12"/>
                  <line x1="21" y1="12" x2="23" y2="12"/>
                  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                </svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                </svg>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* ── Main ───────────────────────────────────────────── */}
      <main className="main">
        <div className="container main-content">
          {/* Upload Section */}
          <FileUpload
            onResult={setResult}
            onLoading={setLoading}
            onError={setError}
            loading={loading}
          />

          {/* Error Banner */}
          {error && (
            <div className="error-banner animate-in">
              <div className="error-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.5"/>
                  <line x1="10" y1="6" x2="10" y2="11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                  <circle cx="10" cy="14" r="1" fill="currentColor"/>
                </svg>
              </div>
              <span className="error-text">{error}</span>
              <button className="error-dismiss" onClick={() => setError(null)}>✕</button>
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="loading-card animate-in">
              <div className="loading-visual">
                <div className="spinner-ring" />
                <div className="spinner-ring inner" />
              </div>
              <div className="loading-text">
                <h3>Analyzing Transaction Network</h3>
                <p className="loading-sub">Running cycle detection, smurfing analysis &amp; shell network scan…</p>
              </div>
              <div className="loading-steps">
                <span className="step active">Parsing CSV</span>
                <span className="step-arrow">→</span>
                <span className="step">Building Graph</span>
                <span className="step-arrow">→</span>
                <span className="step">Detecting Patterns</span>
                <span className="step-arrow">→</span>
                <span className="step">Scoring</span>
              </div>
            </div>
          )}

          {/* Results */}
          {result && !loading && (
            <div className="results animate-in">
              {/* Parse Stats Banner */}
              {result.parse_stats && (
                <div className="parse-banner">
                  <span className="parse-label">Parse Summary</span>
                  <div className="parse-stats-row">
                    <span>{result.parse_stats.total_rows} total rows</span>
                    <span className="parse-sep">•</span>
                    <span className="parse-good">{result.parse_stats.valid_rows} valid</span>
                    {result.parse_stats.dropped_rows > 0 && (
                      <>
                        <span className="parse-sep">•</span>
                        <span className="parse-warn">{result.parse_stats.dropped_rows} dropped</span>
                      </>
                    )}
                    {result.parse_stats.duplicate_tx_ids > 0 && (
                      <>
                        <span className="parse-sep">•</span>
                        <span className="parse-warn">{result.parse_stats.duplicate_tx_ids} duplicates</span>
                      </>
                    )}
                    {result.parse_stats.self_transactions > 0 && (
                      <>
                        <span className="parse-sep">•</span>
                        <span className="parse-warn">{result.parse_stats.self_transactions} self-transfers</span>
                      </>
                    )}
                    {result.parse_stats.negative_amounts > 0 && (
                      <>
                        <span className="parse-sep">•</span>
                        <span className="parse-warn">{result.parse_stats.negative_amounts} negative amounts</span>
                      </>
                    )}
                  </div>
                </div>
              )}

              {/* Summary Statistics */}
              <SummaryStats summary={result.summary} />

              {/* Tabs */}
              <div className="tabs-container">
                <div className="tabs">
                  {TABS.map(tab => (
                    <button
                      key={tab.key}
                      className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
                      onClick={() => setActiveTab(tab.key)}
                    >
                      <span className="tab-icon">{tab.icon}</span>
                      <span className="tab-label">{tab.label}</span>
                      {tab.key === 'rings' && ringCount > 0 && (
                        <span className="tab-badge danger">{ringCount}</span>
                      )}
                      {tab.key === 'accounts' && accountCount > 0 && (
                        <span className="tab-badge warning">{accountCount}</span>
                      )}
                    </button>
                  ))}
                </div>

                <div className="tab-panel">
                  {activeTab === 'graph' && (
                    <GraphVisualization graphData={result.graph} rings={result.fraud_rings} />
                  )}
                  {activeTab === 'rings' && (
                    <SummaryTable rings={result.fraud_rings} type="rings" />
                  )}
                  {activeTab === 'accounts' && (
                    <SummaryTable accounts={result.suspicious_accounts} type="accounts" />
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* ── Footer ─────────────────────────────────────────── */}
      <footer className="footer">
        <div className="container footer-inner">
          <span>Financial Forensics Engine v2.0.0</span>
          <span className="footer-sep">•</span>
          <span>Graph-based money muling detection</span>
        </div>
      </footer>
    </div>
  )
}
