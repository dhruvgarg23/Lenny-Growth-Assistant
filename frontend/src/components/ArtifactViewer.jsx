import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function ArtifactViewer({ artifact, onClose }) {
  // Markdown-only artifacts: rendered with the client's Markdown renderer,
  // so no HTML sanitization or sandboxed iframe is needed.
  const content = artifact?.content || ''

  if (!artifact) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-zinc-400 text-sm">
        <div>
          <div className="text-3xl mb-2">◧</div>
          <p className="font-medium">No artifact yet</p>
          <p className="text-zinc-400">Ask for a “markdown doc” and it will render here.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex items-center justify-between border-b border-zinc-200 px-3 py-2 text-xs">
        <span className="rounded-full bg-zinc-900 px-2.5 py-1 font-medium text-white">MARKDOWN artifact</span>
        <div className="flex gap-3">
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
          <div className="prose prose-zinc max-w-none p-6 prose-headings:font-semibold prose-a:text-blue-600">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  )
}
