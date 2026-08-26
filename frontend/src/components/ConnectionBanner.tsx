/**
 * Thin banner shown at the top when the WS connection drops mid-game.
 * Only visible when the user is already in a room.
 */
import { WifiOff, RefreshCw } from 'lucide-react'
import { useGameStore } from '../state/gameStore'
import { wsClient } from '../services/websocket'

export function ConnectionBanner() {
  const connected = useGameStore((s) => s.connection.connected)
  const room = useGameStore((s) => s.room)

  // Only show when we were in a room and lost the connection.
  if (connected || !room) return null

  return (
    <div
      role="status"
      className="fixed top-0 inset-x-0 z-50 bg-yellow-950 border-b border-yellow-500/20 text-yellow-300 px-4 py-2 flex items-center justify-center gap-3 text-sm"
    >
      <WifiOff className="w-4 h-4 flex-shrink-0" />
      <span>Connection lost. Your game state is preserved on the server.</span>
      <button
        onClick={() => wsClient.reconnect()}
        className="flex items-center gap-1 font-semibold underline underline-offset-2 hover:text-yellow-200 transition-colors"
      >
        <RefreshCw className="w-3 h-3" />
        Reconnect
      </button>
    </div>
  )
}
