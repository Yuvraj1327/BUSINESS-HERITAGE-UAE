import { createBrowserRouter, type RouteObject } from 'react-router-dom'
import { GuestRoute, ProtectedRoute } from '@/auth/guards'
import { RequirePermission } from '@/auth/permission-guards'
import { LoadingIndicator } from '@/components/common/loading-indicator'
import { env } from '@/config/env'
import { navLeaves } from '@/config/navigation'
import { RootLayout } from '@/layouts/RootLayout'
import { ForgotPasswordPage } from '@/pages/auth/ForgotPasswordPage'
import { LoginPage } from '@/pages/auth/LoginPage'
import { ResetPasswordPage } from '@/pages/auth/ResetPasswordPage'
import { BranchDateViewPage } from '@/pages/branch-date/BranchDateViewPage'
import { DashboardPage } from '@/pages/dashboard/DashboardPage'
import { ModulePlaceholderPage } from '@/pages/ModulePlaceholderPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { CashBanksPage } from '@/pages/finance/CashBanksPage'
import { ExpensesPage } from '@/pages/finance/ExpensesPage'
import { OpeningBalancesPage } from '@/pages/finance/OpeningBalancesPage'
import { SupplierDetailPage } from '@/pages/finance/SupplierDetailPage'
import { SuppliersPage } from '@/pages/finance/SuppliersPage'
import { NotificationsPage } from '@/pages/alerts/NotificationsPage'
import { TaskDetailPage } from '@/pages/tasks/TaskDetailPage'
import { TasksPage } from '@/pages/tasks/TasksPage'
import { AgreementDetailPage } from '@/pages/rentals/AgreementDetailPage'
import { ChequeDetailPage } from '@/pages/rentals/ChequeDetailPage'
import { PdcChequesPage } from '@/pages/rentals/PdcChequesPage'
import { RentalsPage } from '@/pages/rentals/RentalsPage'
import { EmployeeDetailPage } from '@/pages/hr/EmployeeDetailPage'
import { EmployeesPage } from '@/pages/hr/EmployeesPage'
import { LicenseDetailPage } from '@/pages/hr/LicenseDetailPage'
import { TradeLicensesPage } from '@/pages/hr/TradeLicensesPage'
import { VisasPassportsPage } from '@/pages/hr/VisasPassportsPage'
import { DailyReportsPage } from '@/pages/reports/DailyReportsPage'
import { RouteErrorPage } from '@/pages/RouteErrorPage'
import { SetupStatusPage } from '@/pages/SetupStatusPage'

const appChildren: RouteObject[] = [
  {
    element: <RequirePermission module="dashboard" action="read" />,
    children: [{ index: true, element: <DashboardPage /> }],
  },
  {
    element: <RequirePermission module="daily_reports" action="read" />,
    children: [
      { path: 'daily-reports', element: <DailyReportsPage /> },
      { path: 'branch-date-view', element: <BranchDateViewPage /> },
    ],
  },
  // Finance (Owner only: the server grants these modules to no other role, and the guards use the same pairs).
  {
    element: <RequirePermission module="cash_banks" action="read" />,
    children: [{ path: 'cash-banks', element: <CashBanksPage /> }],
  },
  {
    element: <RequirePermission module="opening_balances" action="read" />,
    children: [{ path: 'opening-balances', element: <OpeningBalancesPage /> }],
  },
  {
    element: <RequirePermission module="expenses" action="read" />,
    children: [{ path: 'expenses', element: <ExpensesPage /> }],
  },
  {
    element: <RequirePermission module="suppliers" action="read" />,
    children: [
      { path: 'suppliers', element: <SuppliersPage /> },
      { path: 'suppliers/:id', element: <SupplierDetailPage /> },
    ],
  },
  // Employees, visas & passports and trade licences (Owner only: no grant for any other role).
  {
    element: <RequirePermission module="employees" action="read" />,
    children: [
      { path: 'employees', element: <EmployeesPage /> },
      { path: 'employees/:id', element: <EmployeeDetailPage /> },
    ],
  },
  {
    element: <RequirePermission module="visas_passports" action="read" />,
    children: [{ path: 'visas-passports', element: <VisasPassportsPage /> }],
  },
  {
    element: <RequirePermission module="trade_licenses" action="read" />,
    children: [
      { path: 'trade-licenses', element: <TradeLicensesPage /> },
      { path: 'trade-licenses/:id', element: <LicenseDetailPage /> },
    ],
  },
  // Rental agreements and PDC cheques (Owner only: one module, no grant for any other role).
  {
    element: <RequirePermission module="rentals_cheques" action="read" />,
    children: [
      { path: 'rentals', element: <RentalsPage /> },
      { path: 'rentals/:id', element: <AgreementDetailPage /> },
      { path: 'pdc-cheques', element: <PdcChequesPage /> },
      { path: 'pdc-cheques/:id', element: <ChequeDetailPage /> },
    ],
  },
  // Tasks and the centralized Notifications (Owner only: no grant for any other role).
  {
    element: <RequirePermission module="tasks" action="read" />,
    children: [
      { path: 'tasks', element: <TasksPage /> },
      { path: 'tasks/:id', element: <TaskDetailPage /> },
    ],
  },
  {
    element: <RequirePermission module="alerts" action="read" />,
    children: [{ path: 'notifications', element: <NotificationsPage /> }],
  },
  // Step 13: customer orders, pickup / delivery and order reports (Owner: all branches; Branch User: own branch).
  {
    element: <RequirePermission module="orders" action="read" />,
    children: [
      {
        path: 'order-management',
        lazy: async () => ({
          Component: (await import('@/pages/orders/OrderManagementPage')).OrderManagementPage,
        }),
      },
      {
        path: 'orders',
        lazy: async () => ({
          Component: (await import('@/pages/orders/OrdersListPage')).OrdersListPage,
        }),
      },
      {
        path: 'orders/:id',
        lazy: async () => ({
          Component: (await import('@/pages/orders/OrderDetailPage')).OrderDetailPage,
        }),
      },
      {
        path: 'order-operations',
        lazy: async () => ({
          Component: (await import('@/pages/orders/OperationsPage')).OperationsPage,
        }),
      },
      {
        path: 'order-reports',
        lazy: async () => ({
          Component: (await import('@/pages/orders/OrderReportsPage')).OrderReportsPage,
        }),
      },
    ],
  },
  {
    element: <RequirePermission module="orders" action="create" />,
    children: [
      {
        path: 'orders/new',
        lazy: async () => ({
          Component: (await import('@/pages/orders/NewOrderPage')).NewOrderPage,
        }),
      },
    ],
  },
  {
    element: <RequirePermission module="orders" action="update" />,
    children: [
      {
        path: 'orders/:id/edit',
        lazy: async () => ({
          Component: (await import('@/pages/orders/EditOrderPage')).EditOrderPage,
        }),
      },
    ],
  },
  {
    element: <RequirePermission module="customers" action="read" />,
    children: [
      {
        path: 'customers',
        lazy: async () => ({
          Component: (await import('@/pages/orders/CustomersPage')).CustomersPage,
        }),
      },
      {
        path: 'customers/:id',
        lazy: async () => ({
          Component: (await import('@/pages/orders/CustomerDetailPage')).CustomerDetailPage,
        }),
      },
    ],
  },
  // Step 12: Reports & Analytics and the audit-based Activity History (Owner only: no grant for any other role).
  {
    element: <RequirePermission module="reports" action="read" />,
    children: [
      {
        path: 'reports',
        lazy: async () => ({
          Component: (await import('@/pages/analytics/ReportsPage')).ReportsPage,
        }),
      },
    ],
  },
  {
    element: <RequirePermission module="audit_log" action="read" />,
    children: [
      {
        path: 'activity-history',
        lazy: async () => ({
          Component: (await import('@/pages/analytics/ActivityHistoryPage')).ActivityHistoryPage,
        }),
      },
    ],
  },
  // One protected route per module placeholder, generated from the navigation so menu and routes cannot drift.
  // Each declares the same module/action as its menu entry; the real pages replace these in later steps.
  ...navLeaves()
    .filter((item) => item.status === 'placeholder' && item.to)
    .map((item) => ({
      element: (
        <RequirePermission module={item.module} action={item.action} scope={item.requireScope} />
      ),
      children: [{ path: item.to, element: <ModulePlaceholderPage item={item} /> }],
    })),
  {
    // System status and the dev-only design system page belong to Settings.
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
    // Shown while a lazily loaded route (the dev-only design system page) finishes loading on first visit.
    hydrateFallbackElement: <LoadingIndicator fill label="Loading…" />,
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
