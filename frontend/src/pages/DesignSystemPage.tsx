import { zodResolver } from '@hookform/resolvers/zod'
import { Inbox } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { EmptyState } from '@/components/common/empty-state'
import { ErrorState } from '@/components/common/error-state'
import { FormField } from '@/components/common/form-field'
import { LoadingIndicator } from '@/components/common/loading-indicator'
import { PageContainer } from '@/components/layout/page-container'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { BANKS } from '@/constants'
import { aedAmountSchema } from '@/schemas/common'
import { formatAED } from '@/utils/format'

const sampleSchema = z.object({
  title: z.string().min(2, 'At least 2 characters'),
  amount: aedAmountSchema,
})
type SampleForm = z.infer<typeof sampleSchema>

/** Development-only preview of the reusable foundations (route is not registered in production builds). */
export function DesignSystemPage() {
  const [bank, setBank] = useState<string>(BANKS[0])
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<SampleForm>({
    resolver: zodResolver(sampleSchema),
    defaultValues: { title: '', amount: '' },
  })

  return (
    <PageContainer title="Design system" description="Reusable foundations (development only).">
      <Card>
        <CardHeader>
          <CardTitle>Buttons and badges</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2">
          <Button>Primary</Button>
          <Button variant="accent">Accent</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Badge>Default</Badge>
          <Badge variant="success">Matches</Badge>
          <Badge variant="warning">Expiring</Badge>
          <Badge variant="destructive">Diff</Badge>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Form controls</CardTitle>
          <CardDescription>React Hook Form + Zod, AED amount as a decimal string</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="grid max-w-md gap-4"
            onSubmit={(e) =>
              void handleSubmit((v) => toast.success(`Valid: ${formatAED(v.amount)}`))(e)
            }
          >
            <FormField label="Title" required error={errors.title}>
              <Input placeholder="Enter a title" {...register('title')} />
            </FormField>
            <FormField
              label="Amount (AED)"
              required
              error={errors.amount}
              description="Up to 2 decimals"
            >
              <Input inputMode="decimal" placeholder="0.00" {...register('amount')} />
            </FormField>
            <div className="grid gap-1.5">
              <Label>Bank</Label>
              <Select value={bank} onValueChange={setBank}>
                <SelectTrigger aria-label="Bank">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BANKS.map((b) => (
                    <SelectItem key={b} value={b}>
                      {b}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2">
              <Button type="submit">Validate</Button>
              <Dialog>
                <DialogTrigger asChild>
                  <Button type="button" variant="outline">
                    Open dialog
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Confirm action</DialogTitle>
                    <DialogDescription>
                      Dialogs are used for forms and confirmations.
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button variant="outline">Cancel</Button>
                    <Button>Confirm</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Table</CardTitle>
          <CardDescription>
            Sample layout only: illustrative values, not business data
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Label</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Check</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>Row A</TableCell>
                <TableCell className="tabular text-right">{formatAED(1000)}</TableCell>
                <TableCell>
                  <Badge variant="success">Matches</Badge>
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Row B</TableCell>
                <TableCell className="tabular text-right">{formatAED(300)}</TableCell>
                <TableCell>
                  <Badge variant="destructive">Diff</Badge>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <LoadingIndicator fill label="Loading data…" />
        <EmptyState
          icon={Inbox}
          title="No records yet"
          description="Create the first record to get started."
        />
        <ErrorState message="Example error message." onRetry={() => toast.info('Retry clicked')} />
      </div>
    </PageContainer>
  )
}
