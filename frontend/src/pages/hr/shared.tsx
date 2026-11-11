import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { StatusBadge, type Status } from '@/components/common/status-badge'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormTextarea } from '@/components/forms/form-textarea'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { toApiError } from '@/lib/errors'
import type { AuditEntry } from '@/schemas/finance'
import { daysText, describeChange } from './helpers'
import type { EmploymentStatus, ExpiryStatus, Leave } from '@/schemas/hr'

/* ---------- indicators: always colour + word (never colour alone) ---------- */
const EXPIRY: Record<ExpiryStatus, { tone: Status; label: string }> = {
  expired: { tone: 'danger', label: 'Expired' },
  urgent: { tone: 'danger', label: 'Expiring soon' },
  upcoming: { tone: 'warning', label: 'Upcoming' },
  normal: { tone: 'success', label: 'Valid' },
  not_recorded: { tone: 'neutral', label: 'Not recorded' },
  cancelled: { tone: 'danger', label: 'Visa cancelled' },
}
export function ExpiryBadge({
  status,
  days,
}: {
  status: ExpiryStatus
  days?: number | null | undefined
}) {
  const { tone, label } = EXPIRY[status]
  const d = status === 'cancelled' || status === 'not_recorded' ? '' : daysText(days)
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <StatusBadge status={tone}>{label}</StatusBadge>
      {d ? <span className="text-xs text-muted-foreground">{d}</span> : null}
    </span>
  )
}

const EMPLOYMENT: Record<EmploymentStatus, Status> = {
  Active: 'success',
  'On Leave': 'info',
  'Visa Cancelled': 'danger',
}
export const EmploymentBadge = ({ status }: { status: EmploymentStatus }) => (
  <StatusBadge status={EMPLOYMENT[status]}>{status}</StatusBadge>
)

const LEAVE: Record<Leave['state'], { tone: Status; label: string }> = {
  not_on_leave: { tone: 'neutral', label: 'Not on leave' },
  on_leave: { tone: 'info', label: 'On Leave' },
  approaching_limit: { tone: 'warning', label: 'Approaching Six-Month Limit' },
  limit_reached: { tone: 'danger', label: 'Six-Month Limit Reached' },
  visa_cancelled: { tone: 'danger', label: 'Visa Cancelled' },
}
export const LeaveBadge = ({ state }: { state: Leave['state'] }) => (
  <StatusBadge status={LEAVE[state].tone}>{LEAVE[state].label}</StatusBadge>
)

/* ---------- history ---------- */
/* ---------- one dialog for every sensitive action: shows the consequence, asks for a date and/or reason ---------- */
interface ActionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: ReactNode
  confirmLabel: string
  destructive?: boolean
  dateLabel?: string
  dateRequired?: boolean
  dateDefault?: string
  dateMin?: string
  dateMax?: string
  dateHint?: string
  reasonLabel?: string
  reasonRequired?: boolean
  onSubmit: (v: { date: string; reason: string }) => Promise<void>
}

function ActionForm({
  dateLabel,
  dateRequired = true,
  dateDefault = '',
  dateMin,
  dateMax,
  dateHint,
  reasonLabel = 'Reason (kept in the audit history)',
  reasonRequired = true,
  confirmLabel,
  destructive,
  onSubmit,
  onDone,
}: Omit<ActionDialogProps, 'open' | 'onOpenChange' | 'title' | 'description'> & {
  onDone: () => void
}) {
  const schema = z.object({
    date: z.string().refine((v) => !dateLabel || !dateRequired || v !== '', 'Choose a date'),
    reason: reasonRequired
      ? z.string().trim().min(3, 'Enter a reason (at least 3 characters)').max(500)
      : z.string().trim().max(500),
  })
  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: { date: dateDefault, reason: '' },
  })
  const [error, setError] = useState<string | null>(null)
  const { errors, isSubmitting } = form.formState
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={form.handleSubmit(async (v) => {
        setError(null)
        try {
          await onSubmit(v)
          onDone()
        } catch (e) {
          setError(toApiError(e).message)
        }
      })}
    >
      {dateLabel ? (
        <FormDatePicker
          label={dateLabel}
          required={dateRequired}
          {...(dateMin ? { min: dateMin } : {})}
          {...(dateMax ? { max: dateMax } : {})}
          {...(dateHint ? { description: dateHint } : {})}
          error={errors.date}
          {...form.register('date')}
        />
      ) : null}
      <FormTextarea
        label={reasonLabel}
        required={reasonRequired}
        maxLength={500}
        error={errors.reason}
        {...form.register('reason')}
      />
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button
          type="submit"
          variant={destructive ? 'destructive' : 'default'}
          disabled={isSubmitting}
        >
          {isSubmitting ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {confirmLabel}
        </Button>
      </DialogFooter>
    </form>
  )
}

export function ActionDialog({
  open,
  onOpenChange,
  title,
  description,
  ...rest
}: ActionDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription asChild>
            <div>{description}</div>
          </DialogDescription>
        </DialogHeader>
        {/* Mounted only while open, so every opening starts clean. */}
        <ActionForm {...rest} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  )
}

export function ChangeHistory({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) return <p className="text-sm text-muted-foreground">No history yet.</p>
  return (
    <ol className="space-y-3" aria-label="Change history">
      {entries.map((e) => (
        <li key={e.id} className="rounded-md border p-3 text-sm">
          <p className="font-medium">{describeChange(e)}</p>
          <p className="text-xs text-muted-foreground">
            {new Intl.DateTimeFormat('en-GB', {
              dateStyle: 'medium',
              timeStyle: 'short',
              timeZone: 'Asia/Dubai',
            }).format(new Date(e.occurred_at))}{' '}
            · {e.actor_name ?? 'System'}
            {e.reason ? ` · Reason: ${e.reason}` : ''}
          </p>
        </li>
      ))}
    </ol>
  )
}
