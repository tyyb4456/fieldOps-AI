import type { ApiClient } from '../../lib/api/client.ts'
import { ApiError } from '../../lib/api/errors.ts'
import {
  isRecord,
  optionalString,
  parsePaginatedResponse,
  requireArray,
  requireString,
} from '../../lib/api/parse.ts'
import {
  isComplaintChannel,
  isComplaintStatus,
  isPriority,
  type PaginatedResponse,
} from '../../lib/api/types.ts'
import type {
  Complaint,
  ComplaintCreateRequest,
  ComplaintListQuery,
} from './types'

export function parseComplaint(payload: unknown): Complaint {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid complaint response.',
    )
  }

  if (!isComplaintStatus(payload.status)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid complaint status.',
    )
  }

  if (!isPriority(payload.priority)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid complaint priority.',
    )
  }

  if (!isComplaintChannel(payload.channel)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid complaint channel.',
    )
  }

  return {
    id: requireString(payload.id, 'id'),
    customer_id: requireString(payload.customer_id, 'customer_id'),
    equipment_id: optionalString(payload.equipment_id, 'equipment_id'),
    description: requireString(payload.description, 'description'),
    reported_symptoms: requireArray(
      payload.reported_symptoms,
      'reported_symptoms',
    ),
    reported_error_code: optionalString(
      payload.reported_error_code,
      'reported_error_code',
    ),
    channel: payload.channel,
    status: payload.status,
    priority: payload.priority,
    created_at: requireString(payload.created_at, 'created_at'),
    updated_at: requireString(payload.updated_at, 'updated_at'),
  }
}

export function parseComplaintList(
  payload: unknown,
): PaginatedResponse<Complaint> {
  return parsePaginatedResponse(payload, parseComplaint, 'complaint')
}

function toQuery(
  query: ComplaintListQuery,
): Record<string, string | number | undefined> {
  return {
    status: query.status,
    equipment_id: query.equipment_id,
    created_from: query.created_from,
    created_to: query.created_to,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function listComplaints(
  client: ApiClient,
  query: ComplaintListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<Complaint>> {
  const payload = await client.get<unknown>(
    '/api/v1/customers/me/complaints',
    { query: toQuery(query), signal },
  )
  return parseComplaintList(payload)
}

export async function getComplaint(
  client: ApiClient,
  complaintId: string,
  signal?: AbortSignal,
): Promise<Complaint> {
  const payload = await client.get<unknown>(
    `/api/v1/customers/me/complaints/${encodeURIComponent(complaintId)}`,
    { signal },
  )
  return parseComplaint(payload)
}

export async function createComplaint(
  client: ApiClient,
  data: ComplaintCreateRequest,
): Promise<Complaint> {
  const payload = await client.post<unknown>(
    '/api/v1/customers/me/complaints',
    { json: data },
  )
  return parseComplaint(payload)
}
