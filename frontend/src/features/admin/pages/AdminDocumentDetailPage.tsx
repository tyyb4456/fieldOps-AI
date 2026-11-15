import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormError, InlineWarning, Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import type { PaginatedResponse } from '../../../lib/api/types'
import type {
  DocumentChunk,
  DocumentMetadata,
} from '../../documents/types'
import {
  activateAdminDocument,
  deactivateAdminDocument,
  deleteAdminDocument,
  getAdminDocument,
  ingestAdminDocument,
  listAdminDocumentChunks,
  updateAdminDocument,
} from '../api'
import {
  ActiveBadge,
  IngestionStatusBadge,
} from '../components/AdminBadges'
import { AdminPagination } from '../components/AdminPagination'
import { DocumentMetadataForm } from '../components/DocumentForms'
import { adminDocumentErrorMessage } from '../errors'
import { ADMIN_ROUTES } from '../routes'

const CHUNK_PAGE_SIZE = 20

interface DocumentDetailData {
  document: DocumentMetadata
  chunks: PaginatedResponse<DocumentChunk>
}

function DetailRow({ label, value }: { label: string; value: string }) {
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

function formatBytes(bytes: number | null): string {
  if (bytes === null) {
    return 'Unknown'
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function AdminDocumentDetailPage() {
  const apiClient = useApiClient()
  const navigate = useNavigate()
  const { documentId = '' } = useParams()
  const [chunkOffset, setChunkOffset] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [editing, setEditing] = useState(false)

  const { data, error, isLoading, reload } =
    useAsyncData<DocumentDetailData>(
      async (signal) => {
        const [document, chunks] = await Promise.all([
          getAdminDocument(apiClient, documentId, signal),
          listAdminDocumentChunks(
            apiClient,
            documentId,
            { limit: CHUNK_PAGE_SIZE, offset: chunkOffset },
            signal,
          ),
        ])
        return { document, chunks }
      },
      [apiClient, documentId, chunkOffset],
    )

  if (isLoading) {
    return <LoadingScreen label="Loading document..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={adminDocumentErrorMessage(error)}
        onRetry={reload}
      />
    )
  }

  const { document, chunks } = data
  const canActivate =
    document.ingestion_status === 'ready' && !document.is_active
  const canDeactivate = document.is_active

  async function runAction(
    action: () => Promise<unknown>,
    successMessage: string,
  ) {
    setSubmitting(true)
    setActionError(null)
    try {
      await action()
      setNotice(successMessage)
      reload()
    } catch (caught) {
      setActionError(adminDocumentErrorMessage(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function saveMetadata(
    fields: Parameters<typeof updateAdminDocument>[2],
  ) {
    setSubmitting(true)
    try {
      await updateAdminDocument(apiClient, document.id, fields)
      setEditing(false)
      setNotice('Document metadata updated.')
      reload()
    } finally {
      setSubmitting(false)
    }
  }

  async function removeDocument() {
    if (
      !window.confirm(
        'Delete this document, its chunks, and the stored file? This cannot be undone.',
      )
    ) {
      return
    }
    setSubmitting(true)
    setActionError(null)
    try {
      await deleteAdminDocument(apiClient, document.id)
      navigate(ADMIN_ROUTES.documents, {
        state: { notice: 'Document deleted.' },
      })
    } catch (caught) {
      setActionError(adminDocumentErrorMessage(caught))
      setSubmitting(false)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Document"
        title={document.document_name}
        description={`${document.manufacturer} ${document.model}${
          document.version ? ` - v${document.version}` : ''
        }`}
        actions={
          <Link
            to={ADMIN_ROUTES.documents}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Back to documents
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}
      <FormError message={actionError} />

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <IngestionStatusBadge status={document.ingestion_status} />
          <ActiveBadge isActive={document.is_active} />
          <span className="text-xs text-slate-500">
            Uploaded {formatDateTime(document.created_at)}
          </span>
        </div>

        {document.ingestion_error ? (
          <p className="mt-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
            {document.ingestion_error}
          </p>
        ) : null}

        {document.ingestion_status === 'ready' && !document.is_active ? (
          <p className="mt-3 text-sm text-slate-400">
            Ingestion is complete. Activate this document to make it available
            for retrieval.
          </p>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() =>
              void runAction(
                () => ingestAdminDocument(apiClient, document.id),
                'Document queued for re-ingestion.',
              )
            }
            disabled={submitting}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Re-ingest
          </button>
          {canActivate ? (
            <button
              type="button"
              onClick={() =>
                void runAction(
                  () => activateAdminDocument(apiClient, document.id),
                  'Document activated.',
                )
              }
              disabled={submitting}
              className="rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Activate
            </button>
          ) : null}
          {canDeactivate ? (
            <button
              type="button"
              onClick={() =>
                void runAction(
                  () => deactivateAdminDocument(apiClient, document.id),
                  'Document deactivated.',
                )
              }
              disabled={submitting}
              className="rounded-xl border border-amber-400/50 px-4 py-2.5 text-sm font-medium text-amber-200 transition hover:bg-amber-400/10 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Deactivate
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void removeDocument()}
            disabled={submitting}
            className="rounded-xl border border-rose-500/50 px-4 py-2.5 text-sm font-medium text-rose-200 transition hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Delete document
          </button>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <DetailRow label="Document ID" value={document.id} />
        <DetailRow
          label="Original file"
          value={document.original_filename ?? 'Unavailable'}
        />
        <DetailRow label="Size" value={formatBytes(document.byte_size)} />
        <DetailRow
          label="Ingested"
          value={
            document.ingested_at
              ? formatDateTime(document.ingested_at)
              : 'Not ingested'
          }
        />
        <DetailRow
          label="Content type"
          value={document.content_type ?? 'Unknown'}
        />
        <DetailRow
          label="Checksum"
          value={document.checksum_sha256 ?? 'Unavailable'}
        />
        <DetailRow
          label="Uploaded by"
          value={document.uploaded_by_id ?? 'Unknown'}
        />
        <DetailRow
          label="Chunks"
          value={String(chunks.total)}
        />
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-white">Metadata</h2>
            <p className="mt-1 text-sm text-slate-400">
              Changes update retrieval filtering and citation labels.
            </p>
          </div>
          {!editing ? (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
            >
              Edit metadata
            </button>
          ) : null}
        </div>
        {editing ? (
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
            <DocumentMetadataForm
              initial={{
                manufacturer: document.manufacturer,
                model: document.model,
                documentName: document.document_name,
                version: document.version ?? '',
              }}
              isSubmitting={submitting}
              onSubmit={saveMetadata}
              errorMessage={adminDocumentErrorMessage}
            />
          </div>
        ) : null}
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">Stored chunks</h2>
        {document.ingestion_status !== 'ready' ? (
          <div className="mt-4">
            <InlineWarning>
              Chunks are available after ingestion completes successfully.
            </InlineWarning>
          </div>
        ) : chunks.items.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">
            This document has no stored chunks.
          </p>
        ) : (
          <>
            <ul className="mt-4 grid gap-3">
              {chunks.items.map((chunk) => (
                <li
                  key={chunk.id}
                  className="rounded-xl border border-slate-800 bg-slate-950/40 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                    <span>Chunk {chunk.chunk_index}</span>
                    <span>
                      {chunk.page_number
                        ? `Page ${chunk.page_number}`
                        : 'Page unavailable'}
                    </span>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">
                    {chunk.content}
                  </p>
                </li>
              ))}
            </ul>
            <div className="mt-4">
              <AdminPagination
                offset={chunkOffset}
                pageSize={CHUNK_PAGE_SIZE}
                total={chunks.total}
                noun="chunks"
                onOffsetChange={setChunkOffset}
              />
            </div>
          </>
        )}
      </section>
    </div>
  )
}
