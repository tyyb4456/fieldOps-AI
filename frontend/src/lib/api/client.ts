import { ApiError, parseErrorResponse } from './errors.ts'

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'

export type QueryValue = string | number | boolean | null | undefined

export type ResponseType = 'auto' | 'json' | 'text' | 'none'

export interface ApiRequestOptions {
  method?: HttpMethod
  query?: Record<string, QueryValue>
  json?: unknown
  formData?: FormData
  headers?: HeadersInit
  signal?: AbortSignal
  responseType?: ResponseType
  authenticated?: boolean
}

export interface ApiClientOptions {
  baseUrl: string
  getToken: () => Promise<string | null> | string | null
  fetchImpl?: typeof fetch
}

function buildUrl(
  baseUrl: string,
  path: string,
  query: Record<string, QueryValue> | undefined,
): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const url = new URL(`${baseUrl}${normalizedPath}`)

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === null || value === undefined) {
        continue
      }
      url.searchParams.set(key, String(value))
    }
  }

  return url.toString()
}

async function parseSuccessResponse<T>(
  response: Response,
  responseType: ResponseType,
): Promise<T> {
  if (
    responseType === 'none' ||
    response.status === 204 ||
    response.status === 205
  ) {
    return undefined as T
  }

  const contentType = response.headers.get('content-type') ?? ''
  const isJson = contentType.toLowerCase().includes('application/json')
  const shouldReadJson =
    responseType === 'json' || (responseType === 'auto' && isJson)

  if (shouldReadJson) {
    let text: string
    try {
      text = await response.text()
    } catch (caught) {
      throw new ApiError(
        response.status,
        'invalid_response',
        'The API returned an unreadable response.',
        {
          requestId: response.headers.get('x-request-id'),
          cause: caught,
        },
      )
    }

    if (!text.trim()) {
      return undefined as T
    }

    try {
      return JSON.parse(text) as T
    } catch (caught) {
      throw new ApiError(
        response.status,
        'invalid_response',
        'The API returned an invalid JSON response.',
        {
          requestId: response.headers.get('x-request-id'),
          cause: caught,
        },
      )
    }
  }

  const text = await response.text()
  if (!text.trim()) {
    return undefined as T
  }
  return text as T
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    (error as { name?: unknown }).name === 'AbortError'
  )
}

export class ApiClient {
  private readonly baseUrl: string
  private readonly getToken: ApiClientOptions['getToken']
  private readonly fetchImpl: typeof fetch

  constructor({ baseUrl, getToken, fetchImpl }: ApiClientOptions) {
    this.baseUrl = baseUrl.replace(/\/+$/, '')
    this.getToken = getToken
    this.fetchImpl = fetchImpl ?? globalThis.fetch.bind(globalThis)
  }

  async request<T>(
    path: string,
    options: ApiRequestOptions = {},
  ): Promise<T> {
    const {
      method = 'GET',
      query,
      json,
      formData,
      headers: extraHeaders,
      signal,
      responseType = 'auto',
      authenticated = true,
    } = options

    if (json !== undefined && formData !== undefined) {
      throw new Error('A request cannot send both JSON and multipart bodies.')
    }

    const headers = new Headers(extraHeaders)
    headers.set('Accept', 'application/json')

    if (authenticated) {
      let token: string | null
      try {
        token = await this.getToken()
      } catch (caught) {
        throw new ApiError(
          0,
          'token_unavailable',
          'Unable to obtain an authentication token. Please sign in again.',
          { cause: caught },
        )
      }

      if (!token) {
        throw new ApiError(
          401,
          'token_missing',
          'Unable to obtain a Clerk session token.',
        )
      }

      headers.set('Authorization', `Bearer ${token}`)
    }

    let body: BodyInit | undefined
    if (json !== undefined) {
      headers.set('Content-Type', 'application/json')
      body = JSON.stringify(json)
    } else if (formData !== undefined) {
      body = formData
    }

    let response: Response
    try {
      response = await this.fetchImpl(
        buildUrl(this.baseUrl, path, query),
        {
          method,
          headers,
          body,
          signal,
        },
      )
    } catch (caught) {
      if (isAbortError(caught)) {
        throw caught
      }
      throw new ApiError(
        0,
        'network_error',
        'Unable to reach the FieldOps API. Check your connection and try again.',
        { cause: caught },
      )
    }

    if (!response.ok) {
      throw await parseErrorResponse(response)
    }

    return parseSuccessResponse<T>(response, responseType)
  }

  get<T>(path: string, options?: Omit<ApiRequestOptions, 'method'>) {
    return this.request<T>(path, { ...options, method: 'GET' })
  }

  post<T>(path: string, options?: Omit<ApiRequestOptions, 'method'>) {
    return this.request<T>(path, { ...options, method: 'POST' })
  }

  patch<T>(path: string, options?: Omit<ApiRequestOptions, 'method'>) {
    return this.request<T>(path, { ...options, method: 'PATCH' })
  }

  put<T>(path: string, options?: Omit<ApiRequestOptions, 'method'>) {
    return this.request<T>(path, { ...options, method: 'PUT' })
  }

  delete<T>(path: string, options?: Omit<ApiRequestOptions, 'method'>) {
    return this.request<T>(path, { ...options, method: 'DELETE' })
  }
}
