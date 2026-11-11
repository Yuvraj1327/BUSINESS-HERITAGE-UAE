import { ShieldX } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '@/components/common/empty-state'
import { Button } from '@/components/ui/button'

interface PermissionDeniedProps {
  title?: string
  description?: string
  action?: ReactNode
}

/** "You may not open this" block, used by route guards and anywhere a section is withheld. */
export function PermissionDenied({
  title = 'Access denied',
  description = 'Your account does not have permission to open this page.',
  action,
}: PermissionDeniedProps) {
  return (
    <EmptyState
      icon={ShieldX}
      title={title}
      description={description}
      action={
        action ?? (
          <Button asChild>
            <Link to="/">Back to dashboard</Link>
          </Button>
        )
      }
    />
  )
}
