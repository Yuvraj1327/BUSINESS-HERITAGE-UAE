import { Building2 } from 'lucide-react'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { StatusBadge } from '@/components/common/status-badge'
import { PageContainer } from '@/components/layout/page-container'
import { useBranches } from '@/hooks/use-branches'
import type { Branch } from '@/schemas/branch'

const columns: DataTableColumn<Branch>[] = [
  { key: 'order', header: '#', cell: (b) => b.sort_order },
  { key: 'name', header: 'Branch', cell: (b) => <span className="font-medium">{b.name}</span> },
  {
    key: 'status',
    header: 'Status',
    cell: (b) => (
      <StatusBadge status={b.is_active ? 'success' : 'neutral'}>
        {b.is_active ? 'Active' : 'Inactive'}
      </StatusBadge>
    ),
  },
]

/** Read-only branch list from GET /branches (Owner: all branches; Branch User: their own). */
export function BranchesPage() {
  const branches = useBranches()
  return (
    <PageContainer title="Branch Management" description="Branches you have access to.">
      <DataTable
        caption="Branches"
        rows={branches.data}
        isLoading={branches.isLoading}
        error={branches.error}
        onRetry={() => void branches.refetch()}
        getRowId={(b) => b.id}
        columns={columns}
        emptyIcon={Building2}
        emptyTitle="No branches found"
      />
    </PageContainer>
  )
}
