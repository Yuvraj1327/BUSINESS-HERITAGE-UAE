import { AuthLayout } from '@/layouts/AuthLayout'

export function ConfigMissingPage() {
  return (
    <AuthLayout
      title="Sign-in is not configured"
      description="VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are not set. Add them to frontend/.env.local and restart the dev server (see docs/authentication/SUPABASE_SETUP.md)."
    >
      <p className="text-sm text-muted-foreground">
        Only the public anon key belongs here, never the service-role key.
      </p>
    </AuthLayout>
  )
}
