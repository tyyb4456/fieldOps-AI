import React from 'react'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import {
  MemoryRouter,
  Route,
  Routes,
} from 'react-router-dom'
import { ApiClientContext } from '../../src/lib/api/api-client-context.ts'
import { ApiClient } from '../../src/lib/api/client.ts'
import { LocationProbe } from './LocationProbe.tsx'

export interface RecordedRequest {
  url: URL
  init: RequestInit
}

export type FetchHandler = (
  request: RecordedRequest,
) => Response | Promise<Response>

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

export function emptyResponse(status = 204): Response {
  return new Response(null, { status })
}

export function errorResponse(
  status: number,
  code: string,
  message: string,
  details?: unknown,
): Response {
  return jsonResponse({ error: { code, message, details } }, status)
}

export function createTestClient(
  handler: FetchHandler,
  requests: RecordedRequest[] = [],
): ApiClient {
  return new ApiClient({
    baseUrl: 'https://api.example.com',
    getToken: () => 'test-token',
    fetchImpl: async (input, init) => {
      const request = {
        url: new URL(String(input)),
        init: init ?? {},
      }
      requests.push(request)
      return handler(request)
    },
  })
}

export function renderRoute(
  client: ApiClient,
  element: ReactElement,
  options: {
    initialEntry: string
    path: string
  },
) {
  return render(
    <ApiClientContext.Provider value={client}>
      <MemoryRouter initialEntries={[options.initialEntry]}>
        <Routes>
          <Route path={options.path} element={element} />
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </ApiClientContext.Provider>,
  )
}

export function requestsTo(
  requests: readonly RecordedRequest[],
  pathname: string,
): RecordedRequest[] {
  return requests.filter((request) => request.url.pathname === pathname)
}

export function requestBody(request: RecordedRequest): unknown {
  if (typeof request.init.body !== 'string') {
    return undefined
  }
  return JSON.parse(request.init.body) as unknown
}
