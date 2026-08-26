import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Hand, Loader2, AlertCircle } from 'lucide-react'
import { useGameStore } from '../state/gameStore'

export default function CreateRoomPage() {
  const navigate = useNavigate()
  const createRoom = useGameStore((s) => s.createRoom)
  const connection = useGameStore((s) => s.connection)

  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const name = displayName.trim()
    if (!name) {
      setError('Enter your display name.')
      return
    }
    if (name.length < 2 || name.length > 20) {
      setError('Name must be 2–20 characters.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      await createRoom({ display_name: name, overs_per_innings: 0 })
      navigate('/room')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create room.')
      setLoading(false)
    }
  }

  const isLoading = loading || connection.connecting

  return (
    <div className="min-h-screen bg-surface-900 text-white flex flex-col">
      {/* Nav */}
      <nav className="flex items-center gap-4 px-6 py-4 border-b border-white/5">
        <button
          onClick={() => navigate('/')}
          className="w-11 h-11 flex items-center justify-center rounded-xl bg-white/5 hover:bg-white/10 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex items-center gap-2">
          <Hand className="w-5 h-5 text-brand-400" />
          <span className="font-bold tracking-tight">
            Hand<span className="text-brand-400">Cricket</span>
          </span>
        </div>
      </nav>

      {/* Content */}
      <div className="flex-1 flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-md animate-slide-up">
          <div className="mb-8">
            <h1 className="text-3xl font-black tracking-tight mb-2">
              Create a Room
            </h1>
            <p className="text-white/40">
              Set up a private match and share the code with your opponent.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Display name */}
            <div>
              <label
                htmlFor="displayName"
                className="block text-sm font-medium text-white/60 mb-2"
              >
                Your Display Name
              </label>
              <input
                id="displayName"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="e.g. Virat"
                maxLength={20}
                disabled={isLoading}
                className="w-full bg-surface-700 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/20 focus:outline-none focus:border-brand-500/60 focus:ring-1 focus:ring-brand-500/30 transition-colors disabled:opacity-50"
              />
            </div>

            {/* Error */}
            {(error ?? connection.error) && (
              <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-red-400 text-sm">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                {error ?? connection.error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-brand-500 hover:bg-brand-400 disabled:bg-brand-700 disabled:cursor-not-allowed text-white font-bold py-4 rounded-xl text-base transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-brand-900/30"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Creating room…
                </>
              ) : (
                'Create Room'
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-white/30 text-sm">
            Already have a code?{' '}
            <button
              onClick={() => navigate('/join')}
              className="text-brand-400 hover:text-brand-300 transition-colors font-medium"
            >
              Join a room
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
