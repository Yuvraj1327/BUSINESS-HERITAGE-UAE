import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  noun: string
  onPage: (page: number) => void
}

/** Previous / Next with a polite live status. Renders nothing for an empty result. */
export function Pagination({ page, pageSize, total, noun, onPage }: PaginationProps) {
  if (total <= 0) return null
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <nav
      aria-label="Pagination"
      className="flex flex-wrap items-center justify-between gap-2 text-sm"
    >
      <p className="text-muted-foreground" aria-live="polite">
        Page {page} of {pages} · {total} {noun}
      </p>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          <ChevronLeft aria-hidden /> Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
        >
          Next <ChevronRight aria-hidden />
        </Button>
      </div>
    </nav>
  )
}
