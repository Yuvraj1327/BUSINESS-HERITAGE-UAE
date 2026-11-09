import { ShieldX } from 'lucide-react'
import { Link } from 'react-router-dom'
import { EmptyState } from '@/components/common/empty-state'
import { Button } from '@/components/ui/button'

/** Shown in place of a page the signed-in user is not allowed to open (the URL is left as typed). */
export function ForbiddenPage() {
  return (
    <div className="mx-auto max-w-xl p-6">
      <EmptyState
        icon={ShieldX}
        title="Access denied"
        description="Your account does not have permission to open this page."
        action={
          <Button asChild>
            <Link to="/">Back to home</Link>
          </Button>
        }
      />
    </div>
  )
}
