import './helpers/dom.ts'
import React from 'react'
import assert from 'node:assert/strict'
import test, { afterEach } from 'node:test'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { ComplaintDetailPage } from '../src/features/complaints/pages/ComplaintDetailPage.tsx'
import type { Complaint } from '../src/features/complaints/types.ts'
import { PendingMessagesProvider } from '../src/features/conversations/PendingMessagesProvider.tsx'
import { usePendingMessages } from '../src/features/conversations/pending-messages-context.ts'
import type {
  Conversation,
  Message,
} from '../src/features/conversations/types.ts'
import { validateMessageForm } from '../src/features/conversations/validation.ts'
import {
  createTestClient,
  errorResponse,
  jsonResponse,
  requestBody,
  renderRoute,
  type FetchHandler,
  type RecordedRequest,
} from './helpers/customer-test-utils.tsx'

const COMPLAINT_ID = 'complaint-1'
const COMPLAINT_PATH = `/api/v1/customers/me/complaints/${COMPLAINT_ID}`
const CONVERSATIONS_PATH = `${COMPLAINT_PATH}/conversations`
const MESSAGE_PATH_PATTERN =
  /^\/api\/v1\/customers\/me\/conversations\/([^/]+)\/messages$/

afterEach(() => {
  cleanup()
})

function complaint(overrides: Partial<Complaint> = {}): Complaint {
  return {
    id: COMPLAINT_ID,
    customer_id: 'customer-1',
    equipment_id: null,
    description: 'The inverter stopped producing power after sunrise.',
    reported_symptoms: [],
    reported_error_code: 'E-05',
    channel: 'web',
    status: 'received',
    priority: 'normal',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function conversation(
  id: string,
  overrides: Partial<Conversation> = {},
): Conversation {
  return {
    id,
    complaint_id: COMPLAINT_ID,
    channel: 'web',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function message(id: string, overrides: Partial<Message> = {}): Message {
  return {
    id,
    conversation_id: 'conversation-1',
    sender_type: 'customer',
    content: 'A message',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function paginate<T>(items: readonly T[], url: URL) {
  const limitParam = url.searchParams.get('limit')
  const offsetParam = url.searchParams.get('offset')
  const limit = limitParam === null ? items.length : Number(limitParam)
  const offset = offsetParam === null ? 0 : Number(offsetParam)

  return {
    items: items.slice(offset, offset + limit),
    total: items.length,
    limit,
    offset,
  }
}

function method(request: RecordedRequest): string {
  return request.init.method ?? 'GET'
}

function idempotencyKey(request: RecordedRequest): string | null {
  return new Headers(request.init.headers).get('Idempotency-Key')
}

function conversationOption(id: string): HTMLElement {
  return screen.getByTestId(`conversation-option-${id}`)
}

function messageRequests(
  requests: readonly RecordedRequest[],
  conversationId: string,
): RecordedRequest[] {
  return requests.filter(
    (request) =>
      request.url.pathname ===
      `/api/v1/customers/me/conversations/${conversationId}/messages`,
  )
}

interface ApiOptions {
  conversations: Conversation[]
  messages?: Record<string, Message[]>
  onConversationList?: (request: RecordedRequest) => Response
  onMessagesList?: (
    request: RecordedRequest,
    conversationId: string,
  ) => Response | null
  onPost?: (
    request: RecordedRequest,
    conversationId: string,
  ) => Response | Promise<Response>
}

function apiHandler(options: ApiOptions): FetchHandler {
  return (request) => {
    if (request.url.pathname === COMPLAINT_PATH) {
      return jsonResponse(complaint())
    }

    if (request.url.pathname === CONVERSATIONS_PATH) {
      if (options.onConversationList) {
        return options.onConversationList(request)
      }
      return jsonResponse(
        paginate(options.conversations, request.url),
      )
    }

    const match = request.url.pathname.match(MESSAGE_PATH_PATTERN)
    if (match) {
      const conversationId = decodeURIComponent(match[1] ?? '')
      if (method(request) === 'POST') {
        if (!options.onPost) {
          return errorResponse(500, 'unexpected', 'Unexpected POST')
        }
        return options.onPost(request, conversationId)
      }

      if (options.onMessagesList) {
        const custom = options.onMessagesList(request, conversationId)
        if (custom !== null) {
          return custom
        }
      }

      return jsonResponse(
        paginate(
          options.messages?.[conversationId] ?? [],
          request.url,
        ),
      )
    }

    return errorResponse(404, 'not_found', 'Unexpected request')
  }
}

function renderComplaint(client: ReturnType<typeof createTestClient>) {
  return renderRoute(client, <ComplaintDetailPage />, {
    initialEntry: `/customer/complaints/${COMPLAINT_ID}`,
    path: '/customer/complaints/:complaintId',
  })
}

function PendingKeyHarness() {
  const { pendingFor, savePending, clearPending } = usePendingMessages()
  const pending = pendingFor('conversation-1')

  return (
    <div>
      <span data-testid="pending-key">{pending?.key ?? 'none'}</span>
      <button
        type="button"
        onClick={() =>
          savePending('conversation-1', {
            content: 'Older pending message',
            key: 'older-key',
          })
        }
      >
        Save older pending
      </button>
      <button
        type="button"
        onClick={() =>
          savePending('conversation-1', {
            content: 'Newer pending message',
            key: 'newer-key',
          })
        }
      >
        Save newer pending
      </button>
      <button
        type="button"
        onClick={() => clearPending('conversation-1', 'older-key')}
      >
        Clear older pending
      </button>
      <button
        type="button"
        onClick={() => clearPending('conversation-1', 'newer-key')}
      >
        Clear newer pending
      </button>
    </div>
  )
}

test('complaint detail lists multiple conversations and switches message history', async () => {
  const newest = conversation('conversation-2', {
    created_at: '2026-01-02T00:00:00Z',
  })
  const older = conversation('conversation-1', {
    created_at: '2026-01-01T00:00:00Z',
  })
  const requests: RecordedRequest[] = []
  const client = createTestClient(
    apiHandler({
      conversations: [newest, older],
      messages: {
        'conversation-2': [
          message('message-2', {
            conversation_id: 'conversation-2',
            content: 'Second conversation message',
          }),
        ],
        'conversation-1': [
          message('message-1', {
            conversation_id: 'conversation-1',
            content: 'First conversation message',
          }),
        ],
      },
    }),
    requests,
  )

  renderComplaint(client)

  assert.ok(await screen.findByText('Second conversation message'))
  assert.ok(conversationOption('conversation-1'))
  assert.ok(conversationOption('conversation-2'))
  assert.equal(
    conversationOption('conversation-2').getAttribute('aria-pressed'),
    'true',
  )

  fireEvent.click(conversationOption('conversation-1'))

  assert.ok(await screen.findByText('First conversation message'))
  assert.equal(screen.queryByText('Second conversation message'), null)
  assert.equal(
    conversationOption('conversation-1').getAttribute('aria-pressed'),
    'true',
  )

  assert.equal(
    requests.some((request) =>
      request.url.pathname.startsWith('/api/v1/conversations'),
    ),
    false,
  )
})

test('complaint detail shows the legacy-compatible empty conversation state', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient(
    apiHandler({ conversations: [] }),
    requests,
  )

  renderComplaint(client)

  assert.ok(await screen.findByText('No conversation available'))
  assert.ok(
    screen.getByText(
      'The inverter stopped producing power after sunrise.',
    ),
  )
  assert.equal(
    requests.some((request) =>
      MESSAGE_PATH_PATTERN.test(request.url.pathname),
    ),
    false,
  )
})

test('conversation loading failures can be retried', async () => {
  let shouldFail = true
  const requests: RecordedRequest[] = []
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      onConversationList: () =>
        shouldFail
          ? errorResponse(
              503,
              'unavailable',
              'Conversations are temporarily unavailable',
            )
          : jsonResponse({
              items: [conversation('conversation-1')],
              total: 1,
              limit: 100,
              offset: 0,
            }),
    }),
    requests,
  )

  renderComplaint(client)

  assert.ok(
    await screen.findByText('Conversations are temporarily unavailable'),
  )

  shouldFail = false
  fireEvent.click(
    screen.getByRole('button', { name: 'Retry conversations' }),
  )

  assert.ok(await screen.findByTestId('conversation-option-conversation-1'))
})

test('message loading failures can be retried without breaking the complaint', async () => {
  let shouldFail = true
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {
        'conversation-1': [
          message('message-1', { content: 'Recovered message' }),
        ],
      },
      onMessagesList: () =>
        shouldFail
          ? errorResponse(
              503,
              'unavailable',
              'Messages are temporarily unavailable',
            )
          : null,
    }),
  )

  renderComplaint(client)

  assert.ok(
    await screen.findByText('Messages are temporarily unavailable'),
  )
  assert.ok(screen.getByText('Complaint details'))

  shouldFail = false
  fireEvent.click(screen.getByRole('button', { name: 'Retry messages' }))

  assert.ok(await screen.findByText('Recovered message'))
})

test('messages render in backend order with distinct sender labels', async () => {
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {
        'conversation-1': [
          message('message-1', {
            sender_type: 'customer',
            content: 'Customer question',
            created_at: '2026-01-01T10:00:00Z',
          }),
          message('message-2', {
            sender_type: 'staff',
            content: 'Staff reply',
            created_at: '2026-01-01T10:05:00Z',
          }),
        ],
      },
    }),
  )

  renderComplaint(client)

  assert.ok(await screen.findByText('Staff reply'))
  const rendered = screen.getAllByTestId('conversation-message')

  assert.equal(rendered.length, 2)
  assert.match(rendered[0]?.textContent ?? '', /Customer question/)
  assert.match(rendered[1]?.textContent ?? '', /Staff reply/)
  assert.match(rendered[0]?.textContent ?? '', /You/)
  assert.match(rendered[1]?.textContent ?? '', /Service team/)
  assert.equal(rendered[0]?.getAttribute('data-sender'), 'customer')
  assert.equal(rendered[1]?.getAttribute('data-sender'), 'staff')
})

test('older message pagination preserves order, avoids duplicates, and keeps loaded messages on failure', async () => {
  const allMessages = Array.from({ length: 60 }, (_, index) =>
    message(`message-${String(index).padStart(2, '0')}`, {
      content: `Message ${index}`,
      created_at: new Date(
        Date.UTC(2026, 0, 1, 0, 0, index),
      ).toISOString(),
    }),
  )
  let failOlder = true
  let offsetZeroLoads = 0
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: { 'conversation-1': allMessages },
      onMessagesList: (request) => {
        const offset = Number(request.url.searchParams.get('offset'))
        if (offset !== 0) {
          return null
        }
        offsetZeroLoads += 1
        if (offsetZeroLoads >= 2 && failOlder) {
          return errorResponse(
            503,
            'unavailable',
            'Older messages are temporarily unavailable',
          )
        }
        return null
      },
    }),
  )

  renderComplaint(client)

  assert.ok(await screen.findByText('Message 59'))
  assert.equal(
    screen.getAllByTestId('conversation-message').length,
    50,
  )

  fireEvent.click(
    screen.getByRole('button', { name: 'Load older messages' }),
  )

  assert.ok(
    await screen.findByText(
      'Older messages are temporarily unavailable',
    ),
  )
  assert.equal(
    screen.getAllByTestId('conversation-message').length,
    50,
  )

  failOlder = false
  fireEvent.click(
    screen.getByRole('button', { name: 'Retry older messages' }),
  )

  assert.ok(await screen.findByText('Message 0'))
  await waitFor(() => {
    assert.equal(
      screen.getAllByTestId('conversation-message').length,
      60,
    )
  })

  const rendered = screen
    .getAllByTestId('conversation-message')
    .map((node) => node.textContent ?? '')
  assert.equal(new Set(rendered).size, 60)
  assert.equal(
    screen.queryByRole('button', { name: 'Load older messages' }),
    null,
  )
})

test('message validation trims content and enforces the backend limit', () => {
  const blank = validateMessageForm({ content: '   ' })
  assert.equal(blank.isValid, false)
  assert.ok(blank.errors.content)

  const tooLong = validateMessageForm({
    content: 'x'.repeat(10001),
  })
  assert.equal(tooLong.isValid, false)
  assert.ok(tooLong.errors.content)

  const valid = validateMessageForm({ content: '  Hello team  ' })
  assert.equal(valid.isValid, true)
  assert.deepEqual(valid.payload, { content: 'Hello team' })
})

test('blank and whitespace-only messages are rejected without a request', async () => {
  const requests: RecordedRequest[] = []
  let postCount = 0
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {},
      onPost: () => {
        postCount += 1
        return errorResponse(500, 'unexpected', 'Should not submit')
      },
    }),
    requests,
  )

  renderComplaint(client)

  const textarea = await screen.findByLabelText('Message')
  assert.equal(textarea.getAttribute('maxlength'), '10000')

  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
  assert.ok(
    await screen.findByText('Write a message before sending.'),
  )

  fireEvent.change(textarea, { target: { value: '     ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  await waitFor(() => {
    assert.equal(postCount, 0)
  })
  assert.equal(
    messageRequests(requests, 'conversation-1').filter(
      (request) => method(request) === 'POST',
    ).length,
    0,
  )
})

test('a valid web message is submitted once with trimming, a key, and a 201 response', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {},
      onPost: () =>
        jsonResponse(
          message('message-new', {
            content: 'Hello service team',
            created_at: '2026-01-01T11:00:00Z',
          }),
          201,
        ),
    }),
    requests,
  )

  renderComplaint(client)

  assert.ok(
    await screen.findByText('No messages in this conversation yet.'),
  )

  const textarea = screen.getByLabelText('Message')
  fireEvent.change(textarea, {
    target: { value: '   Hello service team   ' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  assert.ok(await screen.findByText('Hello service team'))
  await waitFor(() => {
    assert.equal((textarea as HTMLTextAreaElement).value, '')
  })

  const posts = messageRequests(requests, 'conversation-1').filter(
    (request) => method(request) === 'POST',
  )
  assert.equal(posts.length, 1)
  assert.deepEqual(requestBody(posts[0]!), {
    content: 'Hello service team',
  })
  assert.ok(idempotencyKey(posts[0]!))
  assert.equal(
    screen.getAllByTestId('conversation-message').length,
    1,
  )
  assert.equal(screen.queryByText('Service team'), null)
  assert.equal(screen.queryByText('FieldOps assistant'), null)
  assert.equal(
    requests.some((request) =>
      request.url.pathname.startsWith('/api/v1/conversations'),
    ),
    false,
  )
})

test('a 200 idempotent replay is treated as a successful submission', async () => {
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {},
      onPost: () =>
        jsonResponse(
          message('message-replayed', {
            content: 'Replayed message',
          }),
          200,
        ),
    }),
  )

  renderComplaint(client)

  const textarea = await screen.findByLabelText('Message')
  fireEvent.change(textarea, {
    target: { value: 'Replayed message' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  assert.ok(await screen.findByText('Replayed message'))
  await waitFor(() => {
    assert.equal((textarea as HTMLTextAreaElement).value, '')
  })
  assert.equal(
    screen.getAllByTestId('conversation-message').length,
    1,
  )
})

test('duplicate submission is prevented while a request is pending', async () => {
  const requests: RecordedRequest[] = []
  let resolvePost: (response: Response) => void = () => undefined
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {},
      onPost: () =>
        new Promise<Response>((resolve) => {
          resolvePost = resolve
        }),
    }),
    requests,
  )

  renderComplaint(client)

  const textarea = await screen.findByLabelText('Message')
  fireEvent.change(textarea, { target: { value: 'Pending message' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  await waitFor(() => {
    assert.equal(
      messageRequests(requests, 'conversation-1').filter(
        (request) => method(request) === 'POST',
      ).length,
      1,
    )
  })

  fireEvent.click(screen.getByRole('button', { name: 'Sending...' }))
  assert.equal(
    messageRequests(requests, 'conversation-1').filter(
      (request) => method(request) === 'POST',
    ).length,
    1,
  )

  resolvePost(
    jsonResponse(
      message('message-pending', { content: 'Pending message' }),
      201,
    ),
  )

  assert.ok(await screen.findByText('Pending message'))
})

test('an uncertain network failure preserves the message and reuses the same key on retry', async () => {
  const requests: RecordedRequest[] = []
  let attempts = 0
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {},
      onPost: () => {
        attempts += 1
        if (attempts === 1) {
          throw new TypeError('Network connection lost')
        }
        return jsonResponse(
          message('message-retried', { content: 'Please help' }),
          201,
        )
      },
    }),
    requests,
  )

  renderComplaint(client)

  const textarea = await screen.findByLabelText('Message')
  fireEvent.change(textarea, { target: { value: 'Please help' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  assert.ok(
    await screen.findByText(
      /could not confirm whether your message was sent/i,
    ),
  )
  assert.equal((textarea as HTMLTextAreaElement).value, 'Please help')
  assert.equal(
    screen.queryAllByTestId('conversation-message').length,
    0,
  )

  fireEvent.click(
    screen.getByRole('button', { name: 'Retry sending' }),
  )

  await waitFor(() => {
    const rendered = screen.getAllByTestId('conversation-message')
    assert.equal(rendered.length, 1)
    assert.match(rendered[0]?.textContent ?? '', /Please help/)
  })
  await waitFor(() => {
    assert.equal((textarea as HTMLTextAreaElement).value, '')
  })

  const posts = messageRequests(requests, 'conversation-1').filter(
    (request) => method(request) === 'POST',
  )
  assert.equal(posts.length, 2)
  assert.ok(idempotencyKey(posts[0]!))
  assert.equal(idempotencyKey(posts[0]), idempotencyKey(posts[1]))
  assert.deepEqual(requestBody(posts[1]!), {
    content: 'Please help',
  })
})

test('an uncertain submission survives switching conversations and retries with the same key', async () => {
  const newest = conversation('conversation-2', {
    created_at: '2026-01-02T00:00:00Z',
  })
  const older = conversation('conversation-1', {
    created_at: '2026-01-01T00:00:00Z',
  })
  const requests: RecordedRequest[] = []
  let attempts = 0
  const client = createTestClient(
    apiHandler({
      conversations: [newest, older],
      messages: {
        'conversation-2': [],
        'conversation-1': [
          message('message-1', {
            conversation_id: 'conversation-1',
            content: 'Older conversation message',
          }),
        ],
      },
      onPost: (_request, conversationId) => {
        assert.equal(conversationId, 'conversation-2')
        attempts += 1
        if (attempts === 1) {
          throw new TypeError('Network connection lost')
        }
        return jsonResponse(
          message('message-recovered', {
            conversation_id: 'conversation-2',
            content: 'Please recover this',
          }),
          201,
        )
      },
    }),
    requests,
  )

  renderComplaint(client)

  assert.ok(
    await screen.findByText('No messages in this conversation yet.'),
  )
  const textarea = screen.getByLabelText('Message')
  fireEvent.change(textarea, {
    target: { value: 'Please recover this' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  assert.ok(
    await screen.findByText(
      /could not confirm whether your message was sent/i,
    ),
  )
  assert.equal(
    (textarea as HTMLTextAreaElement).value,
    'Please recover this',
  )

  fireEvent.click(conversationOption('conversation-1'))
  assert.ok(await screen.findByText('Older conversation message'))
  assert.equal(
    (screen.getByLabelText('Message') as HTMLTextAreaElement).value,
    '',
  )

  fireEvent.click(conversationOption('conversation-2'))
  const restoredTextarea = await screen.findByLabelText('Message')
  await waitFor(() => {
    assert.equal(
      (restoredTextarea as HTMLTextAreaElement).value,
      'Please recover this',
    )
  })
  fireEvent.click(
    screen.getByRole('button', { name: 'Retry sending' }),
  )

  await waitFor(() => {
    assert.equal(
      (restoredTextarea as HTMLTextAreaElement).value,
      '',
    )
  })

  const posts = messageRequests(requests, 'conversation-2').filter(
    (request) => method(request) === 'POST',
  )
  assert.equal(posts.length, 2)
  assert.ok(idempotencyKey(posts[0]!))
  assert.equal(idempotencyKey(posts[0]), idempotencyKey(posts[1]))
  assert.deepEqual(requestBody(posts[1]!), {
    content: 'Please recover this',
  })

  fireEvent.click(conversationOption('conversation-1'))
  assert.ok(await screen.findByText('Older conversation message'))
  fireEvent.click(conversationOption('conversation-2'))

  const confirmedTextarea = await screen.findByLabelText('Message')
  await waitFor(() => {
    assert.equal(
      (confirmedTextarea as HTMLTextAreaElement).value,
      '',
    )
  })
  assert.equal(
    screen.queryByRole('button', { name: 'Retry sending' }),
    null,
  )
})

test('editing a pending message does not reuse its previous idempotency key', async () => {
  const requests: RecordedRequest[] = []
  let attempts = 0
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {},
      onPost: (request) => {
        attempts += 1
        if (attempts === 1) {
          throw new TypeError('Network connection lost')
        }
        const body = requestBody(request) as { content: string }
        return jsonResponse(
          message('message-edited', { content: body.content }),
          201,
        )
      },
    }),
    requests,
  )

  renderComplaint(client)

  const textarea = await screen.findByLabelText('Message')
  fireEvent.change(textarea, {
    target: { value: 'Original pending message' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  assert.ok(
    await screen.findByText(
      /could not confirm whether your message was sent/i,
    ),
  )
  assert.ok(
    screen.getByRole('button', { name: 'Retry sending' }),
  )

  fireEvent.change(textarea, {
    target: { value: 'Edited pending message' },
  })
  await waitFor(() => {
    assert.ok(screen.getByRole('button', { name: 'Send message' }))
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  assert.ok(await screen.findByText('Edited pending message'))
  await waitFor(() => {
    assert.equal((textarea as HTMLTextAreaElement).value, '')
  })

  const posts = messageRequests(requests, 'conversation-1').filter(
    (request) => method(request) === 'POST',
  )
  assert.equal(posts.length, 2)
  assert.ok(idempotencyKey(posts[0]!))
  assert.notEqual(idempotencyKey(posts[0]), idempotencyKey(posts[1]))
  assert.deepEqual(requestBody(posts[1]!), {
    content: 'Edited pending message',
  })
})

test('a successful submission clears pending state and cannot be replayed', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {},
      onPost: () =>
        jsonResponse(
          message('message-once', { content: 'Sent once' }),
          201,
        ),
    }),
    requests,
  )

  renderComplaint(client)

  const textarea = await screen.findByLabelText('Message')
  fireEvent.change(textarea, { target: { value: 'Sent once' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  assert.ok(await screen.findByText('Sent once'))
  await waitFor(() => {
    assert.equal((textarea as HTMLTextAreaElement).value, '')
  })

  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  assert.ok(
    await screen.findByText('Write a message before sending.'),
  )
  assert.equal(
    messageRequests(requests, 'conversation-1').filter(
      (request) => method(request) === 'POST',
    ).length,
    1,
  )
  assert.equal(screen.queryByText('Retry sending'), null)
})

test('a new logical message receives a different idempotency key', async () => {
  const requests: RecordedRequest[] = []
  let submitted = 0
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {},
      onPost: (request) => {
        submitted += 1
        const body = requestBody(request) as { content: string }
        return jsonResponse(
          message(`message-${submitted}`, { content: body.content }),
          201,
        )
      },
    }),
    requests,
  )

  renderComplaint(client)

  const textarea = await screen.findByLabelText('Message')
  fireEvent.change(textarea, { target: { value: 'First message' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
  assert.ok(await screen.findByText('First message'))

  await waitFor(() => {
    assert.equal((textarea as HTMLTextAreaElement).value, '')
  })
  fireEvent.change(textarea, { target: { value: 'Second message' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
  assert.ok(await screen.findByText('Second message'))

  const posts = messageRequests(requests, 'conversation-1').filter(
    (request) => method(request) === 'POST',
  )
  assert.equal(posts.length, 2)
  assert.notEqual(idempotencyKey(posts[0]), idempotencyKey(posts[1]))
})

test('an idempotency conflict is surfaced without a silent retry', async () => {
  const requests: RecordedRequest[] = []
  let attempts = 0
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {},
      onPost: (request) => {
        attempts += 1
        if (attempts === 1) {
          return errorResponse(
            409,
            'idempotency_conflict',
            'Idempotency key was already used for a different message.',
          )
        }
        const body = requestBody(request) as { content: string }
        return jsonResponse(
          message('message-corrected', { content: body.content }),
          201,
        )
      },
    }),
    requests,
  )

  renderComplaint(client)

  const textarea = await screen.findByLabelText('Message')
  fireEvent.change(textarea, {
    target: { value: 'Conflicting message' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  assert.ok(
    await screen.findByText(
      /already used for different content/i,
    ),
  )
  const conflictPosts = messageRequests(
    requests,
    'conversation-1',
  ).filter((request) => method(request) === 'POST')
  assert.equal(conflictPosts.length, 1)
  assert.equal(
    (textarea as HTMLTextAreaElement).value,
    'Conflicting message',
  )
  assert.equal(
    screen.queryAllByTestId('conversation-message').length,
    0,
  )
  assert.ok(
    screen.getByRole('button', { name: 'Send message' }),
  )

  fireEvent.change(textarea, {
    target: { value: 'Corrected message' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  assert.ok(await screen.findByText('Corrected message'))
  await waitFor(() => {
    assert.equal((textarea as HTMLTextAreaElement).value, '')
  })

  const posts = messageRequests(requests, 'conversation-1').filter(
    (request) => method(request) === 'POST',
  )
  assert.equal(posts.length, 2)
  assert.ok(idempotencyKey(posts[0]!))
  assert.notEqual(idempotencyKey(posts[0]), idempotencyKey(posts[1]))
  assert.deepEqual(requestBody(posts[1]!), {
    content: 'Corrected message',
  })
})

test('a late response cannot clear a newer pending submission', () => {
  render(
    <PendingMessagesProvider>
      <PendingKeyHarness />
    </PendingMessagesProvider>,
  )

  fireEvent.click(
    screen.getByRole('button', { name: 'Save newer pending' }),
  )
  assert.equal(screen.getByTestId('pending-key').textContent, 'newer-key')

  fireEvent.click(
    screen.getByRole('button', { name: 'Clear older pending' }),
  )
  assert.equal(screen.getByTestId('pending-key').textContent, 'newer-key')

  fireEvent.click(
    screen.getByRole('button', { name: 'Clear newer pending' }),
  )
  assert.equal(screen.getByTestId('pending-key').textContent, 'none')
})

test('an unsupported channel submission error is explained clearly', async () => {
  const client = createTestClient(
    apiHandler({
      conversations: [conversation('conversation-1')],
      messages: {},
      onPost: () =>
        errorResponse(
          409,
          'unsupported_conversation_channel',
          'Customer messages are only supported on web conversations.',
        ),
    }),
  )

  renderComplaint(client)

  const textarea = await screen.findByLabelText('Message')
  fireEvent.change(textarea, { target: { value: 'Hello' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

  assert.ok(
    await screen.findByText(
      /Messages can only be sent through web conversations/i,
    ),
  )
  assert.equal(
    screen.queryAllByTestId('conversation-message').length,
    0,
  )
})

test('non-web conversations are read-only and cannot submit messages', async () => {
  const client = createTestClient(
    apiHandler({
      conversations: [
        conversation('conversation-1', { channel: 'whatsapp' }),
      ],
      messages: {
        'conversation-1': [
          message('message-1', {
            sender_type: 'staff',
            content: 'WhatsApp message history',
          }),
        ],
      },
    }),
  )

  renderComplaint(client)

  assert.ok(await screen.findByText('WhatsApp message history'))
  assert.ok(screen.getByText(/This conversation is read-only here/i))
  assert.ok(screen.getByText(/not supported in this application yet/i))
  assert.equal(screen.queryByLabelText('Message'), null)
  assert.equal(
    screen.queryByRole('button', { name: /Send message/i }),
    null,
  )
})
