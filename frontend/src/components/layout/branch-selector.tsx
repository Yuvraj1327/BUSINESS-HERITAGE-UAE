import { Building2 } from 'lucide-react'
import { ALL_BRANCHES, useBranchContext } from '@/components/layout/branch-context'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

/** Global branch filter (users with all-branch scope only; the layout decides whether to render it). */
export function BranchSelector() {
  const { selectedBranchId, setSelectedBranchId, branches, branchesStatus } = useBranchContext()
  const unavailable = branchesStatus === 'error'
  return (
    <Select
      value={selectedBranchId}
      onValueChange={setSelectedBranchId}
      disabled={branchesStatus === 'loading' || unavailable}
    >
      <SelectTrigger
        aria-label="Branch"
        className="h-11 w-full min-w-0 md:h-9 md:w-52"
        title={unavailable ? 'Branches could not be loaded' : undefined}
      >
        <Building2 className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <SelectValue placeholder={unavailable ? 'Branches unavailable' : 'Loading branches…'} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL_BRANCHES}>All branches</SelectItem>
        {branches.map((b) => (
          <SelectItem key={b.id} value={b.id}>
            {b.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** Read-only branch label for users limited to one branch: shows the assignment, offers no choice. */
export function AssignedBranch() {
  const { selectedBranchName } = useBranchContext()
  if (!selectedBranchName) return null
  return (
    <span
      className="flex h-9 max-w-44 items-center gap-2 rounded-md border bg-card px-3 text-sm"
      title="Your assigned branch"
    >
      <Building2 className="size-4 shrink-0 text-teal" aria-hidden />
      <span className="truncate font-medium">{selectedBranchName}</span>
    </span>
  )
}
