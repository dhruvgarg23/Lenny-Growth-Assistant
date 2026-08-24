import React from 'react'

export default function SessionSidebar({ sessions, activeId, onSelect, onNew, onDelete }) {
  return (
    <div className="flex h-full w-[300px] shrink-0 flex-col border-r border-zinc-200 bg-white">
      <div className="border-b border-zinc-200 p-3">
        <button onClick={onNew} className="w-full rounded-xl bg-zinc-900 px-3 py-2.5 text-sm font-medium text-white hover:bg-zinc-800">+ New chat</button>
      </div>
      <div className="flex-1 overflow-auto p-2">
        {sessions.length === 0 && <p className="p-3 text-xs text-zinc-400">No chats yet. Start a new one.</p>}
        <div className="flex flex-col gap-1">
          {sessions.map(s => (
            <button
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm hover:bg-zinc-50 ${activeId === s.id ? 'bg-zinc-100 font-medium' : ''}`}
            >
              <span className="truncate pr-2">{s.title || 'New chat'}</span>
              <span className="shrink-0 text-[11px] text-zinc-400">{s.message_count ?? 0}</span>
            </button>
          ))}
        </div>
      </div>
      {activeId && (
        <div className="border-t border-zinc-200 p-3">
          <button onClick={() => onDelete(activeId)} className="w-full rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-100">Delete chat</button>
        </div>
      )}
    </div>
  )
}
