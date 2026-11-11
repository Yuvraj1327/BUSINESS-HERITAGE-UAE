import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { SectionCard } from '@/components/common/section-card'
import { FormActions } from '@/components/forms/form-actions'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useCreateOrder, useCustomers } from '@/hooks/use-orders'
import { getErrorMessage } from '@/lib/errors'
import {
  amountText,
  customerFormSchema,
  orderFormSchema,
  PAYMENT_METHODS,
  type Customer,
  type CustomerFormInput,
  type OrderFormInput,
} from '@/schemas/orders'
import { OrderFormParts } from './OrderFormParts'
import { EMPTY_ORDER_FORM, orderBody } from './order-form'

type Mode = 'existing' | 'new'

/** Create an order: pick or add the customer, then service, schedule, amounts and an optional first payment. */
export function NewOrderPage() {
  const navigate = useNavigate()
  const { canChoose, branches, selectedBranchId } = useBranchContext()
  const create = useCreateOrder()
  const [clientKey] = useState(() => crypto.randomUUID()) // a double-click or retry can never create two orders
  const [mode, setMode] = useState<Mode>('existing')
  const [branchId, setBranchId] = useState(
    canChoose && selectedBranchId !== 'all' ? selectedBranchId : '',
  )
  const [search, setSearch] = useState('')
  const [picked, setPicked] = useState<Customer | null>(null)
  const [cust, setCust] = useState<CustomerFormInput>({
    name: '',
    mobile: '',
    whatsapp: '',
    address: '',
    area: '',
    notes: '',
  })
  const [custErrors, setCustErrors] = useState<Record<string, string>>({})
  const [pay, setPay] = useState(false)
  const [payment, setPayment] = useState({ amount: '', method: 'Cash', reference: '' })
  const [payError, setPayError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const term = search.trim()
  const found = useCustomers({
    q: term,
    branch_id: canChoose ? branchId || undefined : undefined,
    page: 1,
    page_size: 8,
  })

  const {
    register,
    control,
    watch,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<OrderFormInput>({
    resolver: zodResolver(orderFormSchema) as never,
    defaultValues: EMPTY_ORDER_FORM,
  })

  async function submit(raw: OrderFormInput) {
    setFormError(null)
    const v = orderFormSchema.parse(raw)
    if (canChoose && !branchId) return setFormError('Choose the branch for this order.')
    const body: Record<string, unknown> = {
      ...orderBody(v),
      client_key: clientKey,
      ...(canChoose ? { branch_id: branchId } : {}),
    }
    if (mode === 'existing') {
      if (!picked) return setFormError('Select an existing customer, or switch to "New customer".')
      body.customer_id = picked.id
    } else {
      const parsed = customerFormSchema.safeParse(cust)
      if (!parsed.success) {
        setCustErrors(
          Object.fromEntries(parsed.error.issues.map((i) => [String(i.path[0]), i.message])),
        )
        return setFormError('Check the customer details.')
      }
      setCustErrors({})
      const c = parsed.data
      body.new_customer = {
        name: c.name,
        mobile: c.mobile,
        whatsapp: c.whatsapp || null,
        address: c.address || null,
        area: c.area || null,
        notes: c.notes || null,
      }
    }
    if (pay) {
      const a = amountText.safeParse(payment.amount)
      if (!a.success || Number(payment.amount) <= 0) {
        setPayError('Enter the amount collected, such as 50 or 50.50')
        return setFormError('Check the payment.')
      }
      setPayError(null)
      body.initial_payment = {
        amount: payment.amount.trim(),
        method: payment.method,
        reference: payment.reference.trim() || null,
      }
    }
    try {
      const d = await create.mutateAsync(body)
      toast.success(`Order ${d.order.order_no} created`)
      navigate(`/orders/${d.order.id}`)
    } catch (e) {
      setFormError(getErrorMessage(e))
    }
  }

  const setC = (k: keyof CustomerFormInput) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setCust((s) => ({ ...s, [k]: e.target.value }))

  return (
    <PageContainer
      title="New Order"
      description="Choose or add the customer, then enter the service, schedule and amounts."
    >
      <form onSubmit={(e) => void handleSubmit(submit)(e)} noValidate className="space-y-6">
        {canChoose ? (
          <SectionCard title="Branch">
            <FormSelect
              label="Branch"
              required
              value={branchId}
              onValueChange={(v) => {
                setBranchId(v)
                setPicked(null)
              }}
              options={branches.map((b) => ({ value: b.id, label: b.name }))}
              description="The order and its customer belong to this branch."
            />
          </SectionCard>
        ) : null}

        <SectionCard title="Customer">
          <div className="space-y-4">
            <div role="group" aria-label="Customer type" className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant={mode === 'existing' ? 'default' : 'outline'}
                aria-pressed={mode === 'existing'}
                onClick={() => setMode('existing')}
              >
                Existing customer
              </Button>
              <Button
                type="button"
                size="sm"
                variant={mode === 'new' ? 'default' : 'outline'}
                aria-pressed={mode === 'new'}
                onClick={() => setMode('new')}
              >
                New customer
              </Button>
            </div>

            {mode === 'existing' ? (
              <div className="space-y-3">
                <FormInput
                  label="Find a customer"
                  type="search"
                  placeholder="Name or mobile number"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                {picked ? (
                  <p className="rounded-md border bg-muted/40 p-3 text-sm" aria-live="polite">
                    Selected: <strong>{picked.name}</strong> · {picked.mobile}
                    {picked.area ? ` · ${picked.area}` : ''}
                  </p>
                ) : null}
                {term.length >= 2 ? (
                  found.isLoading ? (
                    <p className="text-sm text-muted-foreground" role="status">
                      Searching…
                    </p>
                  ) : (found.data?.items ?? []).length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No customer found.{' '}
                      <Button
                        type="button"
                        variant="link"
                        className="h-auto p-0"
                        onClick={() => setMode('new')}
                      >
                        Add a new customer
                      </Button>
                    </p>
                  ) : (
                    <ul className="divide-y rounded-md border" aria-label="Matching customers">
                      {(found.data?.items ?? []).map((c) => (
                        <li key={c.id}>
                          <button
                            type="button"
                            className="flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-muted focus-visible:bg-muted"
                            aria-pressed={picked?.id === c.id}
                            onClick={() => setPicked(c)}
                          >
                            <span className="font-medium">{c.name}</span>
                            <span className="text-xs text-muted-foreground">
                              {c.mobile}
                              {c.area ? ` · ${c.area}` : ''} · {c.branch_name}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )
                ) : (
                  <p className="text-xs text-muted-foreground">Type at least 2 characters.</p>
                )}
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <FormInput
                  label="Customer name"
                  required
                  value={cust.name}
                  onChange={setC('name')}
                  error={custErrors.name}
                  maxLength={150}
                />
                <FormInput
                  label="Mobile number"
                  required
                  inputMode="tel"
                  value={cust.mobile}
                  onChange={setC('mobile')}
                  error={custErrors.mobile}
                  maxLength={30}
                />
                <FormInput
                  label="WhatsApp number (if different)"
                  inputMode="tel"
                  value={cust.whatsapp}
                  onChange={setC('whatsapp')}
                  error={custErrors.whatsapp}
                  maxLength={30}
                />
                <FormInput
                  label="Area"
                  value={cust.area}
                  onChange={setC('area')}
                  error={custErrors.area}
                  maxLength={100}
                />
                <FormInput
                  className="sm:col-span-2"
                  label="Address"
                  value={cust.address}
                  onChange={setC('address')}
                  error={custErrors.address}
                  maxLength={500}
                />
                <FormInput
                  className="sm:col-span-2"
                  label="Customer notes"
                  value={cust.notes}
                  onChange={setC('notes')}
                  error={custErrors.notes}
                  maxLength={2000}
                />
                <p className="text-xs text-muted-foreground sm:col-span-2">
                  A mobile number can belong to one customer per branch. If it already exists you
                  will be asked to select that customer.
                </p>
              </div>
            )}
          </div>
        </SectionCard>

        <OrderFormParts control={control} register={register} errors={errors} watch={watch} />

        <SectionCard
          title="Payment taken now"
          description="Optional. More payments can be recorded later on the order."
        >
          <div className="space-y-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={pay}
                onChange={(e) => setPay(e.target.checked)}
                aria-label="Record a payment now"
              />
              Record a payment now
            </label>
            {pay ? (
              <div className="grid gap-4 sm:grid-cols-3">
                <FormInput
                  label="Amount collected"
                  required
                  inputMode="decimal"
                  value={payment.amount}
                  onChange={(e) => setPayment((s) => ({ ...s, amount: e.target.value }))}
                  error={payError ?? undefined}
                />
                <FormSelect
                  label="Payment method"
                  required
                  value={payment.method}
                  onValueChange={(v) => setPayment((s) => ({ ...s, method: v }))}
                  options={PAYMENT_METHODS.map((m) => ({ value: m, label: m }))}
                />
                <FormInput
                  label="Reference"
                  value={payment.reference}
                  onChange={(e) => setPayment((s) => ({ ...s, reference: e.target.value }))}
                  maxLength={100}
                />
              </div>
            ) : null}
          </div>
        </SectionCard>

        {formError ? (
          <p role="alert" className="flex items-start gap-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden /> {formError}
          </p>
        ) : null}
        <FormActions
          submitLabel="Create order"
          isSubmitting={isSubmitting || create.isPending}
          onCancel={() => navigate('/orders')}
        />
      </form>
    </PageContainer>
  )
}
