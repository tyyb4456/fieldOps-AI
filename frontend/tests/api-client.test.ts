import assert from 'node:assert/strict'
import test from 'node:test'
import { ApiClient } from '../src/lib/api/client.ts'
import { ApiError } from '../src/lib/api/errors.ts'

function jsonResponse(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json',
      ...headers,
    },
  })
}

function createClient(
  fetchImpl: typeof fetch,
  getToken: () => Promise<string | null> | string | null = () =>
    'session-token',
) {
  return new ApiClient({
    baseUrl: 'https://api.example.com',
    getToken,
    fetchImpl,
  })
}

test('authenticated requests include the Clerk Bearer token', async () => {
  let authorization: string | null = null
  let requestedUrl = ''

  const client = createClient(async (input, init) => {
    requestedUrl = String(input)
    authorization = new Headers(init?.headers).get('authorization')
    return jsonResponse({ id: 'user-1' })
  })

  await client.get('/api/v1/users/me')

  assert.equal(authorization, 'Bearer session-token')
  assert.equal(requestedUrl, 'https://api.example.com/api/v1/users/me')
})

test('query parameters are serialized and null values are skipped', async () => {
  let requestedUrl = ''

  const client = createClient(async (input) => {
    requestedUrl = String(input)
    return jsonResponse({ items: [] })
  })

  await client.get('/api/v1/work-orders', {
    query: { status: 'assigned', limit: 10, offset: null },
  })

  const url = new URL(requestedUrl)
  assert.equal(url.searchParams.get('status'), 'assigned')
  assert.equal(url.searchParams.get('limit'), '10')
  assert.equal(url.searchParams.has('offset'), false)
})

test('a missing token fails before the request is sent', async () => {
  let called = false
  const client = createClient(
    async () => {
      called = true
      return jsonResponse({})
    },
    () => null,
  )

  await assert.rejects(
    () => client.get('/api/v1/users/me'),
    (error: unknown) =>
      error instanceof ApiError &&
      error.status === 401 &&
      error.code === 'token_missing',
  )
  assert.equal(called, false)
})

test('token acquisition failure surfaces as a typed error', async () => {
  let called = false
  const client = createClient(
    async () => {
      called = true
      return jsonResponse({})
    },
    () => {
      throw new Error('Clerk is unavailable')
    },
  )

  await assert.rejects(
    () => client.get('/api/v1/users/me'),
    (error: unknown) =>
      error instanceof ApiError &&
      error.status === 0 &&
      error.code === 'token_unavailable',
  )
  assert.equal(called, false)
})

test('401 responses preserve the backend error envelope', async () => {
  const client = createClient(async () =>
    jsonResponse(
      {
        error: {
          code: 'unauthenticated',
          message: 'Authentication credentials are invalid or missing.',
        },
      },
      401,
      { 'x-request-id': 'request-401' },
    ),
  )

  await assert.rejects(
    () => client.get('/api/v1/users/me'),
    (error: unknown) =>
      error instanceof ApiError &&
      error.status === 401 &&
      error.code === 'unauthenticated' &&
      error.requestId === 'request-401',
  )
})

test('403 responses preserve the backend error envelope', async () => {
  const client = createClient(async () =>
    jsonResponse(
      {
        error: {
          code: 'forbidden',
          message: 'You do not have permission to perform this action.',
        },
      },
      403,
    ),
  )

  await assert.rejects(
    () => client.get('/api/v1/admin/documents'),
    (error: unknown) =>
      error instanceof ApiError &&
      error.status === 403 &&
      error.code === 'forbidden',
  )
})

test('non-JSON error bodies fall back to a safe message', async () => {
  const client = createClient(
    async () =>
      new Response('<html>Bad gateway</html>', {
        status: 502,
        statusText: 'Bad Gateway',
        headers: { 'content-type': 'text/html' },
      }),
  )

  await assert.rejects(
    () => client.get('/api/v1/users/me'),
    (error: unknown) =>
      error instanceof ApiError &&
      error.status === 502 &&
      error.code === 'request_failed' &&
      error.message === 'Bad Gateway',
  )
})

test('204 responses return undefined', async () => {
  const client = createClient(
    async () => new Response(null, { status: 204 }),
  )

  const result = await client.delete('/api/v1/customers/me/equipment/1')
  assert.equal(result, undefined)
})

test('empty JSON responses return undefined', async () => {
  const client = createClient(
    async () =>
      new Response('', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
  )

  const result = await client.get('/api/v1/users/me')
  assert.equal(result, undefined)
})

test('invalid JSON success responses are reported as API errors', async () => {
  const client = createClient(
    async () =>
      new Response('{not-json', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
  )

  await assert.rejects(
    () => client.get('/api/v1/users/me'),
    (error: unknown) =>
      error instanceof ApiError &&
      error.status === 200 &&
      error.code === 'invalid_response',
  )
})

test('JSON requests set the content type and body', async () => {
  let contentType: string | null = null
  let body: BodyInit | null | undefined = null

  const client = createClient(async (_input, init) => {
    contentType = new Headers(init?.headers).get('content-type')
    body = init?.body
    return jsonResponse({ id: 'complaint-1' }, 201)
  })

  await client.post('/api/v1/customers/me/complaints', {
    json: { description: 'The inverter stopped working.' },
  })

  assert.equal(contentType, 'application/json')
  assert.equal(
    body,
    JSON.stringify({ description: 'The inverter stopped working.' }),
  )
})

test('multipart requests do not set a JSON content type', async () => {
  let contentType: string | null = null
  let body: BodyInit | null | undefined = null

  const client = createClient(async (_input, init) => {
    contentType = new Headers(init?.headers).get('content-type')
    body = init?.body
    return jsonResponse({ id: 'document-1' }, 202)
  })

  const formData = new FormData()
  formData.set('manufacturer', 'Solis')
  formData.set('file', new Blob(['pdf']), 'manual.pdf')

  await client.post('/api/v1/admin/documents', { formData })

  assert.equal(contentType, null)
  assert.equal(body, formData)
})

test('network failures are reported without retrying non-idempotent calls', async () => {
  let calls = 0
  const client = createClient(async () => {
    calls += 1
    throw new TypeError('Failed to fetch')
  })

  await assert.rejects(
    () =>
      client.post('/api/v1/customers/me/complaints', {
        json: { description: 'A valid description.' },
      }),
    (error: unknown) =>
      error instanceof ApiError &&
      error.status === 0 &&
      error.code === 'network_error',
  )
  assert.equal(calls, 1)
})

test('abort errors are forwarded unchanged', async () => {
  const abortError = new DOMException('Aborted', 'AbortError')
  const client = createClient(async () => {
    throw abortError
  })

  await assert.rejects(
    () => client.get('/api/v1/users/me'),
    (error: unknown) => error === abortError,
  )
})
