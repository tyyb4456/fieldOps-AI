export interface ApiErrorDetails {
  code: string
  message: string
  details?: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: unknown
  readonly requestId: string | null

  constructor(
    status: number,
    code: string,
    message: string,
    options: {
      details?: unknown
      requestId?: string | null
      cause?: unknown
    } = {},
  ) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause })
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = options.details
    this.requestId = options.requestId ?? null
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

export function isUnauthorizedError(error: unknown): error is ApiError {
  return isApiError(error) && error.status === 401
}

export function isForbiddenError(error: unknown): error is ApiError {
  return isApiError(error) && error.status === 403
}

export function isNotFoundError(error: unknown): error is ApiError {
  return isApiError(error) && error.status === 404
}

export function isAbortError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    (error as { name?: unknown }).name === 'AbortError'
  )
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (!isApiError(error)) {
    return fallback
  }

  if (error.status === 401 || error.code === 'token_missing') {
    return 'Your session has expired. Please sign in again.'
  }

  if (error.status === 403) {
    return error.message || 'You do not have permission to do that.'
  }

  if (error.status === 404) {
    return error.message || 'The requested record was not found.'
  }

  if (error.code === 'network_error') {
    return error.message
  }

  if (error.code === 'invalid_response') {
    return 'The API returned a response this page could not read. Please try again.'
  }

  return error.message || fallback
}

function readValidationDetail(
  detail: unknown,
): { field: string; message: string } | null {
  if (!isRecord(detail)) {
    return null
  }

  const message =
    typeof detail.msg === 'string'
      ? detail.msg
      : typeof detail.message === 'string'
        ? detail.message
        : null

  if (message === null) {
    return null
  }

  const location = Array.isArray(detail.loc)
    ? [...detail.loc].reverse().find((part) => typeof part === 'string')
    : null

  return {
    field: typeof location === 'string' ? location : '_form',
    message,
  }
}

export function fieldErrorsFromApiError(
  error: unknown,
): Record<string, string> {
  if (
    !isApiError(error) ||
    error.code !== 'validation_error' ||
    !Array.isArray(error.details)
  ) {
    return {}
  }

  const fieldErrors: Record<string, string> = {}
  for (const detail of error.details) {
    const parsed = readValidationDetail(detail)
    if (parsed !== null && fieldErrors[parsed.field] === undefined) {
      fieldErrors[parsed.field] = parsed.message
    }
  }

  return fieldErrors
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function parseApiErrorBody(payload: unknown): ApiErrorDetails | null {
  if (!isRecord(payload) || !isRecord(payload.error)) {
    return null
  }

  const { code, message, details } = payload.error
  if (typeof code !== 'string' || typeof message !== 'string') {
    return null
  }

  return { code, message, details }
}

export async function parseErrorResponse(response: Response): Promise<ApiError> {
  const requestId = response.headers.get('x-request-id')
  const fallbackMessage =
    response.statusText.trim() ||
    `The API rejected this request with status ${response.status}.`

  let text = ''
  try {
    text = await response.text()
  } catch {
    text = ''
  }

  let parsed: unknown = null
  if (text.trim()) {
    try {
      parsed = JSON.parse(text) as unknown
    } catch {
      parsed = null
    }
  }

  const details = parseApiErrorBody(parsed)
  if (details !== null) {
    return new ApiError(response.status, details.code, details.message, {
      details: details.details,
      requestId,
    })
  }

  return new ApiError(response.status, 'request_failed', fallbackMessage, {
    requestId,
  })
}
