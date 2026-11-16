import { createContext, useContext } from 'react'
import type { PendingSubmission } from './idempotency'

export interface PendingMessagesState {
  pendingFor: (conversationId: string) => PendingSubmission | null
  savePending: (
    conversationId: string,
    pending: PendingSubmission,
  ) => void
  clearPending: (conversationId: string, key?: string) => void
}

export const PendingMessagesContext = createContext<
  PendingMessagesState | undefined
>(undefined)

export function usePendingMessages(): PendingMessagesState {
  const context = useContext(PendingMessagesContext)
  if (context === undefined) {
    throw new Error(
      'usePendingMessages must be used within PendingMessagesProvider',
    )
  }
  return context
}
