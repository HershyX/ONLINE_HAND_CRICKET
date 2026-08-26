import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Hand, LogOut, Copy, Check, Wifi, WifiOff, Loader2, Users,
  CheckCircle2, Clock, Pencil, ArrowLeftRight, Play, AlertTriangle,
  RefreshCw, Shield, Crown,
} from 'lucide-react'
import clsx from 'clsx'
import {
  useGameStore,
  selectLocalPlayer,
  selectIsHost,
  selectStartValidation,
} from '../state/gameStore'
import type { Player, Room, TeamId } from '../types'
import { ChatPanel } from '../components/ChatPanel'

// ─── Copy button ──────────────────────────────────────────────────────────────

function CopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try { await navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 2000) }
    catch { /* silent */ }
  }
  return (
    <button onClick={copy} title="Copy room code"
      className="flex items-center gap-2.5 bg-surface-700 hover:bg-surface-600 border border-white/10 rounded-xl px-4 py-2.5 transition-colors group">
      <span className="font-mono font-bold text-2xl tracking-[0.25em] text-brand-400 select-all">{code}</span>
      {copied
        ? <Check className="w-4 h-4 text-brand-400 flex-shrink-0" />
        : <Copy className="w-4 h-4 text-white/30 group-hover:text-white/60 flex-shrink-0 transition-colors" />}
    </button>
  )
}

// ─── Inline name editor ───────────────────────────────────────────────────────

function NameEditor({ currentName, onSave }: { currentName: string; onSave: (n: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(currentName)
  const ref = useRef<HTMLInputElement>(null)
  const open = () => { setDraft(currentName); setEditing(true); setTimeout(() => ref.current?.focus(), 50) }
  const save = () => { const v = draft.trim(); if (v.length >= 2 && v.length <= 20) onSave(v); setEditing(false) }
  const cancel = () => setEditing(false)
  if (!editing) return (
    <button onClick={open} className="flex items-center gap-1.5 text-white/40 hover:text-brand-400 transition-colors text-xs">
      <Pencil className="w-3 h-3" /> Edit name
    </button>
  )
  return (
    <div className="flex items-center gap-2 mt-1">
      <input ref={ref} value={draft} onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancel() }}
        maxLength={20} className="bg-surface-600 border border-brand-500/50 rounded-lg px-2 py-1 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-500/40 w-36" />
      <button onClick={save} className="text-xs font-semibold text-brand-400 hover:text-brand-300">Save</button>
      <button onClick={cancel} className="text-xs text-white/30 hover:text-white/60">Cancel</button>
    </div>
  )
}

// ─── Player card ──────────────────────────────────────────────────────────────

function PlayerCard({
  player, isMe, isHost, iAmHost, onSwitchTeam, onUpdateName, onTransferHost, gameStarted,
}: {
  player: Player; isMe: boolean; isHost: boolean; iAmHost: boolean
  onSwitchTeam: (t: TeamId) => void; onUpdateName: (n: string) => void
  onTransferHost: (id: string) => void; gameStarted: boolean
}) {
  const otherTeam: TeamId = player.team_id === 'team_a' ? 'team_b' : 'team_a'
  const [showTransfer, setShowTransfer] = useState(false)

  return (
    <div className={clsx(
      'flex flex-col gap-1.5 p-3 rounded-xl border transition-all duration-200',
      player.ready ? 'bg-brand-500/10 border-brand-500/30' : 'bg-surface-700 border-white/5',
      !player.connected && 'opacity-50',
    )}>
      <div className="flex items-center justify-between gap-2">
        {/* Avatar + name */}
        <div className="flex items-center gap-2.5 min-w-0">
          <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm flex-shrink-0',
            player.connected ? 'bg-brand-500/20 text-brand-300' : 'bg-white/5 text-white/20')}>
            {player.display_name.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="font-semibold text-sm text-white truncate">{player.display_name}</span>
              {isMe && <span className="text-[10px] font-semibold bg-white/10 text-white/50 px-1.5 py-0.5 rounded-full flex-shrink-0">you</span>}
              {isHost && (
                <span className="text-[10px] font-semibold bg-brand-500/20 text-brand-400 px-1.5 py-0.5 rounded-full flex-shrink-0 flex items-center gap-0.5">
                  <Shield className="w-2.5 h-2.5" /> host
                </span>
              )}
            </div>
            <div className="flex items-center gap-1 mt-0.5">
              {player.connected ? <Wifi className="w-2.5 h-2.5 text-brand-400" /> : <WifiOff className="w-2.5 h-2.5 text-white/25" />}
              <span className="text-[10px] text-white/30">{player.connected ? 'online' : 'offline'}</span>
            </div>
          </div>
        </div>
        {/* Ready badge */}
        <div className="flex-shrink-0">
          {player.ready
            ? <span className="flex items-center gap-1 text-brand-400 text-xs font-semibold"><CheckCircle2 className="w-4 h-4" /> Ready</span>
            : <span className="flex items-center gap-1 text-white/25 text-xs"><Clock className="w-4 h-4" /> Waiting</span>}
        </div>
      </div>

      {/* My controls */}
      {isMe && !gameStarted && (
        <div className="flex items-center gap-3 pt-1 border-t border-white/5 mt-0.5">
          <NameEditor currentName={player.display_name} onSave={onUpdateName} />
          <button onClick={() => onSwitchTeam(otherTeam)}
            className="flex items-center gap-1 text-xs text-white/40 hover:text-brand-400 transition-colors">
            <ArrowLeftRight className="w-3 h-3" /> Switch team
          </button>
        </div>
      )}

      {/* Host transfer (only host can, only for other connected players) */}
      {iAmHost && !isMe && !gameStarted && player.connected && (
        <div className="pt-1 border-t border-white/5 mt-0.5">
          {showTransfer ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-white/40 flex-1">Make {player.display_name} host?</span>
              <button onClick={() => { onTransferHost(player.id); setShowTransfer(false) }}
                className="text-xs font-bold text-yellow-400 hover:text-yellow-300 px-2 py-0.5 bg-yellow-500/10 rounded-md transition-colors">
                Confirm
              </button>
              <button onClick={() => setShowTransfer(false)} className="text-xs text-white/30 hover:text-white/60">Cancel</button>
            </div>
          ) : (
            <button onClick={() => setShowTransfer(true)}
              className="flex items-center gap-1 text-xs text-white/30 hover:text-yellow-400 transition-colors">
              <Crown className="w-3 h-3" /> Transfer host
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Team column ──────────────────────────────────────────────────────────────

function TeamColumn({
  teamId, room, localPlayerId, hostId, iAmHost, onSwitchTeam, onUpdateName, onTransferHost, gameStarted,
}: {
  teamId: TeamId; room: Room; localPlayerId: string | null; hostId: string; iAmHost: boolean
  onSwitchTeam: (t: TeamId) => void; onUpdateName: (n: string) => void
  onTransferHost: (id: string) => void; gameStarted: boolean
}) {
  const team = room.teams[teamId]
  const players = Object.values(room.players).filter((p) => p.team_id === teamId)
  const connectedCount = players.filter((p) => p.connected).length
  const allReady = connectedCount > 0 && players.filter((p) => p.connected).every((p) => p.ready)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={clsx('w-2 h-2 rounded-full', teamId === 'team_a' ? 'bg-blue-400' : 'bg-purple-400')} />
          <h3 className="font-bold text-white text-sm uppercase tracking-widest">
            {team?.name ?? (teamId === 'team_a' ? 'Team 1' : 'Team 2')}
          </h3>
          {team?.extra_wicket_available && (
            <span className="text-[10px] font-semibold bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 px-1.5 py-0.5 rounded-full">
              +1 wicket
            </span>
          )}
        </div>
        <span className={clsx('text-xs font-medium px-2 py-0.5 rounded-full',
          allReady && connectedCount > 0 ? 'bg-brand-500/15 text-brand-400' : 'bg-white/5 text-white/30')}>
          {connectedCount}p
        </span>
      </div>
      <div className="flex flex-col gap-2 min-h-[60px]">
        {players.length === 0
          ? <div className="flex items-center justify-center h-16 border border-dashed border-white/10 rounded-xl text-white/20 text-xs">Empty</div>
          : players.map((p) => (
            <PlayerCard key={p.id} player={p}
              isMe={p.id === localPlayerId} isHost={p.id === hostId}
              iAmHost={iAmHost}
              onSwitchTeam={onSwitchTeam} onUpdateName={onUpdateName}
              onTransferHost={onTransferHost} gameStarted={gameStarted} />
          ))}
      </div>
    </div>
  )
}

// ─── Start panel ──────────────────────────────────────────────────────────────

function StartPanel({ onStart, loading }: { onStart: () => void; loading: boolean }) {
  const validation = useGameStore(selectStartValidation)
  return (
    <div className="space-y-3">
      {!validation.can_start && validation.reasons.length > 0 && (
        <div className="bg-yellow-500/5 border border-yellow-500/15 rounded-xl px-3 py-2.5 space-y-1">
          {validation.reasons.map((r, i) => (
            <div key={i} className="flex items-start gap-2 text-yellow-400 text-xs">
              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" /><span>{r}</span>
            </div>
          ))}
        </div>
      )}
      <button onClick={onStart} disabled={!validation.can_start || loading}
        className={clsx('w-full flex items-center justify-center gap-2 font-bold py-3.5 rounded-xl text-sm transition-all',
          validation.can_start && !loading
            ? 'bg-brand-500 hover:bg-brand-400 text-white shadow-lg shadow-brand-900/30'
            : 'bg-surface-600 border border-white/10 text-white/30 cursor-not-allowed')}>
        {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Starting…</> : <><Play className="w-4 h-4" /> Start Match</>}
      </button>
    </div>
  )
}

// ─── Main RoomPage ────────────────────────────────────────────────────────────

export default function RoomPage() {
  const navigate   = useNavigate()
  const room       = useGameStore((s) => s.room)
  const roomCode   = useGameStore((s) => s.roomCode)
  const playerId   = useGameStore((s) => s.playerId)
  const connection = useGameStore((s) => s.connection)
  const localPlayer = useGameStore(selectLocalPlayer)
  const isHost     = useGameStore(selectIsHost)

  const switchTeam    = useGameStore((s) => s.switchTeam)
  const updateName    = useGameStore((s) => s.updateName)
  const setReady      = useGameStore((s) => s.setReady)
  const startMatch    = useGameStore((s) => s.startMatch)
  const transferHost  = useGameStore((s) => s.transferHost)
  const leaveRoom     = useGameStore((s) => s.leaveRoom)

  const [starting, setStarting] = useState(false)

  useEffect(() => {
    if (!roomCode && !connection.connecting) navigate('/')
  }, [roomCode, connection.connecting, navigate])

  useEffect(() => {
    // Go to game page if a game is actively in progress.
    // GAME_OVER is excluded — players who returned to lobby should stay here.
    const activeStatuses = ['TOSS', 'TOSS_DECISION', 'INNINGS_SETUP',
      'CHOOSING_NUMBERS', 'RESOLVING_BALL', 'PLAYER_OUT', 'EXTRA_WICKET_VOTE',
      'BOWLER_SWITCH', 'INNINGS_BREAK', 'SECOND_INNINGS']
    if (room?.game && activeStatuses.includes(room.game.status)) {
      navigate('/game')
    }
  }, [room?.game?.status, room, navigate])

  const handleLeave = () => { leaveRoom(); navigate('/') }
  const handleStartMatch = () => {
    setStarting(true)
    startMatch()
    setTimeout(() => setStarting(false), 3000)
  }

  // ── Loading ───────────────────────────────────────────────────────────────

  if (connection.connecting || (!room && !connection.error)) {
    return (
      <div className="min-h-screen bg-surface-900 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-10 h-10 text-brand-400 animate-spin mx-auto mb-4" />
          <p className="text-white/50 text-sm">Connecting…</p>
          {roomCode && <p className="text-white/25 text-xs font-mono mt-1">{roomCode}</p>}
        </div>
      </div>
    )
  }

  if (connection.error && !room) {
    return (
      <div className="min-h-screen bg-surface-900 flex items-center justify-center px-6">
        <div className="text-center max-w-sm">
          <WifiOff className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-white mb-2">Connection failed</h2>
          <p className="text-white/40 text-sm mb-6">{connection.error}</p>
          <button onClick={() => navigate('/')} className="bg-brand-500 hover:bg-brand-400 text-white font-bold px-6 py-3 rounded-xl transition-colors">
            Back to Home
          </button>
        </div>
      </div>
    )
  }

  if (!room) return null

  const gameStarted    = room.room_status === 'IN_GAME'
    && room.game !== null
    && room.game.status !== 'GAME_OVER'
  const connectedCount = Object.values(room.players).filter((p) => p.connected).length

  return (
    <div className="min-h-screen bg-surface-900 text-white flex flex-col">
      {/* Nav */}
      <nav className="flex items-center justify-between px-5 py-3.5 border-b border-white/5 bg-surface-900/80 backdrop-blur sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <Hand className="w-5 h-5 text-brand-400" strokeWidth={2.5} />
          <span className="font-bold tracking-tight">Hand<span className="text-brand-400">Cricket</span></span>
        </div>
        <div className="flex items-center gap-3">
          <div className={clsx('flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full',
            connection.connected ? 'bg-brand-500/10 text-brand-400' : 'bg-red-500/10 text-red-400')}>
            <span className={clsx('w-1.5 h-1.5 rounded-full', connection.connected ? 'bg-brand-400 animate-pulse' : 'bg-red-400')} />
            {connection.connected ? 'Live' : 'Offline'}
          </div>
          {!connection.connected && (
            <button onClick={() => useGameStore.getState().reconnect()}
              className="text-xs text-white/40 hover:text-white flex items-center gap-1">
              <RefreshCw className="w-3 h-3" /> Reconnect
            </button>
          )}
          <button onClick={handleLeave} className="flex items-center gap-1.5 text-sm text-white/30 hover:text-red-400 transition-colors">
            <LogOut className="w-4 h-4" /> Leave
          </button>
        </div>
      </nav>

      {/* Content */}
      <div className="flex-1 flex flex-col items-center px-4 py-6">
        <div className="w-full max-w-2xl space-y-4">

          {/* Room code */}
          <div className="bg-surface-800 border border-white/5 rounded-2xl px-5 py-4 flex items-center justify-between flex-wrap gap-3">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-white/25 mb-2">Room Code</p>
              <CopyButton code={room.room_code} />
            </div>
            <div className="text-right text-xs text-white/30 space-y-1">
              <div className="flex items-center gap-1.5 justify-end">
                <Users className="w-3.5 h-3.5" />
                <span>{connectedCount}/{room.max_players}</span>
              </div>
              <span className={clsx('font-medium', room.room_status === 'IN_GAME' ? 'text-brand-400' : '')}>
                {room.room_status}
              </span>
            </div>
          </div>

          {/* Teams side by side */}
          <div className="bg-surface-800 border border-white/5 rounded-2xl p-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <TeamColumn teamId="team_a" room={room} localPlayerId={playerId} hostId={room.host_id}
                iAmHost={isHost} onSwitchTeam={switchTeam} onUpdateName={updateName}
                onTransferHost={transferHost} gameStarted={gameStarted} />
              <div className="sm:hidden border-t border-white/5" />
              <TeamColumn teamId="team_b" room={room} localPlayerId={playerId} hostId={room.host_id}
                iAmHost={isHost} onSwitchTeam={switchTeam} onUpdateName={updateName}
                onTransferHost={transferHost} gameStarted={gameStarted} />
            </div>
          </div>

          {/* Controls — only in lobby */}
          {!gameStarted && localPlayer && (
            <div className="bg-surface-800 border border-white/5 rounded-2xl p-5 space-y-3">
              {/* Ready toggle */}
              <button onClick={() => setReady(!localPlayer.ready)}
                className={clsx('w-full flex items-center justify-center gap-2 font-bold py-3 rounded-xl text-sm transition-all',
                  localPlayer.ready
                    ? 'bg-surface-600 border border-white/10 text-white/50 hover:bg-surface-500'
                    : 'bg-brand-500/80 hover:bg-brand-500 text-white')}>
                {localPlayer.ready ? <><Clock className="w-4 h-4" /> Cancel Ready</> : <><CheckCircle2 className="w-4 h-4" /> I'm Ready</>}
              </button>

              {/* Start (host only) */}
              {isHost ? (
                <div className="border-t border-white/5 pt-3">
                  <StartPanel onStart={handleStartMatch} loading={starting} />
                </div>
              ) : (
                <p className="text-center text-white/25 text-xs">Waiting for the host to start…</p>
              )}
            </div>
          )}

          {/* Game in progress notice */}
          {gameStarted && (
            <div className="bg-brand-500/10 border border-brand-500/20 rounded-2xl p-4 text-center">
              <p className="text-brand-400 font-semibold text-sm">Match in progress</p>
              <p className="text-white/30 text-xs mt-1">Team membership is locked.</p>
            </div>
          )}

          {/* Chat panel */}
          <ChatPanel room={room} playerId={playerId} />

        </div>
      </div>
    </div>
  )
}
