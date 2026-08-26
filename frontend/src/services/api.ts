/**
 * Thin HTTP client for the Hand Cricket REST API.
 *
 * All game-critical decisions happen over WebSocket; the REST API is used only
 * for pre-game actions (health check, create room, look up a room before
 * connecting via WS).
 */

import { API_BASE_URL } from '../utils/env'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string
  code?: string
}

export interface HealthResponse {
  status: 'ok'
  version: string
  timestamp: string
}

export interface CreateRoomResponse {
  room_code: string
  host_player_id: string
}

export interface CreateRoomRequest {
  display_name: string
  overs_per_innings?: number
}

export interface RoomInfoResponse {
  room_code: string
  player_count: number
  max_players: number
  room_status: string
}

// ─── Core fetch wrapper ───────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE_URL}${path}`
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as ApiError
      detail = body.detail ?? detail
    } catch {
      // ignore parse error, keep default message
    }
    throw new Error(detail)
  }

  // 204 No Content
  if (res.status === 204) return undefined as unknown as T

  return res.json() as Promise<T>
}

// ─── Endpoints ────────────────────────────────────────────────────────────────

/** Ping the backend – used to verify connectivity on app start. */
export async function healthCheck(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health')
}

/** Create a new room and get the room code + initial player id back. */
export async function createRoom(
  req: CreateRoomRequest,
): Promise<CreateRoomResponse> {
  return apiFetch<CreateRoomResponse>('/rooms', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

/** Fetch basic info about a room before joining via WebSocket. */
export async function getRoomInfo(
  roomCode: string,
): Promise<RoomInfoResponse> {
  return apiFetch<RoomInfoResponse>(`/rooms/${roomCode}`)
}
