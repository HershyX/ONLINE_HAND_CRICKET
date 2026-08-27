/**
 * Thin HTTP client for the Hand Cricket REST API.
 *
 * URL construction
 * ────────────────
 * API_BASE_URL is set to https://your-app.onrender.com/api in production.
 * Every path passed to apiFetch must start with "/" and NOT include "/api".
 *
 * Examples:
 *   apiFetch('/rooms')         → https://your-app.onrender.com/api/rooms
 *   apiFetch('/rooms/ABC123')  → https://your-app.onrender.com/api/rooms/ABC123
 *   apiFetch('/health')        → https://your-app.onrender.com/api/health
 */

import { API_BASE_URL, API_CONFIGURATION_ERROR } from '../utils/env'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string
  code?: string
}

export interface HealthResponse {
  status: 'ok'
  version: string
  environment: string
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
  if (API_CONFIGURATION_ERROR) {
    throw new Error(API_CONFIGURATION_ERROR)
  }

  // Ensure exactly one slash between base and path
  const base = API_BASE_URL.replace(/\/$/, '')
  const url  = `${base}/${path.replace(/^\//, '')}`

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
      // ignore parse errors, keep the status code message
    }
    throw new Error(detail)
  }

  if (res.status === 204) return undefined as unknown as T

  return res.json() as Promise<T>
}

// ─── Endpoints ────────────────────────────────────────────────────────────────

/** Ping the backend — verifies connectivity. */
export async function healthCheck(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health')
}

/** Create a new private room. Returns the room code + host player id. */
export async function createRoom(
  req: CreateRoomRequest,
): Promise<CreateRoomResponse> {
  return apiFetch<CreateRoomResponse>('/rooms', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

/** Fetch basic room info before opening a WebSocket connection. */
export async function getRoomInfo(
  roomCode: string,
): Promise<RoomInfoResponse> {
  return apiFetch<RoomInfoResponse>(`/rooms/${roomCode}`)
}
