import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { EmptyState } from '@/components/common/empty-state'
import { ErrorState } from '@/components/common/error-state'
import { SectionCard } from '@/components/common/section-card'
import { Skeleton } from '@/components/ui/skeleton'
import { useCharts } from '@/hooks/use-analytics'
import type { Chart } from '@/schemas/analytics'
import type { ReportFilters } from '@/services/analytics.service'
import { formatAED } from '@/utils/format'

const COLORS = [
  '#0f766e',
  '#1e3a5f',
  '#d97706',
  '#7c3aed',
  '#be123c',
  '#0369a1',
  '#65a30d',
  '#64748b',
]

const fmt = (unit: Chart['unit'], v: unknown) =>
  unit === 'AED' ? formatAED(String(v)) : new Intl.NumberFormat('en-AE').format(Number(v))
const compact = (unit: Chart['unit'], v: number) =>
  unit === 'AED' ? new Intl.NumberFormat('en-AE', { notation: 'compact' }).format(v) : String(v)

function ChartBody({ chart }: { chart: Chart }) {
  const data = chart.points.map((p) => ({
    label: p.label,
    ...Object.fromEntries(chart.series.map((s) => [s, Number(p.values[s] ?? 0)])),
  }))
  const tip = (v: unknown, name: unknown) => [fmt(chart.unit, v), String(name)] as [string, string]
  return (
    <div className="h-64 w-full" role="img" aria-label={`${chart.title} chart`}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        {chart.kind === 'pie' ? (
          <PieChart>
            <Pie data={data} dataKey={chart.series[0] ?? 'value'} nameKey="label" outerRadius="75%">
              {data.map((d, i) => (
                <Cell key={d.label} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={tip} />
            <Legend />
          </PieChart>
        ) : chart.kind === 'line' ? (
          <LineChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={16} />
            <YAxis
              tick={{ fontSize: 11 }}
              width={48}
              tickFormatter={(v: number) => compact(chart.unit, v)}
            />
            <Tooltip formatter={tip} />
            {chart.series.length > 1 ? <Legend /> : null}
            {chart.series.map((s, i) => (
              <Line
                key={s}
                dataKey={s}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        ) : (
          <BarChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11 }}
              interval="preserveStartEnd"
              minTickGap={8}
            />
            <YAxis
              tick={{ fontSize: 11 }}
              width={48}
              tickFormatter={(v: number) => compact(chart.unit, v)}
            />
            <Tooltip formatter={tip} />
            {chart.series.length > 1 ? <Legend /> : null}
            {chart.series.map((s, i) => (
              <Bar key={s} dataKey={s} fill={COLORS[i % COLORS.length]} radius={[3, 3, 0, 0]} />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}

/** The eleven report charts, built by the server from the same tables as the reports. */
export function ChartsSection({ filters }: { filters: ReportFilters }) {
  const q = useCharts(filters)
  if (q.error) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />
  if (!q.data) return <Skeleton className="h-64 w-full" aria-label="Loading charts" />
  return (
    <div className="grid gap-4 lg:grid-cols-2" aria-label="Charts">
      {q.data.charts.map((c) => (
        <SectionCard
          key={c.key}
          title={c.title}
          description={c.unit === 'AED' ? 'Amounts in AED' : undefined}
        >
          {c.points.length === 0 ? (
            <EmptyState title="No data" description={c.empty_message} />
          ) : (
            <ChartBody chart={c} />
          )}
        </SectionCard>
      ))}
    </div>
  )
}
