/**
 * Global error toast that surfaces store.lastError.
 * Mounts once in App.tsx — auto-dismisses after 4 seconds.
 */
import { useEffect } from 'react'
import { X, AlertCircle } from 'lucide-react'
import { useGameStore } from '../state/gameStore'

export function ErrorToast() {
  const lastError = useGameStore((s) => s.lastError)
  const clearError = useGameStore((s) => s.clearError)

  useEffect(() => {
    if (!lastError) return
    const t = setTimeout(clearError, 4000)
    return () => clearTimeout(t)
  }, [lastError, clearError])

  if (!lastError) return null

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-slide-up"
    >
      <div className="flex items-center gap-3 bg-red-950 border border-red-500/30 text-red-300 rounded-xl px-5 py-3 shadow-xl shadow-black/40 max-w-sm">
        <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-400" />
        <span className="text-sm font-medium">{lastError}</span>
        <button
          onClick={clearError}
          className="ml-2 opacity-60 hover:opacity-100 transition-opacity"
          aria-label="Dismiss"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
