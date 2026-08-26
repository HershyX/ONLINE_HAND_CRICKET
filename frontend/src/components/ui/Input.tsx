import { type InputHTMLAttributes, forwardRef } from 'react'
import clsx from 'clsx'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, id, className, ...rest }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="text-sm font-medium text-white/60"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={clsx(
            'w-full bg-surface-700 border rounded-xl px-4 py-3 text-white',
            'placeholder-white/20 transition-colors',
            'focus:outline-none focus:ring-1 focus:ring-brand-500/30',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            error
              ? 'border-red-500/40 focus:border-red-500/60'
              : 'border-white/10 focus:border-brand-500/60',
            className,
          )}
          {...rest}
        />
        {error && <p className="text-xs text-red-400">{error}</p>}
        {hint && !error && <p className="text-xs text-white/30">{hint}</p>}
      </div>
    )
  },
)

Input.displayName = 'Input'
