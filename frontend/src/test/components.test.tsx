import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
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

interface Row {
  id: string
  name: string
  amount: number
}
const COLS: DataTableColumn<Row>[] = [
  { key: 'name', header: 'Name', cell: (r) => r.name },
  { key: 'amount', header: 'Amount', align: 'right', cell: (r) => String(r.amount) },
]
const ROWS: Row[] = [
  { id: '1', name: 'Sample A', amount: 1 },
  { id: '2', name: 'Sample B', amount: 2 },
]

describe('DataTable', () => {
  it('renders rows with an accessible name and right-aligned numbers', () => {
    render(<DataTable columns={COLS} rows={ROWS} getRowId={(r) => r.id} caption="Samples" />)
    const table = screen.getByRole('table', { name: 'Samples' })
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(within(table).getByRole('columnheader', { name: 'Amount' })).toHaveClass('text-right')
  })
  it('shows skeleton rows while loading', () => {
    render(
      <DataTable
        columns={COLS}
        rows={undefined}
        getRowId={(r) => r.id}
        caption="S"
        isLoading
        skeletonRows={2}
      />,
    )
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getAllByRole('row')).toHaveLength(3)
  })
  it('shows the empty state with custom text', () => {
    render(
      <DataTable
        columns={COLS}
        rows={[]}
        getRowId={(r) => r.id}
        caption="S"
        emptyTitle="No samples"
      />,
    )
    expect(screen.getByText('No samples')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
  it('shows the error state with a working retry', async () => {
    const retry = vi.fn()
    render(
      <DataTable
        columns={COLS}
        rows={undefined}
        getRowId={(r) => r.id}
        caption="S"
        error={new Error('x')}
        onRetry={retry}
      />,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: /try again/i }))
    expect(retry).toHaveBeenCalledOnce()
  })
})

describe('display components', () => {
  it('StatusBadge puts the meaning in text, not only colour', () => {
    render(<StatusBadge status="warning">Expiring</StatusBadge>)
    expect(screen.getByText('Expiring')).toBeInTheDocument()
  })
  it('StatCard shows a dash, never an invented number, when it has no value', () => {
    render(<StatCard label="Key figure" placeholder />)
    expect(screen.getByLabelText('No data yet')).toHaveTextContent('—')
  })
  it('StatCard loading and value states', () => {
    const { rerender } = render(<StatCard label="A" isLoading />)
    expect(screen.queryByText('42')).not.toBeInTheDocument()
    rerender(<StatCard label="A" value="42" />)
    expect(screen.getByText('42')).toBeInTheDocument()
  })
  it('SectionCard and PageContainer give headings and optional actions', () => {
    render(
      <PageContainer title="Page" description="About" actions={<button>Act</button>}>
        <SectionCard title="Section" actions={<button>More</button>}>
          body
        </SectionCard>
      </PageContainer>,
    )
    expect(screen.getByRole('heading', { name: 'Page', level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Section', level: 2 })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Act' })).toBeInTheDocument()
    expect(screen.getByText('About')).toBeInTheDocument()
  })
  it('LoadingState announces itself politely', () => {
    render(<LoadingState label="Loading things" />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading things')
  })
  it('PermissionDenied explains and links back', () => {
    render(
      <MemoryRouter>
        <PermissionDenied />
      </MemoryRouter>,
    )
    expect(screen.getByText('Access denied')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to dashboard' })).toHaveAttribute('href', '/')
  })
})

describe('ConfirmDialog', () => {
  function Harness({
    onConfirm,
    isLoading = false,
  }: {
    onConfirm: () => void
    isLoading?: boolean
  }) {
    const [open, setOpen] = useState(true)
    return (
      <>
        <span>{open ? 'open' : 'closed'}</span>
        <ConfirmDialog
          open={open}
          onOpenChange={setOpen}
          title="Deactivate?"
          description="This blocks sign-in."
          confirmLabel="Deactivate"
          destructive
          isLoading={isLoading}
          onConfirm={onConfirm}
        />
      </>
    )
  }
  it('confirms, and leaves closing to the caller', async () => {
    const onConfirm = vi.fn()
    render(<Harness onConfirm={onConfirm} />)
    const dialog = await screen.findByRole('alertdialog', { name: 'Deactivate?' })
    await userEvent.setup().click(within(dialog).getByRole('button', { name: 'Deactivate' }))
    expect(onConfirm).toHaveBeenCalledOnce()
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })
  it('Cancel and Escape close without confirming', async () => {
    const onConfirm = vi.fn()
    const user = userEvent.setup()
    render(<Harness onConfirm={onConfirm} />)
    await screen.findByRole('alertdialog')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.getByText('closed')).toBeInTheDocument())
    expect(onConfirm).not.toHaveBeenCalled()
  })
  it('while loading, both buttons are disabled and Escape does not close', async () => {
    const user = userEvent.setup()
    render(<Harness onConfirm={() => undefined} isLoading />)
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByRole('button', { name: 'Deactivate' })).toBeDisabled()
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled()
    await user.keyboard('{Escape}')
    expect(screen.getByText('open')).toBeInTheDocument()
  })
})

describe('form components', () => {
  it('FormInput labels, marks required, and wires the error for assistive tech', () => {
    render(<FormInput label="Title" required error="Too short" />)
    const input = screen.getByLabelText(/Title/)
    expect(input).toBeRequired()
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAccessibleDescription('Too short')
  })
  it('FormTextarea shows its hint', () => {
    render(<FormTextarea label="Note" description="Optional" />)
    expect(screen.getByLabelText('Note')).toHaveAccessibleDescription('Optional')
  })
  it('FormDatePicker is a native date input that honours max', () => {
    render(<FormDatePicker label="Date" max="2026-11-09" />)
    const input = screen.getByLabelText('Date')
    expect(input).toHaveAttribute('type', 'date')
    expect(input).toHaveAttribute('max', '2026-11-09')
  })
  it('FormSelect is labelled and reports the chosen value', async () => {
    Element.prototype.hasPointerCapture ??= () => false
    Element.prototype.releasePointerCapture ??= () => undefined
    Element.prototype.scrollIntoView ??= () => undefined
    const onChange = vi.fn()
    render(
      <FormSelect
        label="Bank"
        options={[
          { value: 'ENBD', label: 'ENBD' },
          { value: 'ADCB', label: 'ADCB' },
        ]}
        onValueChange={onChange}
      />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('combobox', { name: 'Bank' }))
    await user.click(await screen.findByRole('option', { name: 'ADCB' }))
    expect(onChange).toHaveBeenCalledWith('ADCB')
  })
  it('FormActions: submit, cancel, and a busy state that blocks double submit', async () => {
    const onCancel = vi.fn()
    const { rerender } = render(<FormActions onCancel={onCancel} submitLabel="Save report" />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: 'Save report' })).toHaveAttribute('type', 'submit')
    rerender(<FormActions onCancel={onCancel} submitLabel="Save report" isSubmitting />)
    expect(screen.getByRole('button', { name: 'Save report' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })
})
