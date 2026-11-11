import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { AuthProvider } from '@/auth/AuthProvider'
import { ErrorBoundary } from '@/components/common/error-boundary'
import { Toaster } from '@/components/ui/sonner'
import { queryClient } from '@/lib/query-client'
import { router } from '@/routes'
import { ThemeProvider } from '@/theme/ThemeProvider'

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ThemeProvider>
            <RouterProvider router={router} />
          </ThemeProvider>
        </AuthProvider>
        <Toaster />
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
