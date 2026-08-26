import { type HTMLAttributes } from 'react'
import clsx from 'clsx'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: 'green' | 'yellow' | 'red' | 'gray' | 'blue'
  dot?: boolean
}

const variants = {
  green: 'bg-brand-500/10 text-brand-400 border-brand-500/20',
  yellow: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  red: 'bg-red-500/10 text-red-400 border-red-500/20',
  gray: 'bg-white/5 text-white/50 border-white/10',
  blue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
}

const dotColors = {
  green: 'bg-brand-400',
  yellow: 'bg-yellow-400',
  red: 'bg-red-400',
  gray: 'bg-white/40',
  blue: 'bg-blue-400',
}

export function Badge({
  variant = 'gray',
  dot = false,
  className,
  children,
  ...rest
}: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full border',
        variants[variant],
        className,
      )}
      {...rest}
    >
      {dot && (
        <span
          className={clsx('w-1.5 h-1.5 rounded-full flex-shrink-0', dotColors[variant])}
        />
      )}
      {children}
    </span>
  )
}
