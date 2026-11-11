import { UserPlus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Can } from '@/auth/permission-guards'
import { DataTable } from '@/components/common/data-table'
import { Pagination } from '@/components/common/pagination'
import { FormInput } from '@/components/forms/form-input'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useCustomers } from '@/hooks/use-orders'
import { formatDate } from '@/utils/format'
import { aed } from './order-format'
import { CustomerDialog } from './CustomerDialog'

/** Customers of the branches the user may see. Search by name or mobile. */
export function CustomersPage() {
  const { canChoose, selectedBranchId } = useBranchContext()
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)
  const list = useCustomers({
    q: q.trim(),
    branch_id: canChoose && selectedBranchId !== 'all' ? selectedBranchId : undefined,
    page,
    page_size: 25,
  })
  return (
    <PageContainer
      title="Customers"
      description="Customers belong to one branch. Orders can only be placed for customers of that branch."
      actions={
        <Can module="customers" action="create">
          <Button onClick={() => setAdding(true)}>
            <UserPlus aria-hidden /> New customer
          </Button>
        </Can>
      }
    >
      <FormInput
        label="Search customers"
        type="search"
        placeholder="Name or mobile number"
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setPage(1)
        }}
        maxLength={100}
      />
      <DataTable
        caption="Customers"
        rows={list.data?.items}
        getRowId={(c) => c.id}
        isLoading={list.isLoading}
        error={list.error}
        onRetry={() => void list.refetch()}
        emptyTitle="No customers found"
        emptyDescription="Customers are added here or while placing an order."
        columns={[
          {
            key: 'name',
            header: 'Customer',
            cell: (c) => (
              <Link to={`/customers/${c.id}`} className="font-medium text-primary hover:underline">
                {c.name}
              </Link>
            ),
          },
          { key: 'mobile', header: 'Mobile', cell: (c) => c.mobile },
          { key: 'area', header: 'Area', cell: (c) => c.area ?? '—' },
          ...(canChoose
            ? [
                {
                  key: 'branch',
                  header: 'Branch',
                  cell: (c: { branch_name: string }) => c.branch_name,
                },
              ]
            : []),
          {
            key: 'orders',
            header: 'Orders',
            align: 'right' as const,
            cell: (c) => String(c.order_count),
          },
          {
            key: 'billed',
            header: 'Billed',
            align: 'right' as const,
            cell: (c) => aed(c.total_billed),
          },
          {
            key: 'out',
            header: 'Outstanding',
            align: 'right' as const,
            cell: (c) => aed(c.outstanding),
          },
          {
            key: 'last',
            header: 'Last order',
            cell: (c) => (c.last_order_date ? formatDate(c.last_order_date) : '—'),
          },
        ]}
      />
      {list.data ? (
        <Pagination
          page={list.data.page}
          pageSize={list.data.page_size}
          total={list.data.total}
          noun="customers"
          onPage={setPage}
        />
      ) : null}
      <CustomerDialog open={adding} onOpenChange={setAdding} />
    </PageContainer>
  )
}
