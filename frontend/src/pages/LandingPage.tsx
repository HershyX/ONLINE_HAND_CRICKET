import { useNavigate } from 'react-router-dom'
import { Trophy, Users, Zap, Shield, ChevronRight, Hand, Instagram, Linkedin, Mail, Github } from 'lucide-react'

const features = [
  {
    icon: Users,
    title: 'Real Multiplayer',
    desc: 'Play live against real friends in private rooms — no bots, no fakes.',
  },
  {
    icon: Zap,
    title: 'Instant Play',
    desc: 'Create a room in seconds, share the code, start playing.',
  },
  {
    icon: Shield,
    title: 'Fair & Authoritative',
    desc: 'Every run, wicket and decision is validated server-side.',
  },
  {
    icon: Trophy,
    title: 'Full Match Stats',
    desc: 'Live scorecard, innings history, MVP tracking.',
  },
]

export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-surface-900 text-white flex flex-col">
      {/* ── Nav ── */}
      <nav className="flex items-center justify-between px-6 py-4 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Hand className="w-7 h-7 text-brand-400" strokeWidth={2.5} />
          <span className="font-bold text-xl tracking-tight">
            Hand<span className="text-brand-400">Cricket</span>
          </span>
        </div>
        <button
          onClick={() => navigate('/join')}
          className="text-sm font-medium text-white/70 hover:text-white transition-colors"
        >
          Join a room →
        </button>
      </nav>

      {/* ── Hero ── */}
      <section className="flex-1 flex flex-col items-center justify-center px-6 py-20 text-center bg-hero-pattern">
        <div className="inline-flex items-center gap-2 bg-brand-500/10 border border-brand-500/20 text-brand-400 text-xs font-semibold uppercase tracking-widest px-4 py-1.5 rounded-full mb-8 animate-fade-in">
          <span className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-pulse" />
          Live multiplayer — no timer, play at your own pace
        </div>

        <h1 className="text-5xl sm:text-7xl font-black tracking-tighter leading-none mb-6 animate-slide-up">
          The classic game,
          <br />
          <span className="text-brand-400">online & live.</span>
        </h1>

        <p className="max-w-xl text-white/50 text-lg mb-12 animate-slide-up">
          Hand Cricket brings the backyard favourite to your browser. Create a
          private room, invite a friend, and settle it the old-fashioned way.
        </p>

        <div className="flex flex-col sm:flex-row gap-4 animate-slide-up">
          <button
            onClick={() => navigate('/create')}
            className="group flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-400 text-white font-bold px-8 py-4 rounded-xl text-lg transition-all duration-200 shadow-lg shadow-brand-900/40 hover:shadow-brand-500/30 hover:scale-105"
          >
            Create a Room
            <ChevronRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
          </button>
          <button
            onClick={() => navigate('/join')}
            className="flex items-center justify-center gap-2 bg-white/5 hover:bg-white/10 border border-white/10 text-white font-bold px-8 py-4 rounded-xl text-lg transition-all duration-200"
          >
            Join a Room
          </button>
        </div>
      </section>

      {/* ── Features ── */}
      <section className="px-6 py-16 border-t border-white/5">
        <div className="max-w-4xl mx-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map(({ icon: Icon, title, desc }) => (
            <div
              key={title}
              className="bg-surface-800 border border-white/5 rounded-2xl p-6 hover:border-brand-500/30 transition-colors"
            >
              <div className="w-10 h-10 bg-brand-500/10 rounded-xl flex items-center justify-center mb-4">
                <Icon className="w-5 h-5 text-brand-400" />
              </div>
              <h3 className="font-bold text-white mb-1">{title}</h3>
              <p className="text-sm text-white/40 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-white/5 px-6 py-8">
        <div className="max-w-4xl mx-auto space-y-4">
          <p className="text-center text-white/40 text-sm">
            A Fun Project Created By Harshit Sajjanapu
          </p>
          <div className="flex items-center justify-center gap-6 text-white/30">
            <a
              href="https://www.instagram.com/x.hershy.x/"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-sm hover:text-brand-400 transition-colors"
              aria-label="Instagram"
            >
              <Instagram className="w-4 h-4" />
              @x.hershy.x
            </a>
            <a
              href="https://www.linkedin.com/in/harshit-sajjanapu-9b569a375/"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-sm hover:text-brand-400 transition-colors"
              aria-label="LinkedIn"
            >
              <Linkedin className="w-4 h-4" />
              LinkedIn
            </a>
            <a
              href="mailto:harshit.sajjanapu@gmail.com"
              className="flex items-center gap-1.5 text-sm hover:text-brand-400 transition-colors"
              aria-label="Email"
            >
              <Mail className="w-4 h-4" />
              harshit.sajjanapu@gmail.com
            </a>
            <a
              href="https://github.com/HershyX"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-sm hover:text-brand-400 transition-colors"
              aria-label="GitHub"
            >
              <Github className="w-4 h-4" />
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}
