const KEY_PREFIX = 'customer-message'

export interface PendingSubmission {
  content: string
  key: string
}

export function createIdempotencyKey(): string {
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.randomUUID === 'function'
  ) {
    return `${KEY_PREFIX}-${crypto.randomUUID()}`
  }

  const random = Math.random().toString(36).slice(2, 12)
  return `${KEY_PREFIX}-${Date.now().toString(36)}-${random}`
}

export function idempotencyKeyForSubmission(
  pending: PendingSubmission | null,
  content: string,
): string {
  if (pending !== null && pending.content === content) {
    return pending.key
  }
  return createIdempotencyKey()
}
