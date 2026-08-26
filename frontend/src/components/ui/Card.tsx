import { type HTMLAttributes, forwardRef } from 'react'
import clsx from 'clsx'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Highlight the card border with a brand glow. */
  highlight?: boolean
  padding?: 'sm' | 'md' | 'lg' | 'none'
}

const paddings = {
  none: '',
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-8',
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ highlight = false, padding = 'md', className, children, ...rest }, ref) => (
    <div
      ref={ref}
      className={clsx(
        'bg-surface-800 border rounded-2xl transition-colors',
        highlight ? 'border-brand-500/40' : 'border-white/5',
        paddings[padding],
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  ),
)

Card.displayName = 'Card'
