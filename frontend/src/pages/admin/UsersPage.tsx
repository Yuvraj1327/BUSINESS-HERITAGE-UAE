import { Plus, Users } from 'lucide-react'
import { useState } from 'react'
import { Can } from '@/auth/permission-guards'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { StatusBadge } from '@/components/common/status-badge'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useBranches } from '@/hooks/use-branches'
import { useUsers } from '@/hooks/use-users'
import type { UserProfile } from '@/schemas/users'
import { formatDateTime } from '@/utils/format'
import { roleLabel } from '@/utils/user'
import { UserDialog } from './UserDialog'

/** Owner-only user list; Owners can add Branch Users (POST /users). Editing/deactivating is an operator task. */
export function UsersPage() {
  const users = useUsers()
  const [adding, setAdding] = useState(false)
  const branches = useBranches()
  const branchName = (id: string | null) =>
    id ? (branches.data?.find((b) => b.id === id)?.name ?? '—') : 'All branches'
  const columns: DataTableColumn<UserProfile>[] = [
    {
      key: 'name',
      header: 'Name',
      cell: (u) => <span className="font-medium">{u.full_name}</span>,
    },
    { key: 'role', header: 'Role', cell: (u) => roleLabel(u.role) },
    { key: 'branch', header: 'Branch', cell: (u) => branchName(u.branch_id) },
    {
      key: 'status',
      header: 'Status',
      cell: (u) => (
        <StatusBadge status={u.is_active ? 'success' : 'neutral'}>
          {u.is_active ? 'Active' : 'Inactive'}
        </StatusBadge>
      ),
    },
    { key: 'created', header: 'Created', cell: (u) => formatDateTime(u.created_at) },
  ]
  return (
    <PageContainer
      title="User Management"
      description="Accounts and the branch each one belongs to."
      actions={
        <Can module="user_management" action="create">
          <Button onClick={() => setAdding(true)}>
            <Plus aria-hidden /> New Branch User
          </Button>
        </Can>
      }
    >
      <DataTable
        caption="Users"
        rows={users.data}
        isLoading={users.isLoading}
        error={users.error}
        onRetry={() => void users.refetch()}
        getRowId={(u) => u.user_id}
        columns={columns}
        emptyIcon={Users}
        emptyTitle="No users found"
      />
      <UserDialog open={adding} onOpenChange={setAdding} />
    </PageContainer>
  )
}
