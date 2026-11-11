import type { Control, FieldErrors, UseFormRegister, UseFormWatch } from 'react-hook-form'
import { Controller } from 'react-hook-form'
import { SectionCard } from '@/components/common/section-card'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { FormTextarea } from '@/components/forms/form-textarea'
import { useCategories } from '@/hooks/use-orders'
import { previewFinalPayable, SERVICE_TYPES, type OrderFormInput } from '@/schemas/orders'
import { aed } from './order-format'

interface Props {
  control: Control<OrderFormInput>
  register: UseFormRegister<OrderFormInput>
  errors: FieldErrors<OrderFormInput>
  watch: UseFormWatch<OrderFormInput>
}

/** The order part of the form, shared by "New order" and "Edit order" so the rules are identical. */
export function OrderFormParts({ control, register, errors, watch }: Props) {
  const cats = useCategories()
  const [total, discount, fee] = watch(['order_total', 'discount', 'service_fee'])
  const final = previewFinalPayable(total ?? '', discount ?? '', fee ?? '')
  return (
    <>
      <SectionCard title="Service">
        <div className="grid gap-4 sm:grid-cols-2">
          <Controller
            control={control}
            name="category_id"
            render={({ field }) => (
              <FormSelect
                label="Service category"
                required
                value={field.value}
                onValueChange={field.onChange}
                error={errors.category_id}
                options={(cats.data ?? [])
                  .filter((c) => c.is_active || c.id === field.value)
                  .map((c) => ({ value: c.id, label: c.name }))}
              />
            )}
          />
          <Controller
            control={control}
            name="service_type"
            render={({ field }) => (
              <FormSelect
                label="Service type"
                required
                value={field.value}
                onValueChange={field.onChange}
                error={errors.service_type}
                options={SERVICE_TYPES.map((s) => ({ value: s, label: s }))}
              />
            )}
          />
          <FormTextarea
            className="sm:col-span-2"
            label="Order notes"
            maxLength={2000}
            error={errors.notes}
            {...register('notes')}
          />
        </div>
      </SectionCard>

      <SectionCard
        title="Pickup"
        description="Optional. Leave empty when the customer brings the items in. Dubai time."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <FormDatePicker
            label="Pickup date"
            error={errors.pickup_date}
            {...register('pickup_date')}
          />
          <FormInput
            label="Pickup time"
            type="time"
            error={errors.pickup_time}
            {...register('pickup_time')}
          />
          <FormTextarea
            className="sm:col-span-2"
            label="Pickup address"
            maxLength={500}
            error={errors.pickup_address}
            {...register('pickup_address')}
          />
        </div>
      </SectionCard>

      <SectionCard
        title="Expected delivery"
        description="Dubai time. Cannot be earlier than the pickup."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <FormDatePicker
            label="Delivery date"
            required
            error={errors.delivery_date}
            {...register('delivery_date')}
          />
          <FormInput
            label="Delivery time"
            type="time"
            required
            error={errors.delivery_time}
            {...register('delivery_time')}
          />
          <FormTextarea
            className="sm:col-span-2"
            label="Delivery address"
            maxLength={500}
            error={errors.delivery_address}
            {...register('delivery_address')}
          />
        </div>
      </SectionCard>

      <SectionCard
        title="Amounts (AED)"
        description="Final payable = order total − discount + service fee."
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <FormInput
            label="Order total"
            required
            inputMode="decimal"
            error={errors.order_total}
            {...register('order_total')}
          />
          <FormInput
            label="Discount"
            inputMode="decimal"
            error={errors.discount}
            {...register('discount')}
          />
          <FormInput
            label="Service fee"
            inputMode="decimal"
            error={errors.service_fee}
            {...register('service_fee')}
          />
        </div>
        <p className="mt-3 text-sm" aria-live="polite">
          Final payable: <strong className="tabular">{final === null ? '—' : aed(final)}</strong>
          {final !== null && final <= 0 ? (
            <span className="ml-2 text-destructive">Must be more than zero</span>
          ) : null}
        </p>
      </SectionCard>
    </>
  )
}
