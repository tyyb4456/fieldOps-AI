import type { ApiClient } from '../../lib/api/client.ts'
import { ApiError } from '../../lib/api/errors.ts'
import {
  isRecord,
  optionalString,
  requireBoolean,
  requireString,
} from '../../lib/api/parse.ts'
import type {
  CustomerProfile,
  CustomerUpdateRequest,
} from './types'

export function parseCustomerProfile(payload: unknown): CustomerProfile {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid profile response.',
    )
  }

  return {
    id: requireString(payload.id, 'id'),
    full_name: requireString(payload.full_name, 'full_name'),
    email: optionalString(payload.email, 'email'),
    phone: optionalString(payload.phone, 'phone'),
    address: optionalString(payload.address, 'address'),
    preferred_language: optionalString(
      payload.preferred_language,
      'preferred_language',
    ),
    is_active: requireBoolean(payload.is_active, 'is_active'),
    created_at: requireString(payload.created_at, 'created_at'),
  }
}

export async function fetchCustomerProfile(
  client: ApiClient,
  signal?: AbortSignal,
): Promise<CustomerProfile> {
  const payload = await client.get<unknown>('/api/v1/customers/me', {
    signal,
  })
  return parseCustomerProfile(payload)
}

export async function updateCustomerProfile(
  client: ApiClient,
  data: CustomerUpdateRequest,
): Promise<CustomerProfile> {
  const payload = await client.patch<unknown>('/api/v1/customers/me', {
    json: data,
  })
  return parseCustomerProfile(payload)
}
