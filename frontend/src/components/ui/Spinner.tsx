import { Loader2 } from 'lucide-react'
import clsx from 'clsx'

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
  label?: string
}

const sizes = {
  sm: 'w-4 h-4',
  md: 'w-6 h-6',
  lg: 'w-10 h-10',
}

export function Spinner({ size = 'md', className, label }: SpinnerProps) {
  return (
    <div className="flex flex-col items-center gap-3">
      <Loader2
        className={clsx('animate-spin text-brand-400', sizes[size], className)}
        aria-hidden="true"
      />
      {label && <p className="text-white/50 text-sm">{label}</p>}
    </div>
  )
}
