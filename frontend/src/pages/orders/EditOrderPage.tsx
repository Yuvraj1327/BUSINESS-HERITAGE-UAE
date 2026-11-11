import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ErrorState } from '@/components/common/error-state'
import { LoadingState } from '@/components/common/loading-state'
import { FormActions } from '@/components/forms/form-actions'
import { FormInput } from '@/components/forms/form-input'
import { PageContainer } from '@/components/layout/page-container'
import { useOrder, useUpdateOrder } from '@/hooks/use-orders'
import { getErrorMessage } from '@/lib/errors'
import { orderFormSchema, type OrderFormInput } from '@/schemas/orders'
import { dubaiParts } from '@/utils/format'
import { OrderFormParts } from './OrderFormParts'
import { EMPTY_ORDER_FORM, orderBody } from './order-form'

/** Edit an open order. The server decides what is still editable and refuses edits that would break payments. */
export function EditOrderPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const q = useOrder(id)
  const update = useUpdateOrder(id)
  const [reason, setReason] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    control,
    watch,
    reset,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<OrderFormInput>({
    resolver: zodResolver(orderFormSchema) as never,
    defaultValues: EMPTY_ORDER_FORM,
  })
  const d = q.data
  useEffect(() => {
    if (!d) return
    const pu = dubaiParts(d.order.pickup_at)
    const de = dubaiParts(d.order.delivery_at)
    reset({
      category_id: d.category_id,
      service_type: d.order.service_type as 'Standard' | 'Express',
      notes: d.notes ?? '',
      pickup_date: pu.date,
      pickup_time: pu.time,
      pickup_address: d.order.pickup_address ?? '',
      delivery_date: de.date,
      delivery_time: de.time,
      delivery_address: d.order.delivery_address ?? '',
      order_total: String(d.order_total),
      discount: String(d.discount),
      service_fee: String(d.service_fee),
    })
  }, [d, reset])

  if (q.isLoading)
    return (
      <PageContainer title="Edit Order">
        <LoadingState rows={6} />
      </PageContainer>
    )
  if (q.isError || !d)
    return (
      <PageContainer title="Edit Order">
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </PageContainer>
    )
  if (!d.can_edit)
    return (
      <PageContainer title={`Order ${d.order.order_no}`}>
        <ErrorState
          title="This order can no longer be edited"
          message="Completed and cancelled orders are kept as they are. Use the order page to see its history."
        />
      </PageContainer>
    )

  async function submit(raw: OrderFormInput) {
    setFormError(null)
    const v = orderFormSchema.parse(raw)
    try {
      await update.mutateAsync({ ...orderBody(v), reason: reason.trim() || null })
      toast.success('Order updated')
      navigate(`/orders/${id}`)
    } catch (e) {
      setFormError(getErrorMessage(e))
    }
  }

  return (
    <PageContainer
      title={`Edit ${d.order.order_no}`}
      description={`${d.order.customer_name} · ${d.order.branch_name}. The customer and branch cannot be changed.`}
    >
      <form onSubmit={(e) => void handleSubmit(submit)(e)} noValidate className="space-y-6">
        <OrderFormParts control={control} register={register} errors={errors} watch={watch} />
        <FormInput
          label="Reason for the change (kept in the history)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={500}
        />
        {formError ? (
          <p role="alert" className="flex items-start gap-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden /> {formError}
          </p>
        ) : null}
        <FormActions
          submitLabel="Save changes"
          isSubmitting={isSubmitting || update.isPending}
          onCancel={() => navigate(`/orders/${id}`)}
        />
      </form>
    </PageContainer>
  )
}
