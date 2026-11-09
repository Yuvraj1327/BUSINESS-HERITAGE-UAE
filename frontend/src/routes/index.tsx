import { createBrowserRouter, type RouteObject } from 'react-router-dom'
import { GuestRoute, ProtectedRoute } from '@/auth/guards'
import { RequirePermission } from '@/auth/permission-guards'
import { env } from '@/config/env'
import { RootLayout } from '@/layouts/RootLayout'
import { ForgotPasswordPage } from '@/pages/auth/ForgotPasswordPage'
import { LoginPage } from '@/pages/auth/LoginPage'
import { ResetPasswordPage } from '@/pages/auth/ResetPasswordPage'
import { HomePlaceholderPage } from '@/pages/HomePlaceholderPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { RouteErrorPage } from '@/pages/RouteErrorPage'
import { SetupStatusPage } from '@/pages/SetupStatusPage'

const appChildren: RouteObject[] = [
  {
    element: <RequirePermission module="dashboard" action="read" />,
    children: [{ index: true, element: <HomePlaceholderPage /> }],
  },
  {
    // Owner-only today (SETTINGS has no Branch User grant). Typing the URL as a Branch User shows Access denied.
    element: <RequirePermission module="settings" action="read" />,
    children: [
      { path: 'system-status', element: <SetupStatusPage /> },
      ...(env.isDev
        ? [
            {
              path: 'design-system',
              lazy: async () => ({
                Component: (await import('@/pages/DesignSystemPage')).DesignSystemPage,
              }),
            },
          ]
        : []),
    ],
  },
]

/**
 * Public: /login, /forgot-password, /reset-password (there is deliberately no registration page).
 * Protected: everything under the app shell, each branch of the tree behind <RequirePermission>.
 * Module pages are added in later steps; each must declare its module/action here (default deny).
 */
export const appRoutes: RouteObject[] = [
  {
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <GuestRoute />,
        children: [
          { path: '/login', element: <LoginPage /> },
          { path: '/forgot-password', element: <ForgotPasswordPage /> },
        ],
      },
      { path: '/reset-password', element: <ResetPasswordPage /> },
      {
        element: <ProtectedRoute />,
        children: [{ path: '/', element: <RootLayout />, children: appChildren }],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]

export const router = createBrowserRouter(appRoutes)
