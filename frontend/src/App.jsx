import React, { useState, useEffect, useRef } from 'react'
import { fetchHealth, fetchConfig, listSessions, createSession, deleteSession, listMessages, streamChat, switchModel } from './lib/api'
import SessionSidebar from './components/SessionSidebar'
import ChatPane from './components/ChatPane'
import ArtifactViewer from './components/ArtifactViewer'

export default function App() {
  const [health, setHealth] = useState(null)
  const [config, setConfig] = useState(null)
  const [sessions, setSessions] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [mode, setMode] = useState('chat') // chat | ship30 | artifact
  const [artifactType, setArtifactType] = useState('markdown')
  const [streamingText, setStreamingText] = useState('')
  const [streamingSources, setStreamingSources] = useState([])
  const [status, setStatus] = useState('')
  const [artifact, setArtifact] = useState(null)
  const [showArtifact, setShowArtifact] = useState(true)
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [switching, setSwitching] = useState(false)
  const streamRef = useRef(null)
  const modelMenuRef = useRef(null)

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => setHealth({ status: 'unknown' }))
    fetchConfig().then(setConfig).catch(() => {})
    refreshSessions()
  }, [])

  async function refreshSessions() {
    try {
      const s = await listSessions()
      setSessions(s)
      if (!activeId && s.length > 0) setActiveId(s[0].id)
    } catch {}
  }

  useEffect(() => {
    if (!activeId) { setMessages([]); return }
    listMessages(activeId).then(setMessages).catch(() => setMessages([]))
    setArtifact(null)
    setStreamingText('')
    setStreamingSources([])
  }, [activeId])

  async function handleNew() {
    const s = await createSession()
    await refreshSessions()
    setActiveId(s.id)
  }

  async function handleDelete(id) {
    if (!confirm('Delete this chat?')) return
    await deleteSession(id)
    const remaining = sessions.filter(x => x.id !== id)
    setSessions(remaining)
    setActiveId(remaining[0]?.id || null)
  }

  function handleSend() {
    if (!input.trim() || !activeId) return
    const text = input.trim()
    const payload = { message: text, mode, artifact_type: mode === 'artifact' ? artifactType : undefined }
    // optimistic user
    const tmpId = 'tmp-' + Date.now()
    setMessages(prev => [...prev, { id: tmpId, role: 'user', content: text, sources: [] }])
    setInput('')
    setStreamingText('')
    setStreamingSources([])
    setStatus(mode === 'ship30' ? 'Drafting essay…' : mode === 'artifact' ? 'Generating artifact…' : 'Thinking…')
    setArtifact(null)

    const ctrl = streamChat(activeId, payload, {
      onStatus: (d) => setStatus(d.message || d.stage || ''),
      onSources: (d) => { setStreamingSources(d.sources || []); setStatus('Drafting answer…') },
      onToken: (d) => setStreamingText(prev => prev + (d.delta || '')),
      onArtifact: (d) => { setArtifact(d.artifact); setShowArtifact(true) },
      onDone: (d) => {
        setStatus('')
        const final = streamingTextRef.current || ''
        // reload from server to get persisted message
        listMessages(activeId).then(msgs => {
          setMessages(msgs)
          // preserve artifact if returned
          if (d.artifact) { setArtifact(d.artifact); setShowArtifact(true) }
          else {
            const last = msgs[msgs.length - 1]
            if (last?.artifact) { setArtifact(last.artifact); setShowArtifact(true) }
          }
        })
        setStreamingText('')
        setStreamingSources([])
        refreshSessions()
      },
      onError: (d) => {
        setStatus('')
        const reqStr = d.request_id && d.request_id !== '-' ? `\n> _Request ID: \`${d.request_id}\`_` : ''
        setStreamingText(prev => prev + `\n\n> ⚠️ **Error:** ${d.detail || 'Failed to generate response'}${reqStr}`)
      },
    })
    streamRef.current = ctrl
  }

  // keep ref for onDone closure
  const streamingTextRef = useRef('')
  useEffect(() => { streamingTextRef.current = streamingText }, [streamingText])

  // Close model menu on outside click
  useEffect(() => {
    function handleClick(e) {
      if (modelMenuRef.current && !modelMenuRef.current.contains(e.target)) setModelMenuOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  async function handleModelSwitch(provider, model) {
    setSwitching(true)
    try {
      await switchModel(provider, model)
      // Refresh config to get updated runtime state
      const [h, c] = await Promise.all([fetchHealth(), fetchConfig()])
      setHealth(h)
      setConfig(c)
    } catch (e) {
      alert(`Failed to switch: ${e.message}`)
    } finally {
      setSwitching(false)
      setModelMenuOpen(false)
    }
  }

  const runtimeState = config?.runtime || health?.runtime
  const providerLabel = runtimeState?.provider || config?.provider?.selected || 'ollama'
  const selectedModel = runtimeState?.model || config?.provider?.selected_model || ''
  const groqConfigured = runtimeState?.groq_configured ?? config?.provider?.groq_configured
  const anthropicConfigured = runtimeState?.anthropic_configured ?? config?.provider?.anthropic_configured
  const ollamaOk = health?.ollama_reachable
  const dbOk = health?.db_ok
  const isAnthropic = providerLabel === 'anthropic'
  const isGroq = providerLabel === 'groq'
  const isCloud = isAnthropic || isGroq
  const cloudConfigured = isAnthropic ? anthropicConfigured : (isGroq ? groqConfigured : false)
  const badgeColor = isCloud ? (cloudConfigured ? 'emerald' : 'amber') : (ollamaOk ? 'emerald' : 'amber')
  const statusText = isAnthropic
    ? (anthropicConfigured ? 'cloud' : health ? 'key missing' : 'checking…')
    : isGroq
    ? (groqConfigured ? 'cloud' : health ? 'key missing' : 'checking…')
    : (ollamaOk ? 'local' : health ? 'not reachable' : 'checking…')
  const allowedModels = runtimeState?.allowed_models || config?.allowed_models || {}

  return (
    <div className="flex h-dvh w-full flex-col bg-zinc-50">
      <header className="flex min-h-12 shrink-0 items-center justify-between gap-2 border-b border-zinc-200 bg-white px-4 pt-[env(safe-area-inset-top)]">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <button onClick={() => setSidebarOpen(true)} aria-label="Open sessions" className="shrink-0 rounded-lg border border-zinc-200 px-2 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50 md:hidden">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
          </button>
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-zinc-900 text-[11px] font-bold text-white">LP</div>
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold leading-none">Lenny Growth Assistant</h1>
            <p className="truncate text-[11px] text-zinc-500">Grounded in Lenny’s Podcast transcripts • cites sources</p>
          </div>
        </div>
        <div className="flex min-w-0 shrink-0 items-center gap-2 text-xs">
          <div className="relative" ref={modelMenuRef}>
            <button
              onClick={() => setModelMenuOpen(v => !v)}
              disabled={switching}
              title="Click to switch model"
              className={`flex min-w-0 items-center gap-1.5 rounded-full border px-2.5 py-1 font-medium cursor-pointer transition-colors ${badgeColor === 'emerald' ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100' : 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100'}`}
            >
              {switching ? '⟳ switching…' : (<><span className="max-w-[38vw] truncate sm:max-w-64">{`${providerLabel.toUpperCase()} • ${selectedModel || '—'}`}</span><span className="shrink-0">• {statusText}</span></>)}
              <svg className="h-3 w-3 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
            </button>
            {modelMenuOpen && (
              <div className="absolute end-0 top-full z-50 mt-1 w-72 max-w-[calc(100vw-2rem)] rounded-xl border border-zinc-200 bg-white py-1 shadow-lg">
                {Object.entries(allowedModels).map(([prov, models]) => (
                  <div key={prov}>
                    <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
                      {prov === 'anthropic' ? '🧠 Anthropic Claude (Cloud)' : prov === 'groq' ? '⚡ Groq (Cloud)' : '🖥️ Ollama (Local)'}
                    </div>
                    {(models || []).map(m => {
                      const isActive = prov === providerLabel && m === selectedModel
                      return (
                        <button
                          key={`${prov}-${m}`}
                          onClick={() => handleModelSwitch(prov, m)}
                          className={`flex w-full items-center gap-2 break-words px-3 py-2 text-start text-xs hover:bg-zinc-50 ${
                            isActive ? 'bg-zinc-100 font-semibold text-zinc-900' : 'text-zinc-700'
                          }`}
                        >
                          <span className={`h-1.5 w-1.5 rounded-full ${isActive ? 'bg-emerald-500' : 'bg-transparent'}`} />
                          {m}
                        </button>
                      )
                    })}
                  </div>
                ))}
              </div>
            )}
          </div>
          <span className={`rounded-full border px-2.5 py-1 text-zinc-600 ${dbOk ? 'border-zinc-200 bg-white' : 'border-red-200 bg-red-50 text-red-700'}`}>{dbOk ? 'DB connected' : 'DB degraded'}</span>
          <span className="hidden text-zinc-400 sm:inline">v{health?.version || '1.0.0'}</span>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <div className="hidden md:flex">
          <SessionSidebar sessions={sessions} activeId={activeId} onSelect={setActiveId} onNew={handleNew} onDelete={handleDelete} />
        </div>

        <div className="flex min-w-0 flex-1 flex-col">
          {!activeId ? (
            <div className="flex flex-1 items-center justify-center p-8">
              <div className="text-center">
                <p className="text-sm text-zinc-500">No session. Create one to start.</p>
                <button onClick={handleNew} className="mt-3 rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white">+ New chat</button>
              </div>
            </div>
          ) : (
            <>
              <div className="min-h-0 flex-1">
                <ChatPane messages={messages} streamingText={streamingText} streamingSources={streamingSources} status={status} onExample={(q) => setInput(q)} />
              </div>

              <div className="shrink-0 border-t border-zinc-200 bg-white p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
                <div className="mx-auto flex max-w-2xl flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-3 text-xs">
                    <div className="flex rounded-full border border-zinc-200 p-1">
                      {[
                        ['chat', 'Chat'],
                        ['ship30', 'Ship 30 essay'],
                        ['artifact', 'Artifact'],
                      ].map(([k, label]) => (
                        <button key={k} onClick={() => setMode(k)} className={`rounded-full px-3 py-1 font-medium ${mode === k ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-50'}`}>{label}</button>
                      ))}
                    </div>
                    {mode === 'artifact' && (
                      <div className="flex rounded-full border border-zinc-200 p-1">
                        {['markdown','html'].map(t => (
                          <button key={t} onClick={() => setArtifactType(t)} className={`rounded-full px-3 py-1 font-medium ${artifactType === t ? 'bg-zinc-900 text-white' : 'text-zinc-600'}`}>{t}</button>
                        ))}
                      </div>
                    )}
                    {artifact && (
                      <button onClick={() => setShowArtifact(v => !v)} className="rounded-full border border-zinc-200 px-3 py-1 font-medium hover:bg-zinc-50">
                        {showArtifact ? 'Hide artifact' : 'Show artifact'}
                      </button>
                    )}
                    <span className="text-zinc-400">Enter to send • Shift+Enter newline</span>
                  </div>

                  <div className="flex items-end gap-3">
                    <textarea
                      value={input}
                      onChange={e => setInput(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
                      }}
                      placeholder={mode === 'ship30' ? 'Topic for a ~1,250-word Ship 30 essay (e.g., How Lenny guests think about retention loops)' : mode === 'artifact' ? 'Describe the artifact (e.g., Artifact: HTML one-pager comparing PLG vs sales-led motions)' : 'Ask anything grounded in Lenny transcripts…'}
                      rows={2}
                      className="max-h-32 min-h-[44px] flex-1 resize-none rounded-2xl border border-zinc-300 bg-white px-4 py-3 text-sm placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-none focus:ring-1 focus:ring-zinc-900"
                    />
                    <button onClick={handleSend} disabled={!input.trim()} className="rounded-2xl bg-zinc-900 px-5 py-3 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-40">Send</button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Dock the artifact beside chat once sidebar (300) + panel (~440) + readable chat fit, ≈1200px */}
        {showArtifact && artifact && (
          <div className="hidden w-[min(440px,36vw)] shrink-0 border-s border-zinc-200 bg-white min-[1200px]:flex min-[1200px]:flex-col">
            <ArtifactViewer artifact={artifact} onClose={() => setShowArtifact(false)} />
          </div>
        )}
      </div>

      {/* Mobile sessions drawer */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button aria-label="Close sessions" onClick={() => setSidebarOpen(false)} className="absolute inset-0 cursor-default bg-zinc-900/40" />
          <div className="absolute inset-y-0 start-0 flex w-[300px] max-w-[85vw] shadow-xl">
            <SessionSidebar sessions={sessions} activeId={activeId} onSelect={(id) => { setActiveId(id); setSidebarOpen(false) }} onNew={async () => { await handleNew(); setSidebarOpen(false) }} onDelete={handleDelete} />
          </div>
        </div>
      )}

      {/* Mobile artifact drawer */}
      {showArtifact && artifact && (
        <div className="fixed inset-0 z-40 flex flex-col bg-white min-[1200px]:hidden">
          <div className="flex min-h-12 items-center justify-between border-b px-4 pt-[env(safe-area-inset-top)]">
            <span className="text-sm font-semibold">Artifact</span>
            <button onClick={() => setShowArtifact(false)} className="rounded-xl border px-3 py-1.5 text-sm">Close</button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden pb-[env(safe-area-inset-bottom)]"><ArtifactViewer artifact={artifact} /></div>
        </div>
      )}
    </div>
  )
}
