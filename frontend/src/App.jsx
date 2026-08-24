import React, { useState, useEffect, useRef } from 'react'
import { fetchHealth, fetchConfig, listSessions, createSession, deleteSession, listMessages, streamChat } from './lib/api'
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
  const streamRef = useRef(null)

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
        setStreamingText(prev => prev + `\n\n> ⚠️ ${d.detail || 'Error'}`)
      },
    })
    streamRef.current = ctrl
  }

  // keep ref for onDone closure
  const streamingTextRef = useRef('')
  useEffect(() => { streamingTextRef.current = streamingText }, [streamingText])

  const providerLabel = config?.provider?.selected || health?.provider?.selected || 'ollama'
  const ollamaOk = health?.ollama_reachable
  const dbOk = health?.db_ok

  return (
    <div className="flex h-screen w-screen flex-col bg-zinc-50">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-4">
        <div className="flex items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-zinc-900 text-[11px] font-bold text-white">LP</div>
          <div>
            <h1 className="text-sm font-semibold leading-none">Lenny Growth Assistant</h1>
            <p className="text-[11px] text-zinc-500">Grounded in Lenny’s Podcast transcripts • cites sources</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className={`rounded-full border px-2.5 py-1 font-medium ${ollamaOk ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700'}`}>
            {providerLabel.toUpperCase()} • {ollamaOk ? 'reachable' : health ? 'Ollama not reachable' : 'checking…'}
          </span>
          <span className={`hidden rounded-full border px-2.5 py-1 text-zinc-600 sm:inline ${dbOk ? 'border-zinc-200 bg-white' : 'border-red-200 bg-red-50 text-red-700'}`}>{dbOk ? 'DB connected' : 'DB degraded'}</span>
          <span className="hidden text-zinc-400 sm:inline">v{health?.version || config?.provider?.vector_dim || '1.0.0'}</span>
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

              <div className="shrink-0 border-t border-zinc-200 bg-white p-3">
                <div className="mx-auto flex max-w-3xl flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
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

                  <div className="flex items-end gap-2">
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

        {showArtifact && artifact && (
          <div className="hidden w-[520px] shrink-0 border-l border-zinc-200 bg-white xl:flex xl:flex-col">
            <ArtifactViewer artifact={artifact} onClose={() => setShowArtifact(false)} />
          </div>
        )}
      </div>

      {/* Mobile artifact drawer */}
      {showArtifact && artifact && (
        <div className="fixed inset-0 z-40 flex flex-col bg-white xl:hidden">
          <div className="flex h-12 items-center justify-between border-b px-4">
            <span className="text-sm font-semibold">Artifact</span>
            <button onClick={() => setShowArtifact(false)} className="rounded-xl border px-3 py-1.5 text-sm">Close</button>
          </div>
          <div className="flex-1 overflow-hidden"><ArtifactViewer artifact={artifact} /></div>
        </div>
      )}

      {/* Mobile session toggle could be added */}
    </div>
  )
}
