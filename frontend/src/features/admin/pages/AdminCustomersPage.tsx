import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { FormField, inputClassName } from '../../../components/FormField'
import { PageHeader } from '../../../components/PageHeader'
import { adminCustomerPath } from '../routes'
import { validateCustomerId } from '../validation'

export function AdminCustomersPage() {
  const navigate = useNavigate()
  const [customerId, setCustomerId] = useState('')
  const [error, setError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const result = validateCustomerId(customerId)
    setError(result.errors.customerId ?? null)
    if (!result.isValid || result.payload === null) {
      return
    }
    navigate(adminCustomerPath(result.payload))
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Administrator"
        title="Customer lookup"
        description="Open a customer profile by identifier to review contact details, equipment, and service history links."
      />

      <section className="max-w-xl rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <form onSubmit={handleSubmit} noValidate className="grid gap-4">
          <FormField
            id="admin-customer-id"
            label="Customer ID"
            required
            hint="Use the identifier provided by the customer or the complaint record."
            error={error ?? undefined}
          >
            <input
              id="admin-customer-id"
              className={inputClassName}
              value={customerId}
              onChange={(event) => setCustomerId(event.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
            />
          </FormField>
          <div className="flex justify-end">
            <button
              type="submit"
              className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
            >
              Open customer
            </button>
          </div>
        </form>
      </section>

      <p className="max-w-xl text-xs leading-5 text-slate-500">
        The API exposes customer profiles by identifier only. Complaint records
        show the customer identifier for lookup.
      </p>
    </div>
  )
}
