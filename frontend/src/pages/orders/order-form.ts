import type { OrderFormInput, OrderFormValues } from '@/schemas/orders'

export const EMPTY_ORDER_FORM: OrderFormInput = {
  category_id: '',
  service_type: 'Standard',
  notes: '',
  pickup_date: '',
  pickup_time: '',
  pickup_address: '',
  delivery_date: '',
  delivery_time: '',
  delivery_address: '',
  order_total: '',
  discount: '0',
  service_fee: '0',
}

/** Form values to the API body. Empty optional text becomes null; amounts stay as strings. */
export function orderBody(v: OrderFormValues) {
  return {
    category_id: v.category_id,
    service_type: v.service_type,
    notes: v.notes || null,
    pickup_date: v.pickup_date || null,
    pickup_time: v.pickup_time || null,
    pickup_address: v.pickup_address || null,
    delivery_date: v.delivery_date,
    delivery_time: v.delivery_time,
    delivery_address: v.delivery_address || null,
    order_total: v.order_total,
    discount: v.discount || '0',
    service_fee: v.service_fee || '0',
  }
}
