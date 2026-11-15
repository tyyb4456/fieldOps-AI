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
  isEvidenceStatus,
  isPriority,
  isWorkOrderStatus,
  type PaginatedResponse,
  type WorkOrderStatus,
} from '../../lib/api/types.ts'
import type {
  CompletionReport,
  CompletionReportCreateRequest,
  CompletionReportListQuery,
  CompletionReportUpdateRequest,
  ServiceRecord,
  ServiceRecordCreateRequest,
  ServiceRecordListQuery,
  ServiceRecordUpdateRequest,
  WorkOrder,
  WorkOrderListQuery,
  WorkOrderStatusUpdateRequest,
} from './types'

export function parseWorkOrder(payload: unknown): WorkOrder {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid work-order response.',
    )
  }

  if (!isWorkOrderStatus(payload.status)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid work-order status.',
    )
  }

  if (!isPriority(payload.priority)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid work-order priority.',
    )
  }

  return {
    id: requireString(payload.id, 'id'),
    complaint_id: requireString(payload.complaint_id, 'complaint_id'),
    equipment_id: requireString(payload.equipment_id, 'equipment_id'),
    title: requireString(payload.title, 'title'),
    description: requireString(payload.description, 'description'),
    diagnostic_checklist: requireArray(
      payload.diagnostic_checklist,
      'diagnostic_checklist',
    ),
    priority: payload.priority,
    status: payload.status,
    created_at: requireString(payload.created_at, 'created_at'),
    updated_at: requireString(payload.updated_at, 'updated_at'),
  }
}

export function parseWorkOrderList(
  payload: unknown,
): PaginatedResponse<WorkOrder> {
  return parsePaginatedResponse(payload, parseWorkOrder, 'work-order')
}

function toWorkOrderQuery(
  query: WorkOrderListQuery,
): Record<string, string | number | undefined> {
  return {
    status: query.status,
    priority: query.priority,
    complaint_id: query.complaint_id,
    equipment_id: query.equipment_id,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function listWorkOrders(
  client: ApiClient,
  query: WorkOrderListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<WorkOrder>> {
  const payload = await client.get<unknown>('/api/v1/work-orders', {
    query: toWorkOrderQuery(query),
    signal,
  })
  return parseWorkOrderList(payload)
}

export async function getWorkOrder(
  client: ApiClient,
  workOrderId: string,
  signal?: AbortSignal,
): Promise<WorkOrder> {
  const payload = await client.get<unknown>(
    `/api/v1/work-orders/${encodeURIComponent(workOrderId)}`,
    { signal },
  )
  return parseWorkOrder(payload)
}

export async function updateWorkOrderStatus(
  client: ApiClient,
  workOrderId: string,
  status: WorkOrderStatus,
): Promise<WorkOrder> {
  const payload = await client.post<unknown>(
    `/api/v1/work-orders/${encodeURIComponent(workOrderId)}/status`,
    { json: { status } satisfies WorkOrderStatusUpdateRequest },
  )
  return parseWorkOrder(payload)
}

export function parseServiceRecord(payload: unknown): ServiceRecord {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid service-record response.',
    )
  }

  return {
    id: requireString(payload.id, 'id'),
    equipment_id: requireString(payload.equipment_id, 'equipment_id'),
    work_order_id: requireString(payload.work_order_id, 'work_order_id'),
    technician_id: requireString(payload.technician_id, 'technician_id'),
    findings: optionalString(payload.findings, 'findings'),
    work_performed: optionalString(payload.work_performed, 'work_performed'),
    parts_used: requireArray(payload.parts_used, 'parts_used'),
    recorded_at: requireString(payload.recorded_at, 'recorded_at'),
  }
}

export function parseServiceRecordList(
  payload: unknown,
): PaginatedResponse<ServiceRecord> {
  return parsePaginatedResponse(payload, parseServiceRecord, 'service-record')
}

function toServiceRecordQuery(
  query: ServiceRecordListQuery,
): Record<string, string | number | undefined> {
  return {
    work_order_id: query.work_order_id,
    equipment_id: query.equipment_id,
    technician_id: query.technician_id,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function listServiceRecords(
  client: ApiClient,
  query: ServiceRecordListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<ServiceRecord>> {
  const payload = await client.get<unknown>('/api/v1/service-records', {
    query: toServiceRecordQuery(query),
    signal,
  })
  return parseServiceRecordList(payload)
}

export async function listWorkOrderServiceRecords(
  client: ApiClient,
  workOrderId: string,
  query: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<ServiceRecord>> {
  const payload = await client.get<unknown>(
    `/api/v1/work-orders/${encodeURIComponent(workOrderId)}/service-records`,
    {
      query: { limit: query.limit, offset: query.offset },
      signal,
    },
  )
  return parseServiceRecordList(payload)
}

export async function getServiceRecord(
  client: ApiClient,
  serviceRecordId: string,
  signal?: AbortSignal,
): Promise<ServiceRecord> {
  const payload = await client.get<unknown>(
    `/api/v1/service-records/${encodeURIComponent(serviceRecordId)}`,
    { signal },
  )
  return parseServiceRecord(payload)
}

export async function createServiceRecord(
  client: ApiClient,
  workOrderId: string,
  data: ServiceRecordCreateRequest,
): Promise<ServiceRecord> {
  const payload = await client.post<unknown>(
    `/api/v1/work-orders/${encodeURIComponent(workOrderId)}/service-records`,
    { json: data },
  )
  return parseServiceRecord(payload)
}

export async function updateServiceRecord(
  client: ApiClient,
  serviceRecordId: string,
  data: ServiceRecordUpdateRequest,
): Promise<ServiceRecord> {
  const payload = await client.patch<unknown>(
    `/api/v1/service-records/${encodeURIComponent(serviceRecordId)}`,
    { json: data },
  )
  return parseServiceRecord(payload)
}

export function parseCompletionReport(payload: unknown): CompletionReport {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid completion-report response.',
    )
  }

  if (!isEvidenceStatus(payload.evidence_status)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid evidence status.',
    )
  }

  return {
    id: requireString(payload.id, 'id'),
    work_order_id: requireString(payload.work_order_id, 'work_order_id'),
    service_record_id: optionalString(
      payload.service_record_id,
      'service_record_id',
    ),
    summary: requireString(payload.summary, 'summary'),
    evidence_status: payload.evidence_status,
    verification_notes: optionalString(
      payload.verification_notes,
      'verification_notes',
    ),
    submitted_at: requireString(payload.submitted_at, 'submitted_at'),
    verified_at: optionalString(payload.verified_at, 'verified_at'),
  }
}

export function parseCompletionReportList(
  payload: unknown,
): PaginatedResponse<CompletionReport> {
  return parsePaginatedResponse(payload, parseCompletionReport, 'completion-report')
}

function toCompletionReportQuery(
  query: CompletionReportListQuery,
): Record<string, string | number | undefined> {
  return {
    work_order_id: query.work_order_id,
    service_record_id: query.service_record_id,
    evidence_status: query.evidence_status,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function listCompletionReports(
  client: ApiClient,
  query: CompletionReportListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<CompletionReport>> {
  const payload = await client.get<unknown>('/api/v1/completion-reports', {
    query: toCompletionReportQuery(query),
    signal,
  })
  return parseCompletionReportList(payload)
}

export async function listWorkOrderCompletionReports(
  client: ApiClient,
  workOrderId: string,
  query: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<CompletionReport>> {
  const payload = await client.get<unknown>(
    `/api/v1/work-orders/${encodeURIComponent(workOrderId)}/completion-reports`,
    {
      query: { limit: query.limit, offset: query.offset },
      signal,
    },
  )
  return parseCompletionReportList(payload)
}

export async function getCompletionReport(
  client: ApiClient,
  completionReportId: string,
  signal?: AbortSignal,
): Promise<CompletionReport> {
  const payload = await client.get<unknown>(
    `/api/v1/completion-reports/${encodeURIComponent(completionReportId)}`,
    { signal },
  )
  return parseCompletionReport(payload)
}

export async function createCompletionReport(
  client: ApiClient,
  workOrderId: string,
  data: CompletionReportCreateRequest,
): Promise<CompletionReport> {
  const payload = await client.post<unknown>(
    `/api/v1/work-orders/${encodeURIComponent(workOrderId)}/completion-reports`,
    { json: data },
  )
  return parseCompletionReport(payload)
}

export async function updateCompletionReport(
  client: ApiClient,
  completionReportId: string,
  data: CompletionReportUpdateRequest,
): Promise<CompletionReport> {
  const payload = await client.patch<unknown>(
    `/api/v1/completion-reports/${encodeURIComponent(completionReportId)}`,
    { json: data },
  )
  return parseCompletionReport(payload)
}
