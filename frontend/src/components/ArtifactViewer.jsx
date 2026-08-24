import React, { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import DOMPurify from 'dompurify'

export default function ArtifactViewer({ artifact, onClose }) {
  const sanitized = useMemo(() => {
    if (!artifact) return null
    if (artifact.type === 'html') {
      // Client-side DOMPurify defense-in-depth (backend already sanitized)
      const cfg = {
        ALLOWED_TAGS: ['h1','h2','h3','h4','h5','h6','p','br','hr','ul','ol','li','strong','em','b','i','u','a','blockquote','code','pre','span','div','section','article','header','footer','main','table','thead','tbody','tr','th','td','style'],
        ALLOWED_ATTR: ['href','title','target','rel','class','colspan','rowspan'],
        ALLOW_DATA_ATTR: false,
        FORBID_TAGS: ['script','iframe','object','embed','form','meta','link','base'],
        FORBID_ATTR: ['onerror','onload','onclick','onmouseover','style'],
      }
      // Allow style blocks but strip dangerous CSS via hook
      let html = artifact.content || ''
      // DOMPurify will keep <style> if we allow it, then we extra-strip url/@import via regex
      html = html.replace(/@import/gi, '').replace(/url\(/gi, '(blocked-url')
      const clean = DOMPurify.sanitize(html, cfg)
      return clean
    }
    return artifact.content
  }, [artifact])

  if (!artifact) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-zinc-400 text-sm">
        <div>
          <div className="text-3xl mb-2">◧</div>
          <p className="font-medium">No artifact yet</p>
          <p className="text-zinc-400">Ask for a “markdown doc” or “HTML one-pager” and it will render here.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex items-center justify-between border-b border-zinc-200 px-3 py-2 text-xs">
        <span className="rounded-full bg-zinc-900 px-2.5 py-1 font-medium text-white">{artifact.type.toUpperCase()} artifact</span>
        <div className="flex gap-2">
          <button
            onClick={() => {
              navigator.clipboard.writeText(artifact.content)
            }}
            className="rounded-md border border-zinc-200 px-2.5 py-1 font-medium hover:bg-zinc-50"
          >
            Copy
          </button>
          {onClose && (
            <button onClick={onClose} className="rounded-md border border-zinc-200 px-2.5 py-1 font-medium hover:bg-zinc-50">Close</button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-zinc-50 p-3">
        <div className="mx-auto min-h-full rounded-xl border border-zinc-200 bg-white shadow-sm">
          {artifact.type === 'markdown' ? (
            <div className="prose prose-zinc max-w-none p-6 prose-headings:font-semibold prose-a:text-blue-600">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{artifact.content}</ReactMarkdown>
            </div>
          ) : (
            // Sandboxed iframe — no allow-same-origin, no cookies leaked
            <iframe
              title="artifact"
              sandbox="allow-scripts allow-popups"
              referrerPolicy="no-referrer"
              srcDoc={sanitized}
              className="h-[70vh] min-h-[520px] w-full rounded-xl"
            />
          )}
        </div>
        {/* Security note */}
        <p className="mx-auto mt-3 max-w-3xl text-[11px] leading-relaxed text-zinc-400">
          Rendered as untrusted content: scripts run without <code>allow-same-origin</code>, external resources and forms are blocked, HTML is sanitized with DOMPurify + server-side bleach. CSP and sandbox contain malicious output.
        </p>
      </div>
    </div>
  )
}
