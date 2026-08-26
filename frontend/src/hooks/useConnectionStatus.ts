/**
 * Convenience hook — returns the current WS connection state.
 */
import { useGameStore } from '../state/gameStore'
import type { ConnectionState } from '../types'

export function useConnectionStatus(): ConnectionState {
  return useGameStore((s) => s.connection)
}
