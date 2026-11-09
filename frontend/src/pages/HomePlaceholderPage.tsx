import { useAuth } from '@/auth/use-auth'
import { PageContainer } from '@/components/layout/page-container'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

/** Protected placeholder proving authentication works. Role-specific dashboards arrive in Steps 5-6. */
export function HomePlaceholderPage() {
  const { profile } = useAuth()
  return (
    <PageContainer
      title="Welcome"
      description="You are signed in. Dashboards and modules are added in later steps."
    >
      <Card>
        <CardHeader>
          <CardTitle>{profile?.full_name}</CardTitle>
          <CardDescription>Signed-in account</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="secondary" className="uppercase">
            {profile?.role}
          </Badge>
          {profile?.branch_name ? <span>{profile.branch_name}</span> : <span>All branches</span>}
        </CardContent>
      </Card>
    </PageContainer>
  )
}
