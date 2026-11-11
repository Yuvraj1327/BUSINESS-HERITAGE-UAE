import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useCreateCustomer, useUpdateCustomer } from '@/hooks/use-orders'
import { getErrorMessage } from '@/lib/errors'
import { customerFormSchema, type Customer, type CustomerFormInput } from '@/schemas/orders'

const EMPTY: CustomerFormInput = {
  name: '',
  mobile: '',
  whatsapp: '',
  address: '',
  area: '',
  notes: '',
}

/** Create (no `customer`) or edit a customer. A duplicate mobile in the branch is refused with a clear message. */
export function CustomerDialog({
  open,
  onOpenChange,
  customer,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  customer?: Customer
}) {
  const { canChoose, branches, selectedBranchId } = useBranchContext()
  const create = useCreateCustomer()
  const update = useUpdateCustomer(customer?.id ?? '')
  const [branchId, setBranchId] = useState(
    canChoose && selectedBranchId !== 'all' ? selectedBranchId : '',
  )
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CustomerFormInput>({
    resolver: zodResolver(customerFormSchema) as never,
    defaultValues: EMPTY,
  })
  useEffect(() => {
    if (open)
      reset(
        customer
          ? {
              name: customer.name,
              mobile: customer.mobile,
              whatsapp: customer.whatsapp ?? '',
              address: customer.address ?? '',
              area: customer.area ?? '',
              notes: customer.notes ?? '',
            }
          : EMPTY,
      )
  }, [open, customer, reset])

  async function submit(raw: CustomerFormInput) {
    setError(null)
    const v = customerFormSchema.parse(raw)
    const body = {
      name: v.name,
      mobile: v.mobile,
      whatsapp: v.whatsapp || null,
      address: v.address || null,
      area: v.area || null,
      notes: v.notes || null,
    }
    try {
      if (customer) await update.mutateAsync(body)
      else {
        if (canChoose && !branchId) return setError('Choose the branch for this customer.')
        await create.mutateAsync({ ...body, ...(canChoose ? { branch_id: branchId } : {}) })
      }
      toast.success(customer ? 'Customer updated' : 'Customer added')
      onOpenChange(false)
    } catch (e) {
      setError(getErrorMessage(e))
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setError(null)
        onOpenChange(o)
      }}
    >
      <DialogContent>
        <form onSubmit={(e) => void handleSubmit(submit)(e)} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>{customer ? 'Edit customer' : 'New customer'}</DialogTitle>
            <DialogDescription>
              The mobile number must be unique within the branch.
            </DialogDescription>
          </DialogHeader>
          {!customer && canChoose ? (
            <FormSelect
              label="Branch"
              required
              value={branchId}
              onValueChange={setBranchId}
              options={branches.map((b) => ({ value: b.id, label: b.name }))}
            />
          ) : null}
          <FormInput
            label="Customer name"
            required
            maxLength={150}
            error={errors.name}
            {...register('name')}
          />
          <FormInput
            label="Mobile number"
            required
            inputMode="tel"
            maxLength={30}
            error={errors.mobile}
            {...register('mobile')}
          />
          <FormInput
            label="WhatsApp number (if different)"
            inputMode="tel"
            maxLength={30}
            error={errors.whatsapp}
            {...register('whatsapp')}
          />
          <FormInput label="Area" maxLength={100} error={errors.area} {...register('area')} />
          <FormInput
            label="Address"
            maxLength={500}
            error={errors.address}
            {...register('address')}
          />
          <FormInput label="Notes" maxLength={2000} error={errors.notes} {...register('notes')} />
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending || update.isPending}>
              {customer ? 'Save changes' : 'Add customer'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
