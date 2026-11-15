import type { ApiClient } from '../../lib/api/client.ts'
import { ApiError } from '../../lib/api/errors.ts'
import {
  isRecord,
  optionalString,
  parsePaginatedResponse,
  requireString,
} from '../../lib/api/parse.ts'
import type { PaginatedResponse } from '../../lib/api/types.ts'
import type {
  Equipment,
  EquipmentCreateRequest,
  EquipmentListQuery,
  EquipmentUpdateRequest,
} from './types'

export function parseEquipment(payload: unknown): Equipment {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid equipment response.',
    )
  }

  return {
    id: requireString(payload.id, 'id'),
    customer_id: requireString(payload.customer_id, 'customer_id'),
    manufacturer: requireString(payload.manufacturer, 'manufacturer'),
    model: requireString(payload.model, 'model'),
    serial_number: optionalString(payload.serial_number, 'serial_number'),
    equipment_type: requireString(payload.equipment_type, 'equipment_type'),
    installation_date: optionalString(
      payload.installation_date,
      'installation_date',
    ),
    created_at: requireString(payload.created_at, 'created_at'),
  }
}

export function parseEquipmentList(
  payload: unknown,
): PaginatedResponse<Equipment> {
  return parsePaginatedResponse(payload, parseEquipment, 'equipment')
}

function toQuery(
  query: EquipmentListQuery,
): Record<string, string | number | undefined> {
  return {
    equipment_type: query.equipment_type,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function listEquipment(
  client: ApiClient,
  query: EquipmentListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<Equipment>> {
  const payload = await client.get<unknown>(
    '/api/v1/customers/me/equipment',
    { query: toQuery(query), signal },
  )
  return parseEquipmentList(payload)
}

export async function getEquipment(
  client: ApiClient,
  equipmentId: string,
  signal?: AbortSignal,
): Promise<Equipment> {
  const payload = await client.get<unknown>(
    `/api/v1/customers/me/equipment/${encodeURIComponent(equipmentId)}`,
    { signal },
  )
  return parseEquipment(payload)
}

export async function createEquipment(
  client: ApiClient,
  data: EquipmentCreateRequest,
): Promise<Equipment> {
  const payload = await client.post<unknown>(
    '/api/v1/customers/me/equipment',
    { json: data },
  )
  return parseEquipment(payload)
}

export async function updateEquipment(
  client: ApiClient,
  equipmentId: string,
  data: EquipmentUpdateRequest,
): Promise<Equipment> {
  const payload = await client.patch<unknown>(
    `/api/v1/customers/me/equipment/${encodeURIComponent(equipmentId)}`,
    { json: data },
  )
  return parseEquipment(payload)
}

export async function deleteEquipment(
  client: ApiClient,
  equipmentId: string,
): Promise<void> {
  await client.delete<void>(
    `/api/v1/customers/me/equipment/${encodeURIComponent(equipmentId)}`,
    { responseType: 'none' },
  )
}
