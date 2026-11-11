import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { EmptyState } from '@/components/common/empty-state'
import { ErrorState } from '@/components/common/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

export interface DataTableColumn<T> {
  key: string
  header: string
  cell: (row: T) => ReactNode
  /** Right-align numbers (AED amounts) so digits line up. */
  align?: 'left' | 'right'
  className?: string
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[]
  rows: T[] | undefined
  getRowId: (row: T) => string
  /** Accessible table name (screen readers announce it). */
  caption: string
  isLoading?: boolean
  error?: unknown
  onRetry?: () => void
  emptyTitle?: string
  emptyDescription?: string
  emptyIcon?: LucideIcon
  skeletonRows?: number
  className?: string
}

/**
 * Presentational table with loading, error and empty states. Wide tables scroll inside their own container, never
 * the page. Sorting, paging and filtering are added by the modules that need them.
 */
export function DataTable<T>({
  columns,
  rows,
  getRowId,
  caption,
  isLoading = false,
  error,
  onRetry,
  emptyTitle = 'Nothing to show',
  emptyDescription,
  emptyIcon,
  skeletonRows = 4,
  className,
}: DataTableProps<T>) {
  if (error) return <ErrorState error={error} onRetry={onRetry} />
  if (!isLoading && (!rows || rows.length === 0)) {
    return <EmptyState title={emptyTitle} description={emptyDescription} icon={emptyIcon} />
  }
  return (
    <div className={cn('overflow-hidden rounded-xl border border-sky-100 bg-card', className)}>
      <Table aria-busy={isLoading || undefined}>
        <caption className="sr-only">{caption}</caption>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((c) => (
              <TableHead
                key={c.key}
                scope="col"
                className={cn(c.align === 'right' && 'text-right', c.className)}
              >
                {c.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading
            ? Array.from({ length: skeletonRows }, (_, i) => (
                <TableRow key={i} className="hover:bg-transparent">
                  {columns.map((c) => (
                    <TableCell key={c.key}>
                      <Skeleton className="h-4 w-full max-w-32" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            : (rows ?? []).map((row) => (
                <TableRow key={getRowId(row)}>
                  {columns.map((c) => (
                    <TableCell
                      key={c.key}
                      className={cn(c.align === 'right' && 'tabular text-right', c.className)}
                    >
                      {c.cell(row)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
        </TableBody>
      </Table>
    </div>
  )
}
