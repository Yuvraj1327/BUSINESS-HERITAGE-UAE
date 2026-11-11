import { StatCard } from '@/components/common/stat-card'
import type { Totals } from '@/schemas/dashboard'
import { formatAED } from '@/utils/format'

/** Cash / POS / bank transfer / payment link split of the collections (values from the API). */
export function CollectionBreakdown({
  totals,
  isLoading,
}: {
  totals?: Totals
  isLoading?: boolean
}) {
  const c = totals?.collections
  const items: [string, string | undefined][] = [
    ['Cash', c?.cash_received],
    ['POS', c?.pos_amount],
    ['Bank Transfers', c?.bank_transfer],
    ['Payment Links', c?.link_payment],
  ]
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="collection-breakdown">
      {items.map(([label, value]) => (
        <StatCard
          key={label}
          label={label}
          isLoading={isLoading}
          value={value === undefined ? undefined : formatAED(value)}
        />
      ))}
    </div>
  )
}
