import { Mail, Phone } from 'lucide-react'
import { SectionCard } from '@/components/common/section-card'
import { APP_DISPLAY_NAME } from '@/constants'
import { env } from '@/config/env'
import { useHealth } from '@/hooks/use-health'

export function AboutSettingsPage() {
  const health = useHealth()
  const hasSupport = env.supportEmail !== '' || env.supportPhone !== ''
  return (
    <>
      <SectionCard title="Application">
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium text-muted-foreground">Name</dt>
            <dd className="text-sm">{APP_DISPLAY_NAME}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-muted-foreground">App version</dt>
            <dd className="text-sm">{__APP_VERSION__}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-muted-foreground">Server</dt>
            <dd className="text-sm">
              {health.data
                ? `${health.data.status}, version ${health.data.version}`
                : health.isError
                  ? 'Not reachable'
                  : 'Checking…'}
            </dd>
          </div>
        </dl>
      </SectionCard>
      <SectionCard title="Support">
        {hasSupport ? (
          <ul className="space-y-2 text-sm">
            {env.supportEmail ? (
              <li className="flex items-center gap-2">
                <Mail className="size-4" aria-hidden />
                <a className="text-accent underline" href={`mailto:${env.supportEmail}`}>
                  {env.supportEmail}
                </a>
              </li>
            ) : null}
            {env.supportPhone ? (
              <li className="flex items-center gap-2">
                <Phone className="size-4" aria-hidden />
                <a
                  className="text-accent underline"
                  href={`tel:${env.supportPhone.replace(/\s/g, '')}`}
                >
                  {env.supportPhone}
                </a>
              </li>
            ) : null}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            For help with your account or a problem in the app, contact your administrator (the
            Owner).
          </p>
        )}
      </SectionCard>
      <SectionCard title="Privacy">
        <ul className="list-disc space-y-1.5 pl-5 text-sm">
          <li>
            We keep your name, sign-in email, optional phone number and optional profile photo, plus
            your role and branch assignment.
          </li>
          <li>Your profile photo is stored privately; only you and the Owner can see it.</li>
          <li>
            Business actions you take (for example creating or changing records) are recorded in the
            activity history with your user, for accountability. The Owner can review it.
          </li>
          <li>
            Passwords are handled only by the sign-in service and are never visible to the app or
            the Owner.
          </li>
          <li>
            Your theme, date, timezone and notification choices are saved to your account. Nothing
            is sent to third parties or by email.
          </li>
        </ul>
      </SectionCard>
    </>
  )
}
