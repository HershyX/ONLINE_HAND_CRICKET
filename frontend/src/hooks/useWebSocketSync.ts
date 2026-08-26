/**
 * useWebSocketSync
 *
 * Mounts once at the app root. Subscribes to all WS events and writes
 * server-authoritative state into the Zustand store.
 * No game logic runs here — we trust and forward what the server sends.
 *
 * State-version deduplication
 * ───────────────────────────
 * Every GAME_STATE / BALL_RESOLVED / PLAYER_OUT / INNINGS_COMPLETE /
 * GAME_OVER / GAME_STARTED / EXTRA_WICKET_VOTE / BOWLER_SWITCH event
 * carries game.state_version.  We track the last version we applied and
 * silently discard any event whose version is not strictly greater.
 * This prevents out-of-order WebSocket updates from rolling back state.
 *
 * ROOM_STATE carries the full room (including the embedded game). We always
 * apply ROOM_STATE unconditionally — it is the authoritative snapshot sent
 * on join/reconnect — but we also check the embedded game version before
 * updating the game slice to avoid racing with a concurrent GAME_STATE.
 */

import { useEffect, useRef } from 'react'
import { wsClient } from '../services/websocket'
import { useGameStore } from '../state/gameStore'
import type {
  RoomStatePayload,
  GameState,
  ErrorPayload,
  Room,
} from '../types'

export function useWebSocketSync(): void {
  const store = useGameStore()
  // Track the state_version of the last game event we applied.
  const lastVersionRef = useRef<number>(-1)

  /**
   * Apply a game state update only if its version is strictly newer than
   * what we have already applied.  Pass version=-1 to force-apply
   * (used for ROOM_STATE snapshots on reconnect).
   */
  function applyGame(game: GameState, force = false): void {
    if (!force && game.state_version <= lastVersionRef.current) {
      return  // stale — discard silently
    }
    lastVersionRef.current = game.state_version
    store._setGameState(game)
  }

  useEffect(() => {
    // ── Connection lifecycle ──────────────────────────────────────────────────
    const unsubConnect = wsClient.onConnect(() => {
      store._setConnected(true)
      store._setConnectionError(null)
      // Reset version filter on each new connection so we accept the fresh
      // snapshot sent immediately after connect.
      lastVersionRef.current = -1
    })

    const unsubDisconnect = wsClient.onDisconnect((ev) => {
      store._setConnected(false)
      if (!ev.wasClean) {
        store._setConnectionError('Connection lost — click Reconnect to rejoin.')
      }
    })

    const unsubWsError = wsClient.onError(() => {
      store._setConnectionError('WebSocket error — check your connection.')
      store._setConnected(false)
    })

    // ── Room-level events ─────────────────────────────────────────────────────

    // ROOM_STATE is the authoritative full snapshot.
    // Always update the room (players, teams, connection state).
    // Also update the embedded game — but only if it is newer than what we
    // already have (to avoid racing with a concurrent GAME_STATE).
    const unsubRoomState = wsClient.on<RoomStatePayload>(
      'ROOM_STATE',
      ({ room, your_player_id }) => {
        store._setRoom(room)
        if (room.game) {
          // force=true: ROOM_STATE is a full snapshot, always trust it.
          // We still update lastVersionRef so subsequent GAME_STATE events
          // with the same version don't re-apply unnecessarily.
          if (room.game.state_version > lastVersionRef.current) {
            lastVersionRef.current = room.game.state_version
            store._setGameState(room.game)
          }
        }
        if (your_player_id && your_player_id !== store.playerId) {
          store._setPlayerId(your_player_id)
        }
      },
    )

    const roomFromPayload = ({ room }: { room: Room }) => store._setRoom(room)

    const unsubPlayerJoined  = wsClient.on<{ room: Room }>('PLAYER_JOINED',       roomFromPayload)
    const unsubPlayerLeft    = wsClient.on<{ room: Room }>('PLAYER_LEFT',         roomFromPayload)
    const unsubPlayerUpdated = wsClient.on<{ room: Room }>('PLAYER_UPDATED',      roomFromPayload)
    const unsubPlayerReady   = wsClient.on<{ room: Room }>('PLAYER_READY',        roomFromPayload)
    const unsubReadyChanged  = wsClient.on<{ room: Room }>('READY_STATE_CHANGED', roomFromPayload)
    const unsubTeamUpdated   = wsClient.on<{ room: Room }>('TEAM_UPDATED',        roomFromPayload)

    // ── Game-level events — all version-gated ─────────────────────────────────

    const versioned = (game: GameState) => applyGame(game)

    const unsubGameStarted     = wsClient.on<GameState>('GAME_STARTED', (game) => {
      // A new match always resets state_version to 0.  Force-apply so the
      // version filter doesn't discard it as "stale" from the prior game.
      lastVersionRef.current = -1
      applyGame(game)
    })
    const unsubGameState       = wsClient.on<GameState>('GAME_STATE',       versioned)
    const unsubBallResolved    = wsClient.on<GameState>('BALL_RESOLVED',    versioned)
    const unsubInningsComplete = wsClient.on<GameState>('INNINGS_COMPLETE', versioned)
    const unsubExtraWicketVote = wsClient.on<GameState>('EXTRA_WICKET_VOTE', versioned)
    const unsubBowlerSwitch    = wsClient.on<GameState>('BOWLER_SWITCH',    versioned)
    const unsubGameOver        = wsClient.on<GameState>('GAME_OVER',        versioned)

    // PLAYER_OUT: version-gate the game update AND trigger the wicket popup.
    const unsubPlayerOut = wsClient.on<GameState>('PLAYER_OUT', (game) => {
      if (game.state_version <= lastVersionRef.current) return  // stale
      lastVersionRef.current = game.state_version
      store._setGameState(game)
      const name = game.innings?.last_dismissed_name
      if (name) store._setDismissalNotice(name)
    })

    // ── Error ─────────────────────────────────────────────────────────────────
    const unsubError = wsClient.on<ErrorPayload>('ERROR', ({ message }) => {
      store._setError(message)
    })

    // ── Chat ──────────────────────────────────────────────────────────────────
    const unsubChat = wsClient.on<import('../types').ChatMessage>(
      'CHAT_MESSAGE',
      (msg) => { store._addChatMessage(msg) },
    )

    return () => {
      unsubConnect()
      unsubDisconnect()
      unsubWsError()
      unsubRoomState()
      unsubPlayerJoined()
      unsubPlayerLeft()
      unsubPlayerUpdated()
      unsubPlayerReady()
      unsubReadyChanged()
      unsubTeamUpdated()
      unsubGameStarted()
      unsubGameState()
      unsubBallResolved()
      unsubPlayerOut()
      unsubInningsComplete()
      unsubExtraWicketVote()
      unsubBowlerSwitch()
      unsubGameOver()
      unsubError()
      unsubChat()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
