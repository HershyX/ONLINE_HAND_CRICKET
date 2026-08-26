import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Hand, LogOut, Loader2, Wifi, WifiOff, RefreshCw,
  Trophy, Coins, Play, Skull, ArrowLeftRight, UserCheck,
} from 'lucide-react'
import clsx from 'clsx'
import {
  useGameStore,
  selectLocalPlayer,
  selectIsHost,
} from '../state/gameStore'
import type { GameState, HandNumber, InningsState, Player, Room } from '../types'
import { ChatPanel } from '../components/ChatPanel'

// ─── Constants ────────────────────────────────────────────────────────────────

const NUMBERS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const

// ─── Small helpers ────────────────────────────────────────────────────────────

function useGame() {
  return useGameStore((s) => s.room?.game ?? null)
}

/** Resolve current batsman id from InningsState (backend sends index, not id directly). */
function batsmanId(inn: InningsState): string {
  return inn.current_batsman_idx < inn.batting_order.length
    ? inn.batting_order[inn.current_batsman_idx]
    : ''
}

/**
 * Returns a viewer-relative team label.
 * During an active game: "My Team" if teamId matches myTeamId, else "Opponents".
 * Falls back to the stored team name if the game hasn't started or myTeamId is unknown.
 */
function teamLabel(
  teamId: string,
  myTeamId: string | null | undefined,
  fallbackName: string,
): string {
  if (!myTeamId) return fallbackName
  return teamId === myTeamId ? 'My Team' : 'Opponents'
}

function Waiting({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-6 text-white/40">
      <Loader2 className="w-5 h-5 animate-spin text-brand-400 flex-shrink-0" />
      <span className="text-sm">{text}</span>
    </div>
  )
}

// ─── Wicket popup ─────────────────────────────────────────────────────────────

function WicketPopup() {
  const notice = useGameStore((s) => s.dismissalNotice)
  const clear  = useGameStore((s) => s.clearDismissalNotice)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!notice) return
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(clear, 3500)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [notice, clear])

  if (!notice) return null

  return (
    <div className="fixed inset-0 flex items-center justify-center z-50 pointer-events-none">
      <div className="animate-slide-up bg-red-950 border border-red-500/40 rounded-2xl px-8 py-6 shadow-2xl shadow-black/60 text-center max-w-xs mx-4">
        <Skull className="w-10 h-10 text-red-400 mx-auto mb-3" />
        <p className="text-red-200 text-2xl font-black tracking-tight">OUT!</p>
        <p className="text-red-300 font-semibold mt-1">{notice} is dismissed</p>
      </div>
    </div>
  )
}

// ─── Number grid ──────────────────────────────────────────────────────────────

function NumberGrid({
  onSelect,
  disabled = false,
  selected = null,
}: {
  onSelect: (n: number) => void
  disabled?: boolean
  selected?: number | null
}) {
  return (
    <div className="grid grid-cols-6 md:grid-cols-11 gap-2.5 md:gap-2">
      {NUMBERS.map((n) => (
        <button
          key={n}
          onClick={() => onSelect(n)}
          disabled={disabled || selected !== null}
          className={clsx(
            'aspect-square flex items-center justify-center rounded-xl border font-bold text-lg transition-all duration-150',
            selected === n
              ? 'bg-brand-500 border-brand-400 text-white scale-105'
              : disabled || selected !== null
              ? 'bg-surface-700 border-white/5 text-white/20 cursor-not-allowed'
              : 'bg-surface-700 border-white/10 text-white hover:bg-brand-500/80 hover:border-brand-400 hover:scale-105 active:scale-95',
          )}
        >
          {n}
        </button>
      ))}
    </div>
  )
}

// ─── Last ball display ────────────────────────────────────────────────────────

/** Shows both numbers after each ball is resolved. */
function LastBallDisplay({ inn }: { inn: InningsState }) {
  const ball = inn.last_ball
  if (!ball) return null

  return (
    <div
      className={clsx(
        'flex items-center justify-center gap-3 sm:gap-6 py-3 px-4 rounded-xl border text-center flex-wrap',
        ball.is_wicket
          ? 'bg-red-500/10 border-red-500/25'
          : 'bg-surface-700 border-white/5',
      )}
    >
      <div className="text-center">
        <p className="text-[10px] uppercase tracking-widest text-white/30">Bat</p>
        <p className="font-mono font-black text-2xl text-brand-300">
          {ball.batsman_number}
        </p>
      </div>
      <div className="text-white/20 text-lg font-light">vs</div>
      <div className="text-center">
        <p className="text-[10px] uppercase tracking-widest text-white/30">Bowl</p>
        <p className="font-mono font-black text-2xl text-purple-300">
          {ball.bowler_number}
        </p>
      </div>
      <div className="border-l border-white/10 pl-6 text-center">
        {ball.is_wicket ? (
          <p className="text-red-400 font-bold text-sm">OUT</p>
        ) : (
          <>
            <p className="text-[10px] uppercase tracking-widest text-white/30">Runs</p>
            <p className="font-mono font-black text-2xl text-white">+{ball.runs}</p>
          </>
        )}
      </div>
    </div>
  )
}

// ─── Live scoreboard ──────────────────────────────────────────────────────────

/**
 * Per-player row in the scoreboard.
 * Batting side: name | runs | balls | status
 * Bowling side: name | wickets | balls
 */
function PlayerRow({
  player,
  isBatting,
  isCurrentBatsman,
  isCurrentBowler,
  inn,
}: {
  player: Player
  isBatting: boolean
  isCurrentBatsman: boolean
  isCurrentBowler: boolean
  inn: InningsState
}) {
  const isOut = inn.dismissed[player.id] === true

  return (
    <div
      className={clsx(
        'flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-sm',
        isCurrentBatsman || isCurrentBowler
          ? 'bg-brand-500/10 border border-brand-500/20'
          : 'bg-surface-700/40',
        isOut && 'opacity-50',
      )}
    >
      {/* Name + role indicator */}
      <div className="flex items-center gap-2 min-w-0">
        <div
          className={clsx(
            'w-6 h-6 rounded-md flex items-center justify-center text-xs font-bold flex-shrink-0',
            isCurrentBatsman ? 'bg-brand-500/30 text-brand-300'
              : isCurrentBowler ? 'bg-purple-500/30 text-purple-300'
              : 'bg-white/5 text-white/30',
          )}
        >
          {player.display_name.charAt(0).toUpperCase()}
        </div>
        <span className={clsx('truncate', isOut ? 'text-white/40' : 'text-white/90')}>
          {player.display_name}
        </span>
        {isCurrentBatsman && (
          <span className="text-[9px] font-bold text-brand-400 bg-brand-500/10 px-1.5 py-0.5 rounded-full flex-shrink-0">
            BAT
          </span>
        )}
        {isCurrentBowler && (
          <span className="text-[9px] font-bold text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded-full flex-shrink-0">
            BOWL
          </span>
        )}
      </div>

      {/* Stats */}
      {isBatting ? (
        <div className="flex items-center gap-3 text-right flex-shrink-0">
          <span className="font-mono font-bold text-white">
            {player.batting_stats.runs_scored}
          </span>
          <span className="text-white/30 text-xs">
            ({player.batting_stats.balls_faced})
          </span>
          {isOut ? (
            <span className="text-red-400 text-xs font-semibold w-14 text-right">out</span>
          ) : isCurrentBatsman ? (
            <span className="text-brand-400 text-xs font-semibold w-14 text-right">batting</span>
          ) : (
            <span className="text-white/30 text-xs w-14 text-right">not out</span>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-3 text-right flex-shrink-0">
          <span className="font-mono font-bold text-white">
            {player.bowling_stats.wickets_taken}W
          </span>
          <span className="text-white/30 text-xs">
            {player.bowling_stats.runs_conceded}R
          </span>
          <span className="text-white/30 text-xs">
            {player.bowling_stats.balls_bowled}b
          </span>
        </div>
      )}
    </div>
  )
}

function LiveScoreboard({ game, room }: { game: GameState; room: Room }) {
  const inn = game.innings
  const me  = useGameStore(selectLocalPlayer)

  if (!inn) {
    return (
      <div className="bg-surface-800 border border-white/5 rounded-2xl p-5">
        <p className="text-white/30 text-sm text-center">
          Waiting for innings to start…
        </p>
      </div>
    )
  }

  const battingTeam  = room.teams[inn.batting_team_id]
  const bowlingTeam  = room.teams[inn.bowling_team_id]
  const myTeamId     = me?.team_id
  const myTeamBatting = myTeamId === inn.batting_team_id

  const battingLabel = teamLabel(inn.batting_team_id, myTeamId, battingTeam?.name ?? '—')
  const bowlingLabel = teamLabel(inn.bowling_team_id, myTeamId, bowlingTeam?.name ?? '—')

  const battingPlayers = inn.batting_order
    .filter((pid, i, arr) => arr.indexOf(pid) === i)
    .map((pid) => room.players[pid])
    .filter(Boolean)

  const bowlingPlayers = bowlingTeam.player_ids
    .map((pid) => room.players[pid])
    .filter(Boolean)

  const currentBatId  = batsmanId(inn)
  const currentBowlId = inn.current_bowler_id

  const overs = `${Math.floor(inn.total_balls / 6)}.${inn.total_balls % 6}`

  return (
    <div className="bg-surface-800 border border-white/5 rounded-2xl overflow-hidden">
      {/* Score header */}
      <div className="px-5 pt-4 pb-3 flex items-end justify-between border-b border-white/5">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-white/25 mb-0.5">
            Innings {game.innings_number} · {battingLabel} batting
          </p>
          <p className="font-mono font-black text-4xl text-white leading-none">
            {inn.score}
            <span className="text-white/30 text-2xl">/{inn.wickets}</span>
          </p>
        </div>
        <div className="text-right space-y-1">
          <p className="text-xs text-white/30">{overs} ov</p>
          {game.innings_number === 2 && game.target !== null && (
            <p className="text-brand-300 text-xs font-semibold">
              Need {Math.max(0, game.target - inn.score)} more
            </p>
          )}
          {game.status === 'CHOOSING_NUMBERS' && (
            <p className="text-white/20 text-[10px] flex items-center justify-end gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-white/20 animate-pulse inline-block" />
              awaiting numbers
            </p>
          )}
        </div>
      </div>

      {/* Two-column player stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-white/5">
        {/* Left column — my team */}
        <div className="p-4 space-y-2">
          <p className="text-[10px] font-bold uppercase tracking-widest text-white/25 mb-2 flex items-center gap-1">
            <span className={clsx('w-2 h-2 rounded-full', myTeamBatting ? 'bg-brand-400' : 'bg-purple-400')} />
            {myTeamBatting ? battingLabel : bowlingLabel}
          </p>
          {(myTeamBatting ? battingPlayers : bowlingPlayers).map((p) => (
            <PlayerRow
              key={p.id}
              player={p}
              isBatting={myTeamBatting}
              isCurrentBatsman={p.id === currentBatId}
              isCurrentBowler={p.id === currentBowlId}
              inn={inn}
            />
          ))}
        </div>

        {/* Right column — opposition */}
        <div className="p-4 space-y-2">
          <p className="text-[10px] font-bold uppercase tracking-widest text-white/25 mb-2 flex items-center gap-1">
            <span className={clsx('w-2 h-2 rounded-full', myTeamBatting ? 'bg-purple-400' : 'bg-brand-400')} />
            {myTeamBatting ? bowlingLabel : battingLabel}
          </p>
          {(myTeamBatting ? bowlingPlayers : battingPlayers).map((p) => (
            <PlayerRow
              key={p.id}
              player={p}
              isBatting={!myTeamBatting}
              isCurrentBatsman={p.id === currentBatId}
              isCurrentBowler={p.id === currentBowlId}
              inn={inn}
            />
          ))}
        </div>
      </div>

      {/* Last ball */}
      {inn.last_ball && (
        <div className="px-5 pb-4 pt-1 border-t border-white/5">
          <p className="text-[10px] uppercase tracking-widest text-white/25 mb-2">Last ball</p>
          <LastBallDisplay inn={inn} />
        </div>
      )}
    </div>
  )
}

// ─── Toss phase ───────────────────────────────────────────────────────────────

function TossPhase({ game }: { game: GameState }) {
  const room      = useGameStore((s) => s.room)!
  const me        = useGameStore(selectLocalPlayer)
  const callToss  = useGameStore((s) => s.callToss)
  const respondToss = useGameStore((s) => s.respondToss)

  const [call, setCall]       = useState<'ODD' | 'EVEN' | null>(null)
  const [myNumber, setMyNumber] = useState<number | null>(null)

  // Reset when toss phase exits
  useEffect(() => {
    if (game.status !== 'TOSS') { setMyNumber(null); setCall(null) }
  }, [game.status])

  if (!me) return <Waiting text="Loading…" />

  const isCaller    = me.id === game.toss_caller_player_id
  const isResponder = me.id === game.toss_responder_player_id
  const callerName  = room.players[game.toss_caller_player_id ?? '']?.display_name ?? '…'
  const responderName = room.players[game.toss_responder_player_id ?? '']?.display_name ?? '…'

  // ── Caller flow ──────────────────────────────────────────────────────────
  if (isCaller) {
    if (!call) {
      return (
        <div className="space-y-3">
          <p className="text-white/60 text-sm">
            You are calling the toss. Pick <strong className="text-white">ODD</strong> or{' '}
            <strong className="text-white">EVEN</strong>:
          </p>
          <div className="grid grid-cols-2 gap-3">
            {(['ODD', 'EVEN'] as const).map((c) => (
              <button
                key={c}
                onClick={() => setCall(c)}
                className="py-4 rounded-xl border border-white/10 bg-surface-700 hover:bg-brand-500 hover:border-brand-400 font-bold text-white transition-all"
              >
                {c}
              </button>
            ))}
          </div>
        </div>
      )
    }
    if (myNumber === null) {
      return (
        <div className="space-y-3">
          <p className="text-white/60 text-sm">
            You called <span className="text-brand-300 font-bold">{call}</span>. Now show your
            number:
          </p>
          <NumberGrid
            onSelect={(n) => {
              setMyNumber(n)
              callToss(call, n)
            }}
          />
          <button onClick={() => setCall(null)} className="text-xs text-white/50 hover:text-white px-3 py-2 -ml-3 rounded-lg hover:bg-white/5 transition-colors">
            Change call
          </button>
        </div>
      )
    }
    return <Waiting text={`You showed ${myNumber} — waiting for ${responderName}…`} />
  }

  // ── Responder flow ───────────────────────────────────────────────────────
  if (isResponder) {
    if (!game.toss_call_made) {
      return <Waiting text={`Waiting for ${callerName} to call ODD or EVEN…`} />
    }
    if (myNumber === null) {
      return (
        <div className="space-y-3">
          <p className="text-white/60 text-sm">
            <span className="font-semibold text-white">{callerName}</span> called{' '}
            <span className="text-brand-300 font-bold">{game.toss_call_made}</span>. Show
            your number:
          </p>
          <NumberGrid
            onSelect={(n) => {
              setMyNumber(n)
              respondToss(n)
            }}
          />
        </div>
      )
    }
    return <Waiting text={`You showed ${myNumber} — resolving toss…`} />
  }

  // ── Spectator ────────────────────────────────────────────────────────────
  return (
    <div className="space-y-2">
      <Waiting text="Toss in progress…" />
      <div className="flex justify-between text-xs text-white/30 px-1">
        <span>
          {callerName}: {game.toss_call_made ? `called ${game.toss_call_made}` : 'choosing…'}
        </span>
        <span>{responderName}: waiting</span>
      </div>
    </div>
  )
}

// ─── Toss decision phase ──────────────────────────────────────────────────────

function TossDecisionPhase({ game }: { game: GameState }) {
  const room       = useGameStore((s) => s.room)!
  const me         = useGameStore(selectLocalPlayer)
  const decideToss = useGameStore((s) => s.decideToss)

  if (!me || !game.toss_winner_team_id) return <Waiting text="Resolving toss…" />

  const winnerTeam   = room.teams[game.toss_winner_team_id]
  const myTeamWon    = me.team_id === game.toss_winner_team_id
  const callerName   = room.players[game.toss_caller_player_id ?? '']?.display_name ?? '?'
  const respName     = room.players[game.toss_responder_player_id ?? '']?.display_name ?? '?'
  const callerNum    = game.toss_caller_number
  const respNum      = game.toss_responder_number
  const winnerLabel  = teamLabel(game.toss_winner_team_id, me.team_id, winnerTeam?.name ?? '?')

  return (
    <div className="space-y-4">
      {/* Public toss result — both numbers visible to everyone */}
      <div className="bg-surface-700 rounded-xl p-4 space-y-3">
        <p className="text-[10px] font-bold uppercase tracking-widest text-white/25 text-center">
          Toss result
        </p>
        <div className="flex items-center justify-center gap-3 sm:gap-8 flex-wrap">
          <div className="text-center">
            <p className="text-xs text-white/40">{callerName}</p>
            <p className="font-mono font-black text-3xl text-brand-300">
              {callerNum ?? '?'}
            </p>
          </div>
          <span className="text-white/20 font-light text-xl">+</span>
          <div className="text-center">
            <p className="text-xs text-white/40">{respName}</p>
            <p className="font-mono font-black text-3xl text-purple-300">
              {respNum ?? '?'}
            </p>
          </div>
          <span className="text-white/20 font-light text-xl">=</span>
          <div className="text-center">
            <p className="text-xs text-white/40">Sum</p>
            <p className="font-mono font-black text-3xl text-white">
              {callerNum !== null && respNum !== null ? callerNum + respNum : '?'}
            </p>
          </div>
        </div>
        <p className="text-center text-sm font-semibold text-brand-300">
          🏆 {winnerLabel} won the toss!
        </p>
      </div>

      {/* ── Public decision announcement (visible to ALL once made) ── */}
      {game.toss_announcement ? (
        <div className="bg-brand-500/10 border border-brand-500/25 rounded-xl px-4 py-3 text-center">
          <p className="text-brand-300 font-bold text-sm">{game.toss_announcement}</p>
        </div>
      ) : myTeamWon ? (
        <>
          <p className="text-brand-300 font-semibold text-sm text-center">
            Your team won — bat or bowl?
          </p>
          <div className="grid grid-cols-2 gap-3">
            {(['BAT', 'BOWL'] as const).map((d) => (
              <button
                key={d}
                onClick={() => decideToss(d)}
                className="py-4 rounded-xl border border-white/10 bg-surface-700 hover:bg-brand-500 hover:border-brand-400 font-bold text-white transition-all"
              >
                {d}
              </button>
            ))}
          </div>
        </>
      ) : (
        <Waiting text={`${winnerLabel} won — they are choosing…`} />
      )}
    </div>
  )
}

// ─── Play phase ───────────────────────────────────────────────────────────────

function PlayPhase({ game }: { game: GameState }) {
  const room               = useGameStore((s) => s.room)!
  const me                 = useGameStore(selectLocalPlayer)
  const chooseNumber       = useGameStore((s) => s.chooseNumber)
  const requestBowlerSwitch  = useGameStore((s) => s.requestBowlerSwitch)
  const respondBowlerSwitch  = useGameStore((s) => s.respondBowlerSwitch)
  const requestBatsmanSwitch = useGameStore((s) => s.requestBatsmanSwitch)
  const respondBatsmanSwitch = useGameStore((s) => s.respondBatsmanSwitch)
  const voteExtraWicket    = useGameStore((s) => s.voteExtraWicket)

  const [myNumber, setMyNumber] = useState<number | null>(null)
  const inn = game.innings

  // Reset on every new ball
  useEffect(() => {
    setMyNumber(null)
  }, [inn?.total_balls, inn?.current_batsman_idx, game.status])

  if (!me || !inn) return <Waiting text="Setting up innings…" />

  const currentBat = batsmanId(inn)
  const currentBowl = inn.current_bowler_id
  const isBatsman = me.id === currentBat
  const isBowler  = me.id === currentBowl
  const onBowlingTeam  = me.team_id === inn.bowling_team_id

  // ── Extra-wicket voting ──────────────────────────────────────────────────
  if (game.status === 'EXTRA_WICKET_VOTE' && game.extra_wicket_vote) {
    const vote = game.extra_wicket_vote
    if (vote.eligible_voters.includes(me.id)) {
      if (vote.votes[me.id]) {
        return <Waiting text="Vote cast — waiting for the rest of the team…" />
      }
      return (
        <div className="space-y-3">
          <p className="text-yellow-300 font-semibold text-sm">
            All out! Vote for the extra wicket batsman (round {vote.round}):
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {vote.candidates.map((pid) => (
              <button
                key={pid}
                onClick={() => voteExtraWicket(pid)}
                className="py-3 px-2 rounded-xl border border-white/10 bg-surface-700 hover:bg-brand-500 hover:border-brand-400 text-sm font-semibold text-white truncate transition-all"
              >
                {room.players[pid]?.display_name ?? pid.slice(0, 8)}
              </button>
            ))}
          </div>
        </div>
      )
    }
    return <Waiting text="Batting team is voting for the extra wicket…" />
  }

  // ── Bowler-switch prompt ─────────────────────────────────────────────────
  if (game.status === 'BOWLER_SWITCH' && game.bowler_switch) {
    const sw = game.bowler_switch
    const requesterName = room.players[sw.requested_by]?.display_name ?? '?'
    if (isBowler) {
      return (
        <div className="space-y-3">
          <p className="text-white/70 text-sm">
            <span className="font-semibold text-white">{requesterName}</span> wants to bowl.
            {sw.queue.length > 0 && (
              <span className="text-white/40 text-xs block mt-1">
                Also queued: {sw.queue.map((id) => room.players[id]?.display_name ?? id).join(', ')}
              </span>
            )}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => respondBowlerSwitch(true)}
              className="py-3 rounded-xl bg-brand-500 hover:bg-brand-400 font-bold text-white"
            >
              Accept
            </button>
            <button
              onClick={() => respondBowlerSwitch(false)}
              className="py-3 rounded-xl border border-white/10 bg-surface-700 hover:bg-surface-600 font-bold text-white"
            >
              Decline
            </button>
          </div>
        </div>
      )
    }
    return <Waiting text={`Waiting for current bowler to respond to ${requesterName}'s switch…`} />
  }

  // ── Batsman-switch prompt — shown to the CURRENT BATSMAN ────────────────
  if (game.batsman_switch && game.batsman_switch.current_batsman) {
    const bsw = game.batsman_switch

    if (isBatsman) {
      return (
        <div className="space-y-3">
          <p className="text-white/70 text-sm font-medium">
            Switch request{bsw.requests.length > 1 ? 's' : ''}:
          </p>
          <div className="space-y-2">
            {bsw.requests.map((rid) => {
              const name = room.players[rid]?.display_name ?? rid
              return (
                <div
                  key={rid}
                  className="flex items-center justify-between gap-3 bg-surface-700 rounded-xl px-4 py-2.5"
                >
                  <span className="text-sm font-semibold text-white">{name} wants to bat</span>
                  <button
                    onClick={() => respondBatsmanSwitch(true, rid)}
                    className="text-xs font-bold text-brand-400 hover:text-brand-300 px-3 py-2 min-h-[44px] bg-brand-500/10 hover:bg-brand-500/20 rounded-lg transition-colors"
                  >
                    Let in
                  </button>
                </div>
              )
            })}
          </div>
          <button
            onClick={() => respondBatsmanSwitch(false)}
            className="w-full py-2.5 rounded-xl border border-white/10 bg-surface-700 hover:bg-surface-600 text-sm font-semibold text-white/60 hover:text-white transition-all"
          >
            Decline all
          </button>
        </div>
      )
    }
    const currentName = room.players[bsw.current_batsman]?.display_name ?? 'Batsman'
    return <Waiting text={`${currentName} is deciding on the switch request…`} />
  }

  // ── Normal ball ──────────────────────────────────────────────────────────
  if (isBatsman || isBowler) {
    const roleLabel = isBatsman ? 'batting' : 'bowling'
    const myColor   = isBatsman
      ? { box: 'bg-brand-500/20 border-brand-400/50', text: 'text-brand-300', label: 'Bat' }
      : { box: 'bg-purple-500/20 border-purple-400/50', text: 'text-purple-300', label: 'Bowl' }
    const oppLabel = isBatsman ? 'Bowl' : 'Bat'

    if (myNumber !== null) {
      // ── Submitted: show your number vs hidden opponent number ──────────────
      return (
        <div className="space-y-4">
          <p className="text-white/50 text-xs text-center uppercase tracking-widest">
            Numbers submitted — waiting for the other player
          </p>
          <div className="flex items-center justify-center gap-4">
            {/* My side */}
            <div className="flex flex-col items-center gap-1.5">
              <p className="text-[10px] uppercase tracking-widest text-white/30">{myColor.label}</p>
              <div className={clsx('w-20 h-20 rounded-2xl border-2 flex items-center justify-center shadow-lg', myColor.box)}>
                <span className={clsx('font-mono font-black text-4xl', myColor.text)}>
                  {myNumber}
                </span>
              </div>
              <p className="text-[10px] text-brand-400 font-semibold">You ✓</p>
            </div>

            <span className="text-white/20 text-2xl font-light">vs</span>

            {/* Opponent side — hidden until resolved */}
            <div className="flex flex-col items-center gap-1.5">
              <p className="text-[10px] uppercase tracking-widest text-white/30">{oppLabel}</p>
              <div className="w-20 h-20 rounded-2xl border-2 border-white/10 bg-surface-700 flex items-center justify-center">
                <Loader2 className="w-7 h-7 text-white/20 animate-spin" />
              </div>
              <p className="text-[10px] text-white/25 animate-pulse">Waiting…</p>
            </div>
          </div>
        </div>
      )
    }

    // ── Not yet submitted: number grid ─────────────────────────────────────
    return (
      <div className="space-y-3">
        <p className="text-white/60 text-sm">
          You are <span className="font-semibold text-white">{roleLabel}</span>.
          Show your number:
        </p>
        <NumberGrid
          onSelect={(n) => {
            setMyNumber(n)
            chooseNumber(n as HandNumber)
          }}
        />
      </div>
    )
  }

  // ── Bowling-team spectator — can only request to bowl ────────────────────
  if (onBowlingTeam) {
    const alreadyRequested = game.bowler_switch?.requested_by === me.id
      || game.bowler_switch?.queue.includes(me.id)

    return (
      <div className="space-y-3">
        <Waiting text="Waiting for the current batsman and bowler…" />
        <button
          onClick={() => requestBowlerSwitch(me.id)}
          disabled={alreadyRequested}
          className={clsx(
            'w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border text-sm font-semibold transition-all',
            alreadyRequested
              ? 'border-white/5 bg-surface-700 text-white/20 cursor-not-allowed'
              : 'border-white/10 bg-surface-700 hover:bg-surface-600 text-white/70 hover:text-white',
          )}
        >
          <ArrowLeftRight className="w-3.5 h-3.5" />
          {alreadyRequested ? 'Switch requested' : 'Request to bowl'}
        </button>
      </div>
    )
  }

  // ── Batting-team non-current batsman — can request to swap in ────────────
  const alreadyRequestedBat = game.batsman_switch?.requests.includes(me.id)
  const isOut = inn.dismissed[me.id] === true

  return (
    <div className="space-y-3">
      <Waiting text="Waiting for the current batsman and bowler…" />
      {!isOut && (
        <button
          onClick={() => requestBatsmanSwitch()}
          disabled={!!alreadyRequestedBat}
          className={clsx(
            'w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border text-sm font-semibold transition-all',
            alreadyRequestedBat
              ? 'border-white/5 bg-surface-700 text-white/20 cursor-not-allowed'
              : 'border-white/10 bg-surface-700 hover:bg-surface-600 text-white/70 hover:text-white',
          )}
        >
          <UserCheck className="w-3.5 h-3.5" />
          {alreadyRequestedBat ? 'Request sent' : 'Request to bat now'}
        </button>
      )}
    </div>
  )
}

// ─── Innings break ────────────────────────────────────────────────────────────

function InningsBreakPhase() {
  const room              = useGameStore((s) => s.room)!
  const game              = useGame() as GameState
  const isHost            = useGameStore(selectIsHost)
  const me                = useGameStore(selectLocalPlayer)
  const startSecondInnings = useGameStore((s) => s.startSecondInnings)

  const first    = game.innings_history[0]
  const firstBatId = first?.batting_team_id
  const nextBatId  = first?.bowling_team_id
  const myTeamId   = me?.team_id

  const firstBatLabel = firstBatId ? teamLabel(firstBatId, myTeamId, room.teams[firstBatId]?.name ?? '—') : '—'
  const nextBatLabel  = nextBatId  ? teamLabel(nextBatId,  myTeamId, room.teams[nextBatId]?.name  ?? '—') : '—'

  return (
    <div className="space-y-4 text-center">
      <Trophy className="w-8 h-8 text-brand-400 mx-auto" />
      <div>
        <p className="text-white/50 text-sm">End of innings 1</p>
        <p className="font-mono font-bold text-3xl text-white mt-1">
          {firstBatLabel}: {first?.score ?? 0}/{first?.wickets ?? 0}
        </p>
        {game.target !== null && (
          <p className="text-brand-300 text-sm font-semibold mt-2">
            {nextBatLabel} need {game.target} to win
          </p>
        )}
      </div>

      {isHost ? (
        <button
          onClick={startSecondInnings}
          className="w-full flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-400 text-white font-bold py-4 rounded-xl transition-all shadow-lg shadow-brand-900/30"
        >
          <Play className="w-5 h-5" /> Start Second Innings
        </button>
      ) : (
        <p className="text-white/30 text-sm">Waiting for the host to start the second innings…</p>
      )}
    </div>
  )
}

// ─── Game over ────────────────────────────────────────────────────────────────

// Full-width scorecard for a single team with larger, readable text.
function TeamScorecard({
  teamId, label, accentClass, room, game,
}: {
  teamId: string; label: string; accentClass: string; room: Room; game: GameState
}) {
  const team    = room.teams[teamId as 'team_a' | 'team_b']
  const players = team?.player_ids.map((id) => room.players[id]).filter(Boolean) ?? []
  const batInn  = game.innings_history.find((h) => h.batting_team_id === teamId)

  return (
    <div className="space-y-3 min-w-0">
      {/* Team header */}
      <div className="flex items-center gap-2">
        <span className={clsx('w-2.5 h-2.5 rounded-full flex-shrink-0', accentClass)} />
        <p className="text-sm font-bold uppercase tracking-widest text-white/60 truncate">
          {label}
          {batInn && (
            <span className="ml-2 font-mono normal-case tracking-normal text-white">
              {batInn.score}/{batInn.wickets}
            </span>
          )}
        </p>
      </div>

      {/* Batting table */}
      <div className="bg-surface-700/50 rounded-xl overflow-hidden">
        <div className="grid grid-cols-3 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white/30 border-b border-white/5">
          <span>Bat</span><span className="text-right">R (B)</span><span className="text-right">Status</span>
        </div>
        {players.map((p) => {
          const s = p.batting_stats
          return (
            <div key={p.id} className="grid grid-cols-3 px-3 py-2 text-sm border-b border-white/5 last:border-0 items-center">
              <span className={clsx('font-semibold truncate', s.is_out ? 'text-white/35' : 'text-white/90')}>
                {p.display_name}
              </span>
              <span className="text-right font-mono font-bold text-white">
                {s.runs_scored}<span className="text-white/35 font-normal text-xs"> ({s.balls_faced})</span>
              </span>
              {s.is_out
                ? <span className="text-right text-xs font-bold text-red-400/80">OUT</span>
                : <span className="text-right text-xs font-semibold text-brand-400">not out</span>}
            </div>
          )
        })}
      </div>

      {/* Bowling table */}
      {players.some((p) => p.bowling_stats.balls_bowled > 0) && (
        <div className="bg-surface-700/30 rounded-xl overflow-hidden">
          <div className="grid grid-cols-3 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white/30 border-b border-white/5">
            <span>Bowl</span><span className="text-right">W–R</span><span className="text-right">Balls</span>
          </div>
          {players.filter((p) => p.bowling_stats.balls_bowled > 0).map((p) => {
            const s = p.bowling_stats
            return (
              <div key={p.id} className="grid grid-cols-3 px-3 py-2 text-sm border-b border-white/5 last:border-0 items-center">
                <span className="text-white/80 font-semibold truncate">{p.display_name}</span>
                <span className="text-right font-mono font-bold">
                  <span className="text-purple-300">{s.wickets_taken}</span>
                  <span className="text-white/35">–{s.runs_conceded}</span>
                </span>
                <span className="text-right font-mono text-white/50">{s.balls_bowled}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function GameOverPhase() {
  const navigate       = useNavigate()
  const room           = useGameStore((s) => s.room)!
  const game           = useGame() as GameState
  const me             = useGameStore(selectLocalPlayer)
  const leaveRoom      = useGameStore((s) => s.leaveRoom)
  const returnToLobby  = useGameStore((s) => s.returnToLobby)

  const myTeamId   = me?.team_id ?? null
  const result     = game.final_result
  const winnerTid  = result?.winner_team_id as 'team_a' | 'team_b' | null | undefined
  const winnerLabel = winnerTid
    ? teamLabel(winnerTid, myTeamId, room.teams[winnerTid]?.name ?? '?')
    : null
  const mvp = result?.mvp_player_id ? room.players[result.mvp_player_id] : null

  // Column order: my team left, opponents right
  const teamIds: ('team_a' | 'team_b')[] = myTeamId === 'team_b'
    ? ['team_b', 'team_a'] : ['team_a', 'team_b']

  return (
    <div className="space-y-5">
      {/* Result banner */}
      <div className="text-center space-y-1.5 pb-1">
        <Trophy className="w-12 h-12 text-yellow-400 mx-auto" />
        <p className="text-white/40 text-xs uppercase tracking-widest mt-2">Match Result</p>
        {result?.is_tie
          ? <p className="text-3xl font-black text-white">It&apos;s a Tie!</p>
          : <p className="text-3xl font-black text-brand-300">{winnerLabel ?? '?'} wins!</p>}
        {!result?.is_tie && result?.margin_runs != null && (
          <p className="text-white/60">Won by {result.margin_runs} run{result.margin_runs === 1 ? '' : 's'}</p>
        )}
        {!result?.is_tie && result?.margin_wickets != null && (
          <p className="text-white/60">Won by {result.margin_wickets} wicket{result.margin_wickets === 1 ? '' : 's'}</p>
        )}
        {mvp && (
          <div className="flex items-center justify-center gap-2 text-white/60 pt-1">
            <Coins className="w-4 h-4 text-yellow-400" />
            MVP: <span className="font-bold text-white">{mvp.display_name}</span>
          </div>
        )}
      </div>

      {/* Innings summary */}
      <div className="space-y-2">
        {game.innings_history.map((h) => {
          const batLabel = teamLabel(h.batting_team_id, myTeamId, room.teams[h.batting_team_id]?.name ?? '—')
          return (
            <div key={h.innings_number} className="flex items-center justify-between bg-surface-700/50 rounded-xl px-4 py-2.5">
              <span className="text-white/50 text-sm">Inn {h.innings_number} · {batLabel}</span>
              <span className="font-mono font-bold text-white text-base">
                {h.score}<span className="text-white/35 font-normal">/{h.wickets}</span>
              </span>
            </div>
          )
        })}
      </div>

      {/* Side-by-side full scorecards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {teamIds.map((tid, idx) => (
          <TeamScorecard key={tid} teamId={tid}
            label={teamLabel(tid, myTeamId, room.teams[tid]?.name ?? '—')}
            accentClass={idx === 0 ? 'bg-brand-400' : 'bg-purple-400'}
            room={room} game={game} />
        ))}
      </div>

      {/* Action buttons */}
      <div className="grid grid-cols-2 gap-3 pt-1">
        <button
          onClick={() => { returnToLobby(); navigate('/room') }}
          className="flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-400 text-white font-bold py-3.5 rounded-xl transition-all text-sm"
        >
          <Play className="w-4 h-4" /> Back to Room
        </button>
        <button
          onClick={() => { leaveRoom(); navigate('/') }}
          className="flex items-center justify-center gap-2 bg-surface-600 hover:bg-surface-500 border border-white/10 text-white font-bold py-3.5 rounded-xl transition-all text-sm"
        >
          <LogOut className="w-4 h-4" /> Leave
        </button>
      </div>
    </div>
  )
}

// ─── Main GamePage ────────────────────────────────────────────────────────────

export default function GamePage() {
  const navigate   = useNavigate()
  const room       = useGameStore((s) => s.room)
  const roomCode   = useGameStore((s) => s.roomCode)
  const playerId   = useGameStore((s) => s.playerId)
  const connection = useGameStore((s) => s.connection)
  const leaveRoom  = useGameStore((s) => s.leaveRoom)
  const game       = useGame()

  useEffect(() => {
    if (!roomCode && !connection.connecting) navigate('/')
  }, [roomCode, connection.connecting, navigate])

  useEffect(() => {
    if (room && (!room.game || room.game.status === 'LOBBY')) navigate('/room')
  }, [room, navigate])

  if (!room || !roomCode) return null

  return (
    <div className="min-h-screen bg-surface-900 text-white flex flex-col">
      <WicketPopup />

      {/* Nav */}
      <nav className="flex items-center justify-between px-5 py-3.5 border-b border-white/5 bg-surface-900/80 backdrop-blur sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <Hand className="w-5 h-5 text-brand-400" strokeWidth={2.5} />
          <span className="font-bold tracking-tight">
            Hand<span className="text-brand-400">Cricket</span>
          </span>
          <span className="ml-2 font-mono text-xs text-white/25">{room.room_code}</span>
        </div>
        <div className="flex items-center gap-3">
          <div
            className={clsx(
              'flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full',
              connection.connected ? 'bg-brand-500/10 text-brand-400' : 'bg-red-500/10 text-red-400',
            )}
          >
            {connection.connected
              ? <Wifi className="w-3 h-3" />
              : <WifiOff className="w-3 h-3" />}
            {connection.connected ? 'Live' : 'Offline'}
          </div>
          {!connection.connected && (
            <button
              onClick={() => useGameStore.getState().reconnect()}
              className="text-xs text-white/40 hover:text-white flex items-center gap-1"
            >
              <RefreshCw className="w-3 h-3" /> Reconnect
            </button>
          )}
          <button
            onClick={() => { leaveRoom(); navigate('/') }}
            className="flex items-center gap-1.5 text-sm text-white/30 hover:text-red-400 transition-colors"
          >
            <LogOut className="w-4 h-4" /> Leave
          </button>
        </div>
      </nav>

      {/* Content */}
      <div className="flex-1 flex flex-col items-center px-4 py-8">
        {(() => {
          const activePlay = !!game && game.status !== 'LOBBY' && game.status !== 'GAME_OVER'
          return (
            <div className={clsx('w-full space-y-5', activePlay ? 'max-w-6xl' : 'max-w-2xl')}>
              {!game || game.status === 'LOBBY' ? (
                <div className="bg-surface-800 border border-white/5 rounded-2xl p-8 text-center">
                  <Loader2 className="w-8 h-8 animate-spin text-brand-400 mx-auto mb-3" />
                  <p className="text-white/50 text-sm">Waiting for the match to start…</p>
                </div>
              ) : activePlay ? (
                /* ── Running game: stadium display + chat side by side ── */
                <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-stretch gap-5">
                  <div className="space-y-5 min-w-0">
                    {!['TOSS', 'TOSS_DECISION'].includes(game.status) && (
                      <LiveScoreboard game={game} room={room} />
                    )}

                    {/* Action panel */}
                    <div className="bg-surface-800 border border-white/5 rounded-2xl p-5">
                      {game.status === 'TOSS' && <TossPhase game={game} />}
                      {(game.status === 'TOSS_DECISION' || game.status === 'INNINGS_SETUP') && (
                        <TossDecisionPhase game={game} />
                      )}
                      {['CHOOSING_NUMBERS', 'RESOLVING_BALL', 'PLAYER_OUT',
                        'SECOND_INNINGS', 'EXTRA_WICKET_VOTE', 'BOWLER_SWITCH',
                      ].includes(game.status) && (
                        <PlayPhase game={game} />
                      )}
                      {game.status === 'INNINGS_BREAK' && <InningsBreakPhase />}
                    </div>
                  </div>

                  {/* Chat sits to the RIGHT of the stadium display while the game runs */}
                  <ChatPanel room={room} playerId={playerId} className="h-full min-h-0" />
                </div>
              ) : (
                /* ── Game over: chat below the final result / MVP card ── */
                <>
                  <div className="bg-surface-800 border border-white/5 rounded-2xl p-5">
                    <GameOverPhase />
                  </div>
                  <ChatPanel room={room} playerId={playerId} />
                </>
              )}
            </div>
          )
        })()}
      </div>
    </div>
  )
}
