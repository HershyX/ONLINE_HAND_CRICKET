/**
 * ChatPanel — shared between RoomPage and GamePage.
 * Supports global (all players) and team-scoped messages.
 * Chat history is seeded from room.chat_messages on reconnect and
 * supplemented by live messages in store.chatMessages.
 */
import { useEffect, useRef, useState } from 'react'
import { MessageCircle, Send, Globe, Lock } from 'lucide-react'
import clsx from 'clsx'
import { useGameStore } from '../state/gameStore'
import type { Room } from '../types'

export function ChatPanel({ room, playerId, className }: { room: Room; playerId: string | null; className?: string }) {
  const sendChat    = useGameStore((s) => s.sendChat)
  const chatMessages = useGameStore((s) => s.chatMessages)

  const [scope, setScope] = useState<'global' | 'team'>('global')
  const [draft, setDraft]  = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  const myTeamId = playerId ? room.players[playerId]?.team_id : null

  // Merge server snapshot + live messages, deduped by id, sorted by time
  const allMessages = [
    ...room.chat_messages,
    ...chatMessages.filter((m) => !room.chat_messages.find((rm) => rm.id === m.id)),
  ].sort((a, b) => a.timestamp.localeCompare(b.timestamp))

  const visible = allMessages.filter((m) =>
    m.scope === 'global' || m.team_id === myTeamId
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [visible.length])

  const send = () => {
    const content = draft.trim()
    if (!content) return
    sendChat(content, scope)
    setDraft('')
  }

  return (
    <div
      className={clsx(
        'bg-surface-800 border border-white/5 rounded-2xl flex flex-col overflow-hidden',
        className,
      )}
      style={className ? undefined : { height: '260px' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/5 flex-shrink-0">
        <div className="flex items-center gap-2">
          <MessageCircle className="w-3.5 h-3.5 text-white/40" />
          <span className="text-xs font-semibold text-white/50 uppercase tracking-widest">Chat</span>
        </div>
        <div className="flex items-center gap-1 bg-surface-700 rounded-lg p-0.5">
          <button
            onClick={() => setScope('global')}
            className={clsx(
              'flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-all',
              scope === 'global' ? 'bg-brand-500 text-white' : 'text-white/40 hover:text-white',
            )}
          >
            <Globe className="w-3 h-3" /> All
          </button>
          <button
            onClick={() => setScope('team')}
            className={clsx(
              'flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-all',
              scope === 'team' ? 'bg-purple-600 text-white' : 'text-white/40 hover:text-white',
            )}
          >
            <Lock className="w-3 h-3" /> Team
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5 min-h-0">
        {visible.length === 0 && (
          <p className="text-white/20 text-xs text-center pt-4">No messages yet</p>
        )}
        {visible.map((msg) => {
          const isMe   = msg.player_id === playerId
          const isTeam = msg.scope === 'team'
          return (
            <div key={msg.id} className={clsx('flex flex-col', isMe ? 'items-end' : 'items-start')}>
              <div
                className={clsx(
                  'max-w-[82%] rounded-xl px-3 py-1.5 text-sm',
                  isMe
                    ? isTeam ? 'bg-purple-600/70 text-white' : 'bg-brand-500/70 text-white'
                    : isTeam ? 'bg-purple-500/20 text-white/90' : 'bg-surface-600 text-white/90',
                )}
              >
                {!isMe && (
                  <p className={clsx('text-[10px] font-bold mb-0.5', isTeam ? 'text-purple-300' : 'text-brand-300')}>
                    {msg.display_name}
                  </p>
                )}
                <p className="break-words leading-snug">{msg.content}</p>
              </div>
              {isTeam && (
                <span className="text-[9px] text-white/20 mt-0.5 flex items-center gap-0.5">
                  <Lock className="w-2 h-2" /> team only
                </span>
              )}
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-white/5 flex-shrink-0">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send() }}
          placeholder={scope === 'team' ? 'Team message…' : 'Message everyone…'}
          maxLength={200}
          className={clsx(
            'flex-1 bg-surface-700 border rounded-xl px-3 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:ring-1 transition-colors',
            scope === 'team'
              ? 'border-purple-500/30 focus:border-purple-500/60 focus:ring-purple-500/20'
              : 'border-white/10 focus:border-brand-500/50 focus:ring-brand-500/20',
          )}
        />
        <button
          onClick={send}
          disabled={!draft.trim()}
          className={clsx(
            'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-all',
            draft.trim()
              ? scope === 'team'
                ? 'bg-purple-600 hover:bg-purple-500 text-white'
                : 'bg-brand-500 hover:bg-brand-400 text-white'
              : 'bg-surface-700 text-white/20 cursor-not-allowed',
          )}
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
