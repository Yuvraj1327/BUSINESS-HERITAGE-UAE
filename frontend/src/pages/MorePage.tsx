import { ChevronRight, Info } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useLayoutVariant, useNavigation } from '@/auth/use-navigation'
import { PageContainer } from '@/components/layout/page-container'
import { useOwnerDashboard } from '@/hooks/use-reports'
import { cn } from '@/lib/utils'
import { dubaiToday, formatAED } from '@/utils/format'

const TONES = [
  'from-white to-sky-50 text-sky-700',
  'from-white to-violet-50 text-violet-700',
  'from-white to-emerald-50 text-emerald-700',
  'from-white to-orange-50 text-orange-700',
  'from-white to-indigo-50 text-indigo-700',
  'from-white to-teal-50 text-teal-700',
  'from-white to-pink-50 text-pink-700',
]

/** Today's real totals from the owner dashboard API (all branches). */
function TodaySummary() {
  const today = dubaiToday()
  const q = useOwnerDashboard({ mode: 'day', date: today })
  const k = q.data?.kpis
  const cells: [string, string | number | undefined, string][] = [
    ['Total Orders', k?.total_orders, 'bg-sky-50'],
    ['Total Sales', k && formatAED(k.total_sales), 'bg-emerald-50'],
    ['Total Received', k && formatAED(k.total_received), 'bg-violet-50'],
  ]
  return (
    <section className="rounded-2xl border bg-card p-4 shadow-card" aria-label="Today's summary">
      <Link to="/" className="mb-3 flex items-center justify-between font-semibold text-primary">
        Today&apos;s Summary <ChevronRight className="size-5" aria-hidden />
      </Link>
      <div className="grid grid-cols-3 gap-2">
        {cells.map(([label, value, bg]) => (
          <div key={label} className={cn('rounded-xl p-2 text-center', bg)}>
            <p className="text-[11px] text-muted-foreground">{label}</p>
            <p className="tabular text-sm font-semibold text-primary">{value ?? '—'}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

/** Full menu as a tile grid (the "More" tab on phones). Contents follow the user's permissions. */
export function MorePage() {
  const sections = useNavigation()
  const owner = useLayoutVariant() === 'owner'
  const tiles = sections.flatMap((s) =>
    s.items.flatMap((i) => (i.children ? i.children : [i])).filter((i) => i.to),
  )
  return (
    <PageContainer title="More" description="All pages you can open.">
      {tiles.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Info className="size-4" aria-hidden /> No pages available.
        </p>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {tiles.map((item, i) => (
            <li key={item.key}>
              <Link
                to={item.to!}
                className={cn(
                  'flex min-h-28 flex-col items-center justify-center gap-2 rounded-2xl border bg-gradient-to-br p-3 text-center text-sm font-medium text-primary shadow-card transition hover:shadow-md',
                  TONES[i % TONES.length],
                )}
              >
                <item.icon className="size-7" aria-hidden />
                <span className="text-primary">{item.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {owner ? <TodaySummary /> : null}
    </PageContainer>
  )
}
