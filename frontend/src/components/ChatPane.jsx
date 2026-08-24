import React, { useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function SourceChips({ sources }) {
  if (!sources?.length) return null
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {sources.slice(0, 6).map((s, i) => (
        <span key={s.chunk_id || i} className="inline-flex max-w-[260px] truncate rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-[11px] font-medium text-zinc-600" title={`${s.title} — ${s.source_path}`}>
          {s.title?.slice(0, 36) || s.source_path?.split('/').pop()} {s.guest ? `· ${s.guest.split(' ')[0]}` : ''}
        </span>
      ))}
      {sources.length > 6 && <span className="text-[11px] text-zinc-400">+{sources.length - 6} more</span>}
    </div>
  )
}

export default function ChatPane({ messages, streamingText, streamingSources, status, onExample }) {
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, streamingText, status])

  const hasMessages = messages.length > 0 || streamingText

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-auto px-4 py-6">
        {!hasMessages && (
          <div className="mx-auto max-w-2xl">
            <div className="rounded-2xl border border-zinc-200 bg-white p-6">
              <h2 className="text-lg font-semibold">Ask grounded product & growth questions</h2>
              <p className="mt-1 text-sm text-zinc-500">Answers cite Lenny’s Podcast transcripts. Try one:</p>
              <div className="mt-4 grid gap-2">
                {[
                  'How should we improve onboarding activation in the first 7 days?',
                  'What does Lenny’s Podcast recommend for PLG pricing vs. sales-led?',
                  'Summarize advice on building a product-led growth engine',
                ].map(q => (
                  <button key={q} onClick={() => onExample(q)} className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 text-left text-sm hover:bg-zinc-100">{q}</button>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2 text-xs">
                <span className="rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-violet-700">Tip: add “ship 30” for a 1,250-word essay</span>
                <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-sky-700">Or “artifact: HTML one-pager” to render beside chat</span>
              </div>
            </div>
          </div>
        )}

        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          {messages.map(m => (
            <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`${m.role === 'user' ? 'max-w-[80%] rounded-2xl bg-zinc-900 px-4 py-3 text-white' : 'max-w-[90%] rounded-2xl border border-zinc-200 bg-white px-4 py-3'} `}>
                {m.role === 'assistant' ? (
                  <div className="prose prose-zinc prose-sm max-w-none prose-p:leading-relaxed prose-headings:font-semibold">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{m.content}</p>
                )}
                {m.sources?.length > 0 && <SourceChips sources={m.sources} />}
                {m.artifact && <div className="mt-2 text-xs text-zinc-500">↗ Artifact: {m.artifact.type}</div>}
              </div>
            </div>
          ))}

          {streamingText && (
            <div className="flex justify-start">
              <div className="max-w-[90%] rounded-2xl border border-zinc-200 bg-white px-4 py-3">
                <div className="prose prose-zinc prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingText}</ReactMarkdown>
                </div>
                {streamingSources?.length > 0 && <SourceChips sources={streamingSources} />}
              </div>
            </div>
          )}

          {status && <div className="flex items-center gap-2 text-xs text-zinc-500"><span className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />{status}</div>}

          <div ref={endRef} />
        </div>
      </div>
    </div>
  )
}
