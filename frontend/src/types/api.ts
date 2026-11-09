/** Error envelope returned by the backend (see backend/app/core/exceptions.py). */
export interface ApiErrorBody {
  error: {
    code: string
    message: string
    fields?: Record<string, string[]> | null
  }
  request_id?: string | null
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
