import { useState } from 'react'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { Notice } from '../../../components/Feedback'
import { PageHeader } from '../../../components/PageHeader'
import { apiErrorMessage } from '../../../lib/api/errors'
import { useApiClient } from '../../../lib/api/api-client-context'
import { formatDate } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { fetchCustomerProfile, updateCustomerProfile } from '../api'
import { ProfileForm } from '../components/ProfileForm'
import type { CustomerUpdateRequest } from '../types'

function ReadOnlyRow({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
      <dt className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm font-medium text-slate-100">
        {value}
      </dd>
    </div>
  )
}

export function CustomerProfilePage() {
  const apiClient = useApiClient()
  const [notice, setNotice] = useState<string | null>(null)
  const { data, error, isLoading, reload, setData } = useAsyncData(
    (signal) => fetchCustomerProfile(apiClient, signal),
    [apiClient],
  )

  if (isLoading) {
    return <LoadingScreen label="Loading your profile..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={apiErrorMessage(error, 'Unable to load your profile.')}
        onRetry={reload}
      />
    )
  }

  async function saveProfile(payload: CustomerUpdateRequest) {
    const updated = await updateCustomerProfile(apiClient, payload)
    setData(updated)
    setNotice('Your profile has been updated.')
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Profile"
        title="Your profile"
        description="Your name, email, and phone come from your authenticated account. You can update your service address and preferred language."
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <ReadOnlyRow label="Full name" value={data.full_name} />
        <ReadOnlyRow label="Email" value={data.email ?? 'Not provided'} />
        <ReadOnlyRow label="Phone" value={data.phone ?? 'Not provided'} />
        <ReadOnlyRow
          label="Account status"
          value={data.is_active ? 'Active' : 'Inactive'}
        />
        <ReadOnlyRow label="Customer since" value={formatDate(data.created_at)} />
        <ReadOnlyRow label="Customer ID" value={data.id} />
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">
          Editable profile details
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          Only the fields supported by the customer profile API are shown here.
        </p>
        <div className="mt-5">
          <ProfileForm
            key={`${data.address ?? ''}|${data.preferred_language ?? ''}`}
            profile={data}
            onSubmit={saveProfile}
          />
        </div>
      </section>
    </div>
  )
}
