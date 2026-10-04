const API = import.meta.env.VITE_API_URL || '/api'

export async function fetchHealth() {
  const r = await fetch(`${API}/health`)
  if (!r.ok) throw new Error(`Health ${r.status}`)
  return r.json()
}
export async function fetchConfig() {
  const r = await fetch(`${API}/config`)
  return r.json()
}
export async function listSessions() {
  const r = await fetch(`${API}/sessions`)
  return r.json()
}
export async function createSession(title = 'New chat') {
  const r = await fetch(`${API}/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
export async function deleteSession(id) {
  const r = await fetch(`${API}/sessions/${id}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
export async function listMessages(sessionId) {
  const r = await fetch(`${API}/sessions/${sessionId}/messages`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

// SSE chat — returns EventSource-like controller that calls callbacks
export function streamChat(sessionId, payload, handlers) {
  const url = `${API}/sessions/${sessionId}/chat/stream`
  const ctrl = new AbortController()
  let buf = ''
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(payload),
    signal: ctrl.signal,
  }).then(async (res) => {
    if (!res.ok) {
      const txt = await res.text().catch(() => '')
      handlers.onError?.({ detail: txt || `HTTP ${res.status}` })
      return
    }
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      // Parse SSE frames: event: X\ndata: {...}\n\n
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const frame = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const lines = frame.split('\n')
        let event = 'message'
        let data = ''
        for (const l of lines) {
          if (l.startsWith('event:')) event = l.slice(6).trim()
          else if (l.startsWith('data:')) data += l.slice(5).trim()
        }
        let parsed
        try { parsed = JSON.parse(data || '{}') } catch { parsed = { raw: data } }
        if (event === 'status') handlers.onStatus?.(parsed)
        else if (event === 'sources') handlers.onSources?.(parsed)
        else if (event === 'token') handlers.onToken?.(parsed)
        else if (event === 'artifact') handlers.onArtifact?.(parsed)
        else if (event === 'done') handlers.onDone?.(parsed)
        else if (event === 'error') handlers.onError?.(parsed)
        else handlers.onError?.({ detail: `Unknown SSE event: ${event}` })
      }
    }
  }).catch((e) => {
    if (e.name !== 'AbortError') handlers.onError?.({ detail: e.message })
  })
  return { abort: () => ctrl.abort() }
}

export async function switchModel(provider, model) {
  const r = await fetch(`${API}/config/model`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, model }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }))
    throw new Error(err.detail || 'Failed to switch model')
  }
  return r.json()
}

export { API }
