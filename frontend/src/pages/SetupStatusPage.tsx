import { CheckCircle2, CircleDashed, RotateCw } from 'lucide-react'
import { ErrorState } from '@/components/common/error-state'
import { LoadingIndicator } from '@/components/common/loading-indicator'
import { PageContainer } from '@/components/layout/page-container'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { env } from '@/config/env'
import { useHealth } from '@/hooks/use-health'

function Row({ label, value, ok }: { label: string; value: string; ok: boolean | null }) {
  return (
    <li className="flex items-center justify-between gap-3 py-2 text-sm">
      <span className="flex items-center gap-2">
        {ok === null ? (
          <CircleDashed className="size-4 text-muted-foreground" aria-hidden />
        ) : (
          <CheckCircle2 className="size-4 text-success" aria-hidden />
        )}
        {label}
      </span>
      <span className="truncate text-muted-foreground">{value}</span>
    </li>
  )
}

/** Placeholder landing page proving React, routing, styling, the API client and providers all work. */
export function SetupStatusPage() {
  const health = useHealth()

  return (
    <PageContainer
      title="Application foundation"
      description="System check. Business modules and dashboards are added in later steps."
      actions={
        <Button variant="outline" size="sm" onClick={() => void health.refetch()}>
          <RotateCw /> Re-check
        </Button>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Backend API</CardTitle>
            <CardDescription>{env.apiBaseUrl}</CardDescription>
          </CardHeader>
          <CardContent>
            {health.isPending ? (
              <LoadingIndicator label="Contacting API…" />
            ) : health.isError ? (
              <ErrorState
                title="API not reachable"
                error={health.error}
                onRetry={() => void health.refetch()}
                className="py-6"
              />
            ) : (
              <ul className="divide-y">
                <li className="flex items-center justify-between py-2 text-sm">
                  <span>Status</span>
                  <Badge variant="success">{health.data.status}</Badge>
                </li>
                <Row label="Service" value={health.data.service} ok />
                <Row label="Version" value={health.data.version} ok />
                <Row label="Environment" value={health.data.environment} ok />
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Frontend configuration</CardTitle>
            <CardDescription>Validated environment (no secrets are shown)</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              <Row label="Build mode" value={env.mode} ok />
              <Row label="API base URL" value={env.apiBaseUrl} ok />
              <Row
                label="Supabase (Step 4)"
                value={env.supabaseConfigured ? 'configured' : 'not configured yet'}
                ok={env.supabaseConfigured ? true : null}
              />
            </ul>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  )
}
