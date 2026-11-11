import { useState, type ReactNode } from 'react'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { Textarea } from '@/components/ui/textarea'
import { toApiError } from '@/lib/errors'
import { voidReasonSchema } from '@/schemas/finance'

interface ReasonDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: ReactNode
  confirmLabel: string
  destructive?: boolean
  isLoading?: boolean
  /** Runs with the trimmed reason. Throw to keep the dialog open and show the server message. */
  onSubmit: (reason: string) => Promise<void>
}

/**
 * Corrections are never silent: every void / edit / un-save asks for a reason (3+ characters) that is stored in the
 * audit log. Server errors (e.g. "would make a balance negative") are shown inside the dialog.
 */
export function ReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive = true,
  isLoading,
  onSubmit,
}: ReasonDialogProps) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const close = (next: boolean) => {
    if (!next) {
      setReason('')
      setError(null)
    }
    onOpenChange(next)
  }

  async function confirm() {
    const parsed = voidReasonSchema.safeParse(reason)
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? 'Enter a reason')
      return
    }
    try {
      await onSubmit(parsed.data)
      close(false)
    } catch (e) {
      setError(toApiError(e).message)
    }
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={close}
      title={title}
      destructive={destructive}
      confirmLabel={confirmLabel}
      isLoading={isLoading}
      onConfirm={confirm}
      description={
        <div className="space-y-3 text-left text-sm">
          <div>{description}</div>
          <label className="grid gap-1.5">
            <span className="font-medium">Reason (required, kept in the audit log)</span>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
              aria-invalid={error ? true : undefined}
            />
          </label>
          {error ? (
            <p role="alert" className="text-destructive">
              {error}
            </p>
          ) : null}
        </div>
      }
    />
  )
}
