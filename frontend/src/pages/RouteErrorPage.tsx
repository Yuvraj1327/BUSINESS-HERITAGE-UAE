import { isRouteErrorResponse, useRouteError } from 'react-router-dom'
import { ErrorState } from '@/components/common/error-state'

export function RouteErrorPage() {
  const error = useRouteError()
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : 'Unexpected error.'
  return (
    <div className="mx-auto max-w-xl p-6">
      <ErrorState
        title="This page could not be displayed"
        message={message}
        onRetry={() => window.location.reload()}
      />
    </div>
  )
}
