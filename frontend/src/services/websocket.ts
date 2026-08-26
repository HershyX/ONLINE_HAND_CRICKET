/**
 * WebSocket client for Hand Cricket.
 *
 * Only transport and message routing live here — no game logic.
 */

import type {
  WSMessage,
  WSMessageType,
  ChooseNumberPayload,
  TossCallPayload,
  TossResponsePayload,
  TossDecisionPayload,
  SetReadyPayload,
  HandNumber,
} from '../types'
import { WS_BASE_URL } from '../utils/env'

type MessageListener<T = unknown> = (payload: T) => void

export class HandCricketWSClient {
  private socket: WebSocket | null = null
  private listeners = new Map<WSMessageType, Set<MessageListener>>()
  private onConnectCallbacks: Array<() => void> = []
  private onDisconnectCallbacks: Array<(ev: CloseEvent) => void> = []
  private onErrorCallbacks: Array<(ev: Event) => void> = []
  private currentUrl: string | null = null

  // ── Connection ──────────────────────────────────────────────────────────────

  connect(roomCode: string, playerId: string, displayName = ''): void {
    this.close()
    const url =
      `${WS_BASE_URL}/rooms/${roomCode}` +
      `?player_id=${encodeURIComponent(playerId)}` +
      `&display_name=${encodeURIComponent(displayName)}`
    this.currentUrl = url
    this.socket = new WebSocket(url)

    this.socket.onopen = () => this.onConnectCallbacks.forEach((cb) => cb())

    this.socket.onmessage = (ev: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(ev.data) as WSMessage
        this.dispatch(msg.type, msg.payload)
      } catch {
        console.error('[WS] Failed to parse message', ev.data)
      }
    }

    this.socket.onclose = (ev) =>
      this.onDisconnectCallbacks.forEach((cb) => cb(ev))

    this.socket.onerror = (ev) =>
      this.onErrorCallbacks.forEach((cb) => cb(ev))
  }

  reconnect(): void {
    if (!this.currentUrl) return
    const url = new URL(this.currentUrl)
    const parts = url.pathname.split('/')
    const roomCode = parts[parts.length - 1]
    const playerId = url.searchParams.get('player_id') ?? ''
    const displayName = url.searchParams.get('display_name') ?? ''
    this.connect(roomCode, playerId, displayName)
  }

  close(): void {
    if (this.socket) {
      this.socket.onopen = null
      this.socket.onmessage = null
      this.socket.onclose = null
      this.socket.onerror = null
      if (
        this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING
      ) {
        this.socket.close(1000, 'Client disconnect')
      }
      this.socket = null
    }
  }

  get isConnected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN
  }

  // ── Sending ─────────────────────────────────────────────────────────────────

  private send<T>(type: WSMessageType, payload: T): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Cannot send — socket not open', type)
      return
    }
    const msg: WSMessage<T> = {
      type,
      payload,
      timestamp: new Date().toISOString(),
    }
    this.socket.send(JSON.stringify(msg))
  }

  // ── Lobby actions ────────────────────────────────────────────────────────────

  sendUpdateName(displayName: string): void {
    this.send('UPDATE_NAME', { display_name: displayName })
  }

  sendSwitchTeam(teamId: 'team_a' | 'team_b'): void {
    this.send('SWITCH_TEAM', { team_id: teamId })
  }

  sendSetReady(payload: SetReadyPayload): void {
    this.send<SetReadyPayload>('SET_READY', payload)
  }

  sendStartMatch(): void {
    this.send('START_MATCH', {})
  }

  sendTransferHost(newHostId: string): void {
    this.send('TRANSFER_HOST', { new_host_id: newHostId })
  }

  sendReturnToLobby(): void {
    this.send('RETURN_TO_LOBBY', {})
  }

  sendChatMessage(content: string, scope: 'global' | 'team'): void {
    this.send('CHAT_MESSAGE', { content, scope })
  }

  // ── Game actions ─────────────────────────────────────────────────────────────

  sendTossCall(payload: TossCallPayload): void {
    this.send<TossCallPayload>('TOSS_CALL', payload)
  }

  sendTossResponse(payload: TossResponsePayload): void {
    this.send<TossResponsePayload>('TOSS_RESPONSE', payload)
  }

  sendTossDecision(payload: TossDecisionPayload): void {
    this.send<TossDecisionPayload>('TOSS_DECISION', payload)
  }

  sendChooseNumber(number: HandNumber): void {
    this.send<ChooseNumberPayload>('CHOOSE_NUMBER', { number })
  }

  sendVoteExtraWicket(candidatePlayerId: string): void {
    this.send('VOTE_EXTRA_WICKET', { candidate_player_id: candidatePlayerId })
  }

  sendRequestBowlerSwitch(incomingBowlerId: string): void {
    this.send('REQUEST_BOWLER_SWITCH', { incoming_bowler_id: incomingBowlerId })
  }

  sendRespondBowlerSwitch(accept: boolean): void {
    this.send('RESPOND_BOWLER_SWITCH', { accept })
  }

  sendRequestBatsmanSwitch(): void {
    this.send('REQUEST_BATSMAN_SWITCH', {})
  }

  sendRespondBatsmanSwitch(accept: boolean, chosenPlayerId?: string): void {
    this.send('RESPOND_BATSMAN_SWITCH', {
      accept,
      ...(chosenPlayerId ? { chosen_player_id: chosenPlayerId } : {}),
    })
  }

  sendStartSecondInnings(): void {
    this.send('START_SECOND_INNINGS', {})
  }

  sendPong(): void {
    this.send('PONG', {})
  }

  // ── Listeners ────────────────────────────────────────────────────────────────

  on<T>(type: WSMessageType, listener: MessageListener<T>): () => void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set())
    }
    this.listeners.get(type)!.add(listener as MessageListener)
    return () => this.off(type, listener as MessageListener)
  }

  off(type: WSMessageType, listener: MessageListener): void {
    this.listeners.get(type)?.delete(listener)
  }

  onConnect(cb: () => void): () => void {
    this.onConnectCallbacks.push(cb)
    return () => {
      this.onConnectCallbacks = this.onConnectCallbacks.filter((f) => f !== cb)
    }
  }

  onDisconnect(cb: (ev: CloseEvent) => void): () => void {
    this.onDisconnectCallbacks.push(cb)
    return () => {
      this.onDisconnectCallbacks = this.onDisconnectCallbacks.filter(
        (f) => f !== cb,
      )
    }
  }

  onError(cb: (ev: Event) => void): () => void {
    this.onErrorCallbacks.push(cb)
    return () => {
      this.onErrorCallbacks = this.onErrorCallbacks.filter((f) => f !== cb)
    }
  }

  private dispatch(type: WSMessageType, payload: unknown): void {
    if (type === 'PING') {
      this.sendPong()
      return
    }
    const set = this.listeners.get(type)
    if (set) set.forEach((listener) => listener(payload))
  }
}

export const wsClient = new HandCricketWSClient()
