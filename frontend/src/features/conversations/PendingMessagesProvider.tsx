import {
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { PendingSubmission } from './idempotency'
import {
  PendingMessagesContext,
  type PendingMessagesState,
} from './pending-messages-context'

export function PendingMessagesProvider({
  children,
}: {
  children: ReactNode
}) {
  const [pendingByConversation, setPendingByConversation] = useState<
    Record<string, PendingSubmission>
  >({})

  const pendingFor = useCallback(
    (conversationId: string): PendingSubmission | null =>
      pendingByConversation[conversationId] ?? null,
    [pendingByConversation],
  )

  const savePending = useCallback(
    (conversationId: string, pending: PendingSubmission) => {
      setPendingByConversation((current) => ({
        ...current,
        [conversationId]: pending,
      }))
    },
    [],
  )

  const clearPending = useCallback(
    (conversationId: string, key?: string) => {
      setPendingByConversation((current) => {
        const existing = current[conversationId]
        if (existing === undefined) {
          return current
        }
        if (key !== undefined && existing.key !== key) {
          return current
        }

        const next = { ...current }
        delete next[conversationId]
        return next
      })
    },
    [],
  )

  const value = useMemo<PendingMessagesState>(
    () => ({ pendingFor, savePending, clearPending }),
    [clearPending, pendingFor, savePending],
  )

  return (
    <PendingMessagesContext.Provider value={value}>
      {children}
    </PendingMessagesContext.Provider>
  )
}
