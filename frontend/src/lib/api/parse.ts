import { ApiError } from './errors.ts'
import type { PaginatedResponse } from './types.ts'

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function invalidResponse(message: string): ApiError {
  return new ApiError(500, 'invalid_response', message)
}

export function requireString(value: unknown, field: string): string {
  if (typeof value !== 'string') {
    throw invalidResponse(`The API returned an invalid "${field}" field.`)
  }
  return value
}

export function requireBoolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') {
    throw invalidResponse(`The API returned an invalid "${field}" field.`)
  }
  return value
}

export function requireNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw invalidResponse(`The API returned an invalid "${field}" field.`)
  }
  return value
}

export function optionalString(
  value: unknown,
  field: string,
): string | null {
  if (value === null || value === undefined) {
    return null
  }
  return requireString(value, field)
}

export function requireArray(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) {
    throw invalidResponse(`The API returned an invalid "${field}" field.`)
  }
  return value
}

export function parsePaginatedResponse<T>(
  payload: unknown,
  parseItem: (item: unknown) => T,
  label: string,
): PaginatedResponse<T> {
  if (!isRecord(payload)) {
    throw invalidResponse(`The API returned an invalid ${label} list.`)
  }

  const items = requireArray(payload.items, 'items').map(parseItem)

  return {
    items,
    total: requireNumber(payload.total, 'total'),
    limit: requireNumber(payload.limit, 'limit'),
    offset: requireNumber(payload.offset, 'offset'),
  }
}
