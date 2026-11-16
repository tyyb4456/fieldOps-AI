import { useState } from 'react'
import { Badge } from '../../../components/Badge'
import { EmptyState } from '../../../components/EmptyState'
import { FormError } from '../../../components/Feedback'
import { useApiClient } from '../../../lib/api/api-client-context'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { listComplaintConversations } from '../api'
import { conversationListErrorMessage } from '../errors'
import { conversationChannelLabel } from '../labels'
import { ConversationThread } from './ConversationThread'

export function ComplaintConversations({
  complaintId,
}: {
  complaintId: string
}) {
  const apiClient = useApiClient()
  const conversations = useAsyncData(
    (signal) =>
      listComplaintConversations(
        apiClient,
        complaintId,
        { limit: 100 },
        signal,
      ),
    [apiClient, complaintId],
  )
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const items = conversations.data?.items ?? []
  const selected =
    items.find((item) => item.id === selectedId) ?? items[0] ?? null
  const activeId = selected?.id ?? null

  return (
    <section
      className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"
      aria-labelledby="complaint-conversations-heading"
    >
      <div>
        <h2
          id="complaint-conversations-heading"
          className="text-base font-semibold text-white"
        >
          Conversations
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          Messages exchanged with the service team about this complaint.
        </p>
      </div>

      <div className="mt-4">
        {conversations.isLoading ? (
          <p className="text-sm text-slate-400">
            Loading conversations...
          </p>
        ) : conversations.error ? (
          <div className="grid gap-3">
            <FormError
              message={conversationListErrorMessage(conversations.error)}
            />
            <div>
              <button
                type="button"
                onClick={conversations.reload}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500"
              >
                Retry conversations
              </button>
            </div>
          </div>
        ) : !conversations.data ? null : items.length === 0 ? (
          <EmptyState
            title="No conversation available"
            description="This complaint does not have a conversation yet. Your complaint and its status are still available. No conversation is created automatically for older complaints."
          />
        ) : (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,18rem)_minmax(0,1fr)]">
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">
                {items.length} conversation{items.length === 1 ? '' : 's'}
              </p>
              <ul className="mt-2 grid gap-2">
                {items.map((item) => {
                  const isSelected = item.id === activeId
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        data-testid={`conversation-option-${item.id}`}
                        aria-pressed={isSelected}
                        onClick={() => setSelectedId(item.id)}
                        className={`w-full rounded-xl border px-4 py-3 text-left transition ${
                          isSelected
                            ? 'border-sky-500/50 bg-sky-500/10'
                            : 'border-slate-800 bg-slate-950/40 hover:border-slate-600'
                        }`}
                      >
                        <span className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-sm font-semibold text-white">
                            {conversationChannelLabel(item.channel)}{' '}
                            conversation
                          </span>
                          {isSelected ? (
                            <Badge tone="info">Open</Badge>
                          ) : null}
                        </span>
                        <span className="mt-1 block text-xs text-slate-400">
                          Started {formatDateTime(item.created_at)}
                        </span>
                        <span className="mt-1 block break-all text-xs text-slate-600">
                          ID {item.id}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>

            <div className="min-w-0">
              {selected ? (
                <ConversationThread
                  key={selected.id}
                  conversation={selected}
                />
              ) : null}
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
