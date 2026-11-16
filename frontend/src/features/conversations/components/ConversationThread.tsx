import { useState } from 'react'
import { FormError, InlineWarning } from '../../../components/Feedback'
import { useApiClient } from '../../../lib/api/api-client-context'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { listConversationMessages } from '../api'
import { messageListErrorMessage } from '../errors'
import {
  conversationChannelLabel,
  SENDER_LABELS,
} from '../labels'
import type { Conversation, Message } from '../types'
import { MessageComposer } from './MessageComposer'

const PAGE_SIZE = 50

interface InitialThread {
  messages: Message[]
  total: number
  loadedOffset: number
}

function dedupeMessages(messages: readonly Message[]): Message[] {
  const seen = new Set<string>()
  const result: Message[] = []

  for (const message of messages) {
    if (seen.has(message.id)) {
      continue
    }
    seen.add(message.id)
    result.push(message)
  }

  return result
}

export function ConversationThread({
  conversation,
}: {
  conversation: Conversation
}) {
  const apiClient = useApiClient()
  const initial = useAsyncData<InitialThread>(
    async (signal) => {
      const first = await listConversationMessages(
        apiClient,
        conversation.id,
        { limit: PAGE_SIZE, offset: 0 },
        signal,
      )

      if (first.total <= first.items.length || first.items.length === 0) {
        return {
          messages: first.items,
          total: first.total,
          loadedOffset: 0,
        }
      }

      const lastOffset = Math.max(0, first.total - PAGE_SIZE)
      const last = await listConversationMessages(
        apiClient,
        conversation.id,
        { limit: PAGE_SIZE, offset: lastOffset },
        signal,
      )

      return {
        messages: last.items,
        total: Math.max(first.total, last.total),
        loadedOffset: lastOffset,
      }
    },
    [apiClient, conversation.id],
  )

  const [olderMessages, setOlderMessages] = useState<Message[]>([])
  const [loadedOffset, setLoadedOffset] = useState<number | null>(null)
  const [isLoadingOlder, setIsLoadingOlder] = useState(false)
  const [olderError, setOlderError] = useState<string | null>(null)

  const currentLoadedOffset =
    loadedOffset ?? initial.data?.loadedOffset ?? 0
  const messages = dedupeMessages([
    ...olderMessages,
    ...(initial.data?.messages ?? []),
  ])

  function handleSubmitted(message: Message) {
    if (!initial.data) {
      return
    }

    initial.setData({
      ...initial.data,
      messages: dedupeMessages([...initial.data.messages, message]),
      total: initial.data.total + 1,
    })
  }

  async function loadOlder() {
    if (isLoadingOlder || currentLoadedOffset <= 0) {
      return
    }

    const nextOffset = Math.max(0, currentLoadedOffset - PAGE_SIZE)
    setIsLoadingOlder(true)
    setOlderError(null)

    try {
      const page = await listConversationMessages(
        apiClient,
        conversation.id,
        { limit: PAGE_SIZE, offset: nextOffset },
      )
      setOlderMessages((current) =>
        dedupeMessages([...page.items, ...current]),
      )
      setLoadedOffset(nextOffset)
    } catch (caught) {
      setOlderError(messageListErrorMessage(caught))
    } finally {
      setIsLoadingOlder(false)
    }
  }

  return (
    <section
      className="grid gap-4 rounded-xl border border-slate-800 bg-slate-950/30 p-4"
      aria-label={`${conversationChannelLabel(conversation.channel)} conversation`}
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-white">
            {conversationChannelLabel(conversation.channel)} conversation
          </h3>
          <p className="mt-1 text-xs text-slate-500">
            Started {formatDateTime(conversation.created_at)}
          </p>
        </div>
        <span className="text-xs text-slate-600">ID {conversation.id}</span>
      </header>

      {initial.isLoading ? (
        <p className="text-sm text-slate-400">Loading messages...</p>
      ) : initial.error ? (
        <div className="grid gap-3">
          <FormError message={messageListErrorMessage(initial.error)} />
          <div>
            <button
              type="button"
              onClick={initial.reload}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500"
            >
              Retry messages
            </button>
          </div>
        </div>
      ) : !initial.data ? null : (
        <>
          {currentLoadedOffset > 0 ? (
            <div className="grid gap-2">
              <button
                type="button"
                onClick={loadOlder}
                disabled={isLoadingOlder}
                className="justify-self-start rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoadingOlder
                  ? 'Loading older messages...'
                  : 'Load older messages'}
              </button>
              {olderError ? (
                <div className="grid gap-2">
                  <FormError message={olderError} />
                  <div>
                    <button
                      type="button"
                      onClick={loadOlder}
                      className="text-xs font-semibold text-sky-300 underline underline-offset-2 hover:text-sky-200"
                    >
                      Retry older messages
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {messages.length === 0 ? (
            <p className="rounded-xl border border-dashed border-slate-800 px-4 py-6 text-center text-sm text-slate-400">
              No messages in this conversation yet.
            </p>
          ) : (
            <ol className="grid gap-3" aria-label="Message history">
              {messages.map((message) => {
                const isCustomer = message.sender_type === 'customer'
                return (
                  <li
                    key={message.id}
                    data-testid="conversation-message"
                    data-sender={message.sender_type}
                    className={`max-w-[85%] rounded-2xl border px-4 py-3 ${
                      isCustomer
                        ? 'ml-auto border-sky-500/30 bg-sky-500/10'
                        : 'mr-auto border-slate-700 bg-slate-800/60'
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                      <span className="font-semibold text-slate-200">
                        {SENDER_LABELS[message.sender_type]}
                      </span>
                      <span>{formatDateTime(message.created_at)}</span>
                    </div>
                    <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-slate-100">
                      {message.content}
                    </p>
                  </li>
                )
              })}
            </ol>
          )}

          {conversation.channel === 'web' ? (
            <MessageComposer
              conversationId={conversation.id}
              onSubmitted={handleSubmitted}
            />
          ) : (
            <InlineWarning>
              This conversation is read-only here. Sending messages through{' '}
              {conversationChannelLabel(conversation.channel)} is not
              supported in this application yet.
            </InlineWarning>
          )}
        </>
      )}
    </section>
  )
}
