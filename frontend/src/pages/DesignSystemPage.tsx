import { zodResolver } from '@hookform/resolvers/zod'
import { Inbox, Layers } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { EmptyState } from '@/components/common/empty-state'
import { ErrorState } from '@/components/common/error-state'
import { LoadingState } from '@/components/common/loading-state'
import { PermissionDenied } from '@/components/common/permission-denied'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { StatusBadge } from '@/components/common/status-badge'
import { FormActions } from '@/components/forms/form-actions'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { FormTextarea } from '@/components/forms/form-textarea'
import { PageContainer } from '@/components/layout/page-container'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { BANKS } from '@/constants'
import { aedAmountSchema } from '@/schemas/common'
import { dubaiToday, formatAED } from '@/utils/format'

const sampleSchema = z.object({
  title: z.string().min(2, 'At least 2 characters'),
  amount: aedAmountSchema,
  bank: z.string().min(1, 'Choose a bank'),
  date: z.string().min(1, 'Choose a date'),
  note: z.string().optional(),
})
type SampleForm = z.infer<typeof sampleSchema>

interface SampleRow {
  id: string
  label: string
  amount: number
  state: 'success' | 'danger'
}
const SAMPLE_ROWS: SampleRow[] = [
  { id: 'a', label: 'Row A', amount: 1000, state: 'success' },
  { id: 'b', label: 'Row B', amount: 300, state: 'danger' },
]
const COLUMNS: DataTableColumn<SampleRow>[] = [
  { key: 'label', header: 'Label', cell: (r) => r.label },
  { key: 'amount', header: 'Amount', align: 'right', cell: (r) => formatAED(r.amount) },
  {
    key: 'state',
    header: 'Status',
    cell: (r) => (
      <StatusBadge status={r.state}>{r.state === 'success' ? 'Matches' : 'Difference'}</StatusBadge>
    ),
  },
]

const SWATCHES = [
  ['Primary navy', 'bg-primary'],
  ['Primary blue', 'bg-accent'],
  ['Accent teal', 'bg-teal'],
  ['Background', 'bg-background border'],
  ['Surface', 'bg-card border'],
  ['Border', 'bg-border'],
  ['Text primary', 'bg-foreground'],
  ['Text secondary', 'bg-muted-foreground'],
] as const

/** Development-only preview of the shared UI (route is not registered in production builds). */
export function DesignSystemPage() {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<SampleForm>({
    resolver: zodResolver(sampleSchema),
    defaultValues: { title: '', amount: '', bank: '', date: '', note: '' },
  })

  return (
    <PageContainer
      title="Design system"
      description="Shared components and tokens (development only). Sample values are illustrative, not business data."
    >
      <SectionCard title="Colour tokens">
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {SWATCHES.map(([name, cls]) => (
            <li key={name} className="flex items-center gap-2 text-sm">
              <span className={`size-8 shrink-0 rounded-md ${cls}`} aria-hidden />
              {name}
            </li>
          ))}
        </ul>
      </SectionCard>

      <SectionCard title="Buttons, badges and status">
        <div className="flex flex-wrap items-center gap-2">
          <Button>Primary</Button>
          <Button variant="accent">Accent</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Badge>Default</Badge>
          <Badge variant="secondary">Secondary</Badge>
          <StatusBadge status="success">Success</StatusBadge>
          <StatusBadge status="warning">Warning</StatusBadge>
          <StatusBadge status="danger">Danger</StatusBadge>
          <StatusBadge status="info">Info</StatusBadge>
          <StatusBadge status="neutral">Neutral</StatusBadge>
        </div>
      </SectionCard>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Stat card" value="123" description="With a value" icon={Layers} />
        <StatCard label="Placeholder" placeholder description="No data yet" />
        <StatCard label="Loading" isLoading />
        <StatCard label="Amount" value={formatAED(2500)} description="AED, tabular figures" />
      </div>

      <SectionCard
        title="Data table"
        description="Scrolls inside its own container on small screens"
      >
        <DataTable
          columns={COLUMNS}
          rows={SAMPLE_ROWS}
          getRowId={(r) => r.id}
          caption="Sample rows"
        />
      </SectionCard>

      <SectionCard title="Form components">
        <form
          className="grid max-w-xl gap-4"
          onSubmit={(e) =>
            void handleSubmit((v) => toast.success(`Valid: ${formatAED(v.amount)}`))(e)
          }
        >
          <FormInput
            label="Title"
            required
            error={errors.title}
            placeholder="Enter a title"
            {...register('title')}
          />
          <FormInput
            label="Amount (AED)"
            required
            error={errors.amount}
            description="Up to 2 decimals"
            inputMode="decimal"
            placeholder="0.00"
            {...register('amount')}
          />
          <Controller
            control={control}
            name="bank"
            render={({ field }) => (
              <FormSelect
                label="Bank"
                required
                options={BANKS.map((b) => ({ value: b, label: b }))}
                value={field.value}
                onValueChange={field.onChange}
                error={errors.bank}
              />
            )}
          />
          <FormDatePicker
            label="Date"
            required
            max={dubaiToday()}
            error={errors.date}
            {...register('date')}
          />
          <FormTextarea label="Note" description="Optional" {...register('note')} />
          <FormActions submitLabel="Validate" onCancel={() => toast.info('Cancel clicked')}>
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirmOpen(true)}
              className="h-11 sm:h-9"
            >
              Open confirm dialog
            </Button>
          </FormActions>
        </form>
        <ConfirmDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Confirm action"
          description="Confirmations are used before sensitive actions."
          confirmLabel="Confirm"
          onConfirm={() => {
            toast.success('Confirmed')
            setConfirmOpen(false)
          }}
        />
      </SectionCard>

      <div className="grid gap-4 md:grid-cols-2">
        <SectionCard title="Loading">
          <LoadingState />
        </SectionCard>
        <SectionCard title="Empty">
          <EmptyState
            icon={Inbox}
            title="No records yet"
            description="Create the first record to get started."
          />
        </SectionCard>
        <SectionCard title="Error">
          <ErrorState
            message="Example error message."
            onRetry={() => toast.info('Retry clicked')}
          />
        </SectionCard>
        <SectionCard title="Permission denied">
          <PermissionDenied />
        </SectionCard>
      </div>
    </PageContainer>
  )
}
