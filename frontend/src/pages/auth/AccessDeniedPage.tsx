import { ShieldAlert } from 'lucide-react'
import { useAuth } from '@/auth/use-auth'
import { Button } from '@/components/ui/button'
import { AuthLayout } from '@/layouts/AuthLayout'

/** Signed in with Supabase, but the ERP will not let this account in (no profile, inactive, or profile load failed). */
export function AccessDeniedPage() {
  const { profileStatus, profileError, reloadProfile, signOut } = useAuth()
  const copy =
    profileStatus === 'inactive'
      ? {
          title: 'Account inactive',
          body: 'This account has been deactivated. Please contact the administrator.',
        }
      : profileStatus === 'missing'
        ? {
            title: 'Account not set up',
            body: 'Your sign-in works, but your account has not been set up yet. Please contact the administrator.',
          }
        : {
            title: 'Could not load your account',
            body: profileError ?? 'Something went wrong while loading your account.',
          }

  return (
    <AuthLayout title={copy.title}>
      <div className="grid gap-4">
        <p className="flex gap-2 text-sm text-muted-foreground">
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          {copy.body}
        </p>
        {profileStatus === 'error' ? (
          <Button variant="outline" onClick={reloadProfile}>
            Try again
          </Button>
        ) : null}
        <Button onClick={() => void signOut()}>Sign out</Button>
      </div>
    </AuthLayout>
  )
}
