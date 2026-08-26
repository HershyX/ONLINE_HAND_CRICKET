import { type HTMLAttributes } from 'react'
import { AlertCircle, CheckCircle2, Info, XCircle } from 'lucide-react'
import clsx from 'clsx'

export interface AlertProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'error' | 'success' | 'info' | 'warning'
  title?: string
}

const config = {
  error: {
    icon: XCircle,
    wrapper: 'bg-red-500/10 border-red-500/20 text-red-400',
  },
  success: {
    icon: CheckCircle2,
    wrapper: 'bg-brand-500/10 border-brand-500/20 text-brand-400',
  },
  info: {
    icon: Info,
    wrapper: 'bg-blue-500/10 border-blue-500/20 text-blue-400',
  },
  warning: {
    icon: AlertCircle,
    wrapper: 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400',
  },
}

export function Alert({
  variant = 'error',
  title,
  className,
  children,
  ...rest
}: AlertProps) {
  const { icon: Icon, wrapper } = config[variant]
  return (
    <div
      role="alert"
      className={clsx(
        'flex items-start gap-3 border rounded-xl px-4 py-3 text-sm',
        wrapper,
        className,
      )}
      {...rest}
    >
      <Icon className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
      <div>
        {title && <p className="font-semibold mb-0.5">{title}</p>}
        <div className="opacity-80">{children}</div>
      </div>
    </div>
  )
}
