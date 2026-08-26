/**
 * Zustand store — single source of client-side UI state.
 * No game logic lives here.
 */

import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import type {
  Room,
  ConnectionState,
  GameState,
  HandNumber,
  TossDecision,
  TeamId,
  StartMatchValidation,
  ChatMessage,
} from '../types'
import { wsClient } from '../services/websocket'
import { createRoom as apiCreateRoom, getRoomInfo } from '../services/api'
import type { CreateRoomRequest } from '../services/api'

// ─── State shape ──────────────────────────────────────────────────────────────

interface GameStore {
  playerId: string | null
  displayName: string | null
  room: Room | null
  roomCode: string | null
  connection: ConnectionState
  lastError: string | null
  dismissalNotice: string | null
  /** All chat messages received this session (global + team scoped) */
  chatMessages: ChatMessage[]

  // ── Actions ──────────────────────────────────────────────────────────────────

  setDisplayName: (name: string) => void
  createRoom: (req: CreateRoomRequest) => Promise<void>
  joinRoom: (roomCode: string, displayName: string) => Promise<void>
  reconnect: () => void
  leaveRoom: () => void

  // Lobby actions
  updateName: (name: string) => void
  switchTeam: (teamId: TeamId) => void
  setReady: (ready: boolean) => void
  startMatch: () => void
  transferHost: (newHostId: string) => void
  returnToLobby: () => void
  sendChat: (content: string, scope: 'global' | 'team') => void

  // Game actions
  callToss: (call: 'ODD' | 'EVEN', number: number) => void
  respondToss: (number: number) => void
  decideToss: (decision: TossDecision) => void
  chooseNumber: (number: HandNumber) => void
  voteExtraWicket: (candidatePlayerId: string) => void
  requestBowlerSwitch: (incomingBowlerId: string) => void
  respondBowlerSwitch: (accept: boolean) => void
  requestBatsmanSwitch: () => void
  respondBatsmanSwitch: (accept: boolean, chosenPlayerId?: string) => void
  startSecondInnings: () => void

  clearError: () => void
  clearDismissalNotice: () => void

  // ── Internal setters ─────────────────────────────────────────────────────────

  _setRoom: (room: Room) => void
  _setGameState: (game: GameState) => void
  _setConnected: (connected: boolean) => void
  _setConnecting: (connecting: boolean) => void
  _setConnectionError: (error: string | null) => void
  _setError: (error: string) => void
  _setPlayerId: (id: string) => void
  _setDismissalNotice: (name: string) => void
  _addChatMessage: (msg: ChatMessage) => void
}

// ─── Session persistence ──────────────────────────────────────────────────────

const STORAGE_KEY = 'hc_session'

interface StoredSession {
  playerId: string
  displayName: string
  roomCode: string
}

function saveSession(s: StoredSession) {
  try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s)) } catch { /* ok */ }
}

function loadSession(): StoredSession | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as StoredSession) : null
  } catch { return null }
}

function clearSession() {
  try { sessionStorage.removeItem(STORAGE_KEY) } catch { /* ok */ }
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useGameStore = create<GameStore>()(
  devtools(
    (set, get) => ({
      playerId: null,
      displayName: null,
      room: null,
      roomCode: null,
      connection: { connected: false, connecting: false, error: null },
      lastError: null,
      dismissalNotice: null,
      chatMessages: [],

      setDisplayName: (name) => set({ displayName: name }),

      createRoom: async (req) => {
        set((s) => ({
          connection: { ...s.connection, connecting: true, error: null },
          lastError: null,
        }))
        try {
          const { room_code, host_player_id } = await apiCreateRoom(req)
          const displayName = req.display_name
          set({ playerId: host_player_id, displayName, roomCode: room_code })
          saveSession({ playerId: host_player_id, displayName, roomCode: room_code })
          wsClient.connect(room_code, host_player_id, displayName)
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'Failed to create room'
          set((s) => ({
            connection: { ...s.connection, connecting: false, error: msg },
            lastError: msg,
          }))
          throw err
        }
      },

      joinRoom: async (roomCode, displayName) => {
        set((s) => ({
          connection: { ...s.connection, connecting: true, error: null },
          lastError: null,
        }))
        try {
          await getRoomInfo(roomCode)
          const tempId = `join_${Date.now()}`
          set({ displayName, roomCode, playerId: tempId })
          saveSession({ playerId: tempId, displayName, roomCode })
          wsClient.connect(roomCode, tempId, displayName)
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'Failed to join room'
          set((s) => ({
            connection: { ...s.connection, connecting: false, error: msg },
            lastError: msg,
          }))
          throw err
        }
      },

      reconnect: () => {
        const session = loadSession()
        if (!session) return
        set({
          playerId: session.playerId,
          displayName: session.displayName,
          roomCode: session.roomCode,
        })
        wsClient.connect(session.roomCode, session.playerId, session.displayName)
      },

      leaveRoom: () => {
        wsClient.close()
        clearSession()
        set({
          room: null,
          roomCode: null,
          playerId: null,
          chatMessages: [],
          connection: { connected: false, connecting: false, error: null },
        })
      },

      // ── Lobby ─────────────────────────────────────────────────────────────

      updateName: (name) => {
        // Update local display name optimistically for smooth UI
        const trimmed = name.trim()
        set({ displayName: trimmed })
        // Save to session so reconnect preserves the new name
        const s = get()
        if (s.roomCode && s.playerId) {
          saveSession({ playerId: s.playerId, displayName: trimmed, roomCode: s.roomCode })
        }
        wsClient.sendUpdateName(trimmed)
      },

      switchTeam: (teamId) => {
        wsClient.sendSwitchTeam(teamId)
      },

      setReady: (ready) => {
        wsClient.sendSetReady({ ready })
      },

      startMatch: () => {
        wsClient.sendStartMatch()
      },

      transferHost: (newHostId) => wsClient.sendTransferHost(newHostId),

      returnToLobby: () => wsClient.sendReturnToLobby(),

      sendChat: (content, scope) => wsClient.sendChatMessage(content, scope),

      // ── Game ──────────────────────────────────────────────────────────────

      callToss: (call, number) => wsClient.sendTossCall({ call, number }),
      respondToss: (number) => wsClient.sendTossResponse({ number }),
      decideToss: (decision) => wsClient.sendTossDecision({ decision }),
      chooseNumber: (number) => wsClient.sendChooseNumber(number),
      voteExtraWicket: (candidatePlayerId) => wsClient.sendVoteExtraWicket(candidatePlayerId),
      requestBowlerSwitch: (incomingBowlerId) =>
        wsClient.sendRequestBowlerSwitch(incomingBowlerId),
      respondBowlerSwitch: (accept) => wsClient.sendRespondBowlerSwitch(accept),
      requestBatsmanSwitch: () => wsClient.sendRequestBatsmanSwitch(),
      respondBatsmanSwitch: (accept, chosenPlayerId) =>
        wsClient.sendRespondBatsmanSwitch(accept, chosenPlayerId),
      startSecondInnings: () => wsClient.sendStartSecondInnings(),

      clearError: () => set({ lastError: null }),
      clearDismissalNotice: () => set({ dismissalNotice: null }),

      // ── Internal ──────────────────────────────────────────────────────────

      _setRoom: (room) => set({ room }),

      _setGameState: (game) =>
        set((s) => ({ room: s.room ? { ...s.room, game } : s.room })),

      _setConnected: (connected) =>
        set((s) => ({ connection: { ...s.connection, connected, connecting: false } })),

      _setConnecting: (connecting) =>
        set((s) => ({ connection: { ...s.connection, connecting } })),

      _setConnectionError: (error) =>
        set((s) => ({ connection: { ...s.connection, error, connecting: false } })),

      _setError: (error) => set({ lastError: error }),

      _setPlayerId: (id) => {
        set({ playerId: id })
        const s = get()
        if (s.roomCode && s.displayName) {
          saveSession({ playerId: id, displayName: s.displayName, roomCode: s.roomCode })
        }
      },

      _setDismissalNotice: (name) => set({ dismissalNotice: name }),

      _addChatMessage: (msg) =>
        set((s) => ({
          chatMessages: [...s.chatMessages.slice(-199), msg],
        })),
    }),
    { name: 'HandCricketStore' },
  ),
)

// ─── Selectors ────────────────────────────────────────────────────────────────

export const selectLocalPlayer = (s: GameStore) =>
  s.playerId && s.room ? (s.room.players[s.playerId] ?? null) : null

export const selectGame = (s: GameStore) => s.room?.game ?? null
export const selectIsHost = (s: GameStore) =>
  !!s.playerId && s.room?.host_id === s.playerId

export const selectPlayers = (s: GameStore) =>
  s.room ? Object.values(s.room.players) : []

export const selectTeams = (s: GameStore) =>
  s.room ? Object.values(s.room.teams) : []

export const selectTeamPlayers = (teamId: TeamId) => (s: GameStore) => {
  if (!s.room) return []
  return Object.values(s.room.players).filter((p) => p.team_id === teamId)
}

export const selectAllReady = (s: GameStore) => {
  if (!s.room) return false
  const players = Object.values(s.room.players)
  return (
    players.length >= 2 && players.every((p) => !p.connected || p.ready)
  )
}

/** Compute start-match validation from current room state (client-side mirror). */
export const selectStartValidation = (
  s: GameStore,
): StartMatchValidation => {
  const room = s.room
  if (!room) return { can_start: false, reasons: ['No room'] }

  const reasons: string[] = []
  const connected = Object.values(room.players).filter((p) => p.connected)

  if (room.host_id !== s.playerId) {
    reasons.push('Only the host can start')
  }
  if (connected.length < 2) {
    reasons.push('Need at least 2 players')
  }
  // Block if a game is actively in progress (not just GAME_OVER)
  const blockingStatuses = ['TOSS', 'TOSS_DECISION', 'INNINGS_SETUP',
    'CHOOSING_NUMBERS', 'RESOLVING_BALL', 'PLAYER_OUT', 'EXTRA_WICKET_VOTE',
    'BOWLER_SWITCH', 'INNINGS_BREAK', 'SECOND_INNINGS']
  if (room.game && blockingStatuses.includes(room.game.status)) {
    reasons.push('A game is already in progress')
  }
  const notReady = connected.filter((p) => !p.ready)
  if (notReady.length > 0) {
    reasons.push(`Waiting for: ${notReady.map((p) => p.display_name).join(', ')}`)
  }
  const teamA = Object.values(room.players).filter(
    (p) => p.connected && p.team_id === 'team_a',
  ).length
  const teamB = Object.values(room.players).filter(
    (p) => p.connected && p.team_id === 'team_b',
  ).length
  if (teamA === 0 || teamB === 0) {
    reasons.push('Both teams need at least one player')
  } else if (Math.abs(teamA - teamB) > 1) {
    reasons.push(`Teams too unequal (${teamA} vs ${teamB})`)
  }

  return { can_start: reasons.length === 0, reasons }
}
