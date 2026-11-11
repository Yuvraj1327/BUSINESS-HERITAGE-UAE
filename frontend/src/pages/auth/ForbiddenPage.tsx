import { PermissionDenied } from '@/components/common/permission-denied'

/** Shown in place of a page the signed-in user is not allowed to open (the URL is left as typed). */
export function ForbiddenPage() {
  return (
    <div className="mx-auto max-w-xl p-6">
      <PermissionDenied />
    </div>
  )
}
