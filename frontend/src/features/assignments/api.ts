import type { ApiClient } from '../../lib/api/client.ts'
import { ApiError } from '../../lib/api/errors.ts'
import {
  isRecord,
  optionalString,
  parsePaginatedResponse,
  requireString,
} from '../../lib/api/parse.ts'
import {
  isAssignmentStatus,
  type AssignmentStatus,
  type PaginatedResponse,
} from '../../lib/api/types.ts'
import type { Assignment, AssignmentListQuery } from './types'

export function parseAssignment(payload: unknown): Assignment {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid assignment response.',
    )
  }

  if (!isAssignmentStatus(payload.assignment_status)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid assignment status.',
    )
  }

  return {
    id: requireString(payload.id, 'id'),
    work_order_id: requireString(payload.work_order_id, 'work_order_id'),
    technician_id: requireString(payload.technician_id, 'technician_id'),
    assignment_status: payload.assignment_status,
    assigned_at: requireString(payload.assigned_at, 'assigned_at'),
    accepted_at: optionalString(payload.accepted_at, 'accepted_at'),
    rejected_at: optionalString(payload.rejected_at, 'rejected_at'),
  }
}

export function parseAssignmentList(
  payload: unknown,
): PaginatedResponse<Assignment> {
  return parsePaginatedResponse(payload, parseAssignment, 'assignment')
}

function toQuery(
  query: AssignmentListQuery,
): Record<string, string | number | undefined> {
  return {
    status: query.status,
    work_order_id: query.work_order_id,
    technician_id: query.technician_id,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function listAssignments(
  client: ApiClient,
  query: AssignmentListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<Assignment>> {
  const payload = await client.get<unknown>('/api/v1/assignments', {
    query: toQuery(query),
    signal,
  })
  return parseAssignmentList(payload)
}

export async function getAssignment(
  client: ApiClient,
  assignmentId: string,
  signal?: AbortSignal,
): Promise<Assignment> {
  const payload = await client.get<unknown>(
    `/api/v1/assignments/${encodeURIComponent(assignmentId)}`,
    { signal },
  )
  return parseAssignment(payload)
}

export async function acceptAssignment(
  client: ApiClient,
  assignmentId: string,
): Promise<Assignment> {
  const payload = await client.post<unknown>(
    `/api/v1/assignments/${encodeURIComponent(assignmentId)}/accept`,
  )
  return parseAssignment(payload)
}

export async function rejectAssignment(
  client: ApiClient,
  assignmentId: string,
): Promise<Assignment> {
  const payload = await client.post<unknown>(
    `/api/v1/assignments/${encodeURIComponent(assignmentId)}/reject`,
  )
  return parseAssignment(payload)
}

export type { AssignmentStatus }
