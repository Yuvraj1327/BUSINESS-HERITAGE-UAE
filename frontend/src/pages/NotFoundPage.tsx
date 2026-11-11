import { SearchX } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/auth/use-auth'
import { EmptyState } from '@/components/common/empty-state'
import { LoadingIndicator } from '@/components/common/loading-indicator'
import { Button } from '@/components/ui/button'
import { RootLayout } from '@/layouts/RootLayout'

function NotFoundContent() {
  return (
    <div className="mx-auto max-w-xl p-6">
      <EmptyState
        icon={SearchX}
        title="Page not found"
        description="The page you are looking for does not exist or has moved."
        action={
          <Button asChild>
            <Link to="/">Back to start</Link>
          </Button>
        }
      />
    </div>
  )
}

/**
 * Unknown URL. Signed-in users keep the application shell (navigation stays usable); visitors who are not signed
 * in get the bare page. Never reveals whether a page exists behind a permission.
 */
export function NotFoundPage() {
  const { status, profileStatus } = useAuth()
  if (status === 'loading' || (status === 'authenticated' && profileStatus === 'loading')) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <LoadingIndicator />
      </div>
    )
  }
  if (status === 'authenticated' && profileStatus === 'ready') {
    return (
      <RootLayout>
        <NotFoundContent />
      </RootLayout>
    )
  }
  return <NotFoundContent />
}
