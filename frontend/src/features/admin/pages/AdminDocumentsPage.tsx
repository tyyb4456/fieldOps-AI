import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { Notice } from '../../../components/Feedback'
import { FormField, inputClassName } from '../../../components/FormField'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { uploadAdminDocument, listAdminDocuments } from '../api'
import {
  ActiveBadge,
  IngestionStatusBadge,
} from '../components/AdminBadges'
import { AdminPagination } from '../components/AdminPagination'
import { DocumentUploadForm } from '../components/DocumentForms'
import { adminDocumentErrorMessage } from '../errors'
import { ADMIN_ROUTES, adminDocumentPath } from '../routes'

const PAGE_SIZE = 20

export function AdminDocumentsPage() {
  const apiClient = useApiClient()
  const [offset, setOffset] = useState(0)
  const [manufacturerInput, setManufacturerInput] = useState('')
  const [modelInput, setModelInput] = useState('')
  const [manufacturer, setManufacturer] = useState('')
  const [model, setModel] = useState('')
  const [activeFilter, setActiveFilter] = useState<'all' | 'active' | 'inactive'>(
    'all',
  )
  const [showUpload, setShowUpload] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const { data, error, isLoading, reload } = useAsyncData(
    (signal) =>
      listAdminDocuments(
        apiClient,
        {
          manufacturer: manufacturer || undefined,
          model: model || undefined,
          is_active:
            activeFilter === 'all' ? undefined : activeFilter === 'active',
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [apiClient, offset, manufacturer, model, activeFilter],
  )

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setOffset(0)
    setManufacturer(manufacturerInput.trim())
    setModel(modelInput.trim())
  }

  async function upload(fields: Parameters<typeof uploadAdminDocument>[1]) {
    setUploading(true)
    try {
      await uploadAdminDocument(apiClient, fields)
      setShowUpload(false)
      setNotice('Document uploaded and queued for ingestion.')
      reload()
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Administrator"
        title="Technical documents"
        description="Upload PDF manuals, monitor ingestion, activate documents for retrieval, and inspect stored chunks."
        actions={
          <button
            type="button"
            onClick={() => setShowUpload((current) => !current)}
            className="rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
          >
            {showUpload ? 'Close upload form' : 'Upload document'}
          </button>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      {showUpload ? (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
          <h2 className="text-base font-semibold text-white">
            Upload a new PDF
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Ingestion runs asynchronously. The document must finish ingestion
            before it can be activated.
          </p>
          <div className="mt-4">
            <DocumentUploadForm
              isSubmitting={uploading}
              onSubmit={upload}
              errorMessage={adminDocumentErrorMessage}
            />
          </div>
        </section>
      ) : null}

      <section className="grid gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-5 sm:grid-cols-3">
        <form onSubmit={applyFilters} className="grid gap-3 sm:col-span-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField id="admin-document-manufacturer-filter" label="Manufacturer">
              <input
                id="admin-document-manufacturer-filter"
                className={inputClassName}
                value={manufacturerInput}
                onChange={(event) => setManufacturerInput(event.target.value)}
              />
            </FormField>
            <FormField id="admin-document-model-filter" label="Model">
              <input
                id="admin-document-model-filter"
                className={inputClassName}
                value={modelInput}
                onChange={(event) => setModelInput(event.target.value)}
              />
            </FormField>
          </div>
          <div>
            <button
              type="submit"
              className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
            >
              Apply filters
            </button>
          </div>
        </form>
        <FormField id="admin-document-active-filter" label="Activation">
          <select
            id="admin-document-active-filter"
            className={inputClassName}
            value={activeFilter}
            onChange={(event) => {
              setOffset(0)
              setActiveFilter(
                event.target.value as 'all' | 'active' | 'inactive',
              )
            }}
          >
            <option value="all">All documents</option>
            <option value="active">Active only</option>
            <option value="inactive">Inactive only</option>
          </select>
        </FormField>
      </section>

      {isLoading ? (
        <LoadingScreen label="Loading documents..." />
      ) : error || !data ? (
        <ErrorScreen
          message={apiErrorMessage(error, 'Unable to load documents.')}
          onRetry={reload}
        />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No documents match these filters"
          description="Upload a PDF manual to make technical content available for retrieval."
        />
      ) : (
        <>
          <ul className="grid gap-3">
            {data.items.map((document) => (
              <li key={document.id}>
                <Link
                  to={adminDocumentPath(document.id)}
                  className="block rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-sky-500/40"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <IngestionStatusBadge
                      status={document.ingestion_status}
                    />
                    <ActiveBadge isActive={document.is_active} />
                    <span className="text-xs text-slate-500">
                      Uploaded {formatDateTime(document.created_at)}
                    </span>
                  </div>
                  <h2 className="mt-3 text-base font-semibold text-white">
                    {document.document_name}
                    {document.version ? ` (v${document.version})` : ''}
                  </h2>
                  <p className="mt-1 text-sm text-slate-400">
                    {document.manufacturer} {document.model}
                  </p>
                  {document.ingestion_error ? (
                    <p className="mt-2 text-xs text-rose-300">
                      {document.ingestion_error}
                    </p>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
          <AdminPagination
            offset={offset}
            pageSize={PAGE_SIZE}
            total={data.total}
            noun="documents"
            onOffsetChange={setOffset}
          />
        </>
      )}

      <Link
        to={ADMIN_ROUTES.dashboard}
        className="w-fit rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
      >
        Back to dashboard
      </Link>
    </div>
  )
}
