import { useRef, useState, type FormEvent } from 'react'
import { FormError } from '../../../components/Feedback'
import {
  FormField,
  inputClassName,
} from '../../../components/FormField'
import { useApiClient } from '../../../lib/api/api-client-context'
import { createSubmissionGuard } from '../../../lib/forms/submission-guard'
import type { FieldErrors } from '../../../lib/forms/validation'
import { sendConversationMessage } from '../api'
import {
  isUncertainSubmissionError,
  messageSubmissionErrorMessage,
} from '../errors'
import { idempotencyKeyForSubmission } from '../idempotency'
import { usePendingMessages } from '../pending-messages-context'
import type { Message } from '../types'
import {
  MESSAGE_CONTENT_MAX_LENGTH,
  validateMessageForm,
} from '../validation'

export function MessageComposer({
  conversationId,
  onSubmitted,
}: {
  conversationId: string
  onSubmitted: (message: Message) => void
}) {
  const apiClient = useApiClient()
  const { pendingFor, savePending, clearPending } = usePendingMessages()
  const pending = pendingFor(conversationId)
  const [content, setContent] = useState(
    () => pending?.content ?? '',
  )
  const [errors, setErrors] = useState<FieldErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const guardRef = useRef(createSubmissionGuard())

  function updateContent(value: string) {
    setContent(value)
    if (pending !== null && pending.content !== value.trim()) {
      clearPending(conversationId, pending.key)
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!guardRef.current.begin()) {
      return
    }

    const result = validateMessageForm({ content })
    setErrors(result.errors)
    setApiError(null)

    if (!result.isValid || result.payload === null) {
      guardRef.current.end()
      return
    }

    const nextContent = result.payload.content
    const key = idempotencyKeyForSubmission(pending, nextContent)
    savePending(conversationId, { content: nextContent, key })
    setIsSubmitting(true)

    try {
      const message = await sendConversationMessage(
        apiClient,
        conversationId,
        nextContent,
        key,
      )
      clearPending(conversationId, key)
      setContent('')
      onSubmitted(message)
    } catch (caught) {
      if (!isUncertainSubmissionError(caught)) {
        clearPending(conversationId, key)
      }
      setApiError(messageSubmissionErrorMessage(caught))
    } finally {
      setIsSubmitting(false)
      guardRef.current.end()
    }
  }

  const buttonLabel = isSubmitting
    ? 'Sending...'
    : pending
      ? 'Retry sending'
      : 'Send message'

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-3">
      <FormError message={apiError} />

      <FormField
        id="conversation-message-content"
        label="Message"
        hint={`Up to ${MESSAGE_CONTENT_MAX_LENGTH.toLocaleString()} characters.`}
        error={errors.content}
      >
        <textarea
          id="conversation-message-content"
          className={`${inputClassName} min-h-24 resize-y`}
          value={content}
          maxLength={MESSAGE_CONTENT_MAX_LENGTH}
          aria-invalid={errors.content ? true : undefined}
          aria-describedby={
            errors.content
              ? 'conversation-message-content-error'
              : 'conversation-message-content-hint'
          }
          onChange={(event) => updateContent(event.target.value)}
        />
      </FormField>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">
          {content.trim().length.toLocaleString()} /{' '}
          {MESSAGE_CONTENT_MAX_LENGTH.toLocaleString()}
          {pending && !isSubmitting
            ? ' - Your message was not confirmed as sent. Retrying reuses the same submission safely.'
            : ''}
        </p>
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {buttonLabel}
        </button>
      </div>
    </form>
  )
}
