import type { ApiClient } from '../../lib/api/client.ts'
import { ApiError } from '../../lib/api/errors.ts'
import {
  isRecord,
  optionalString,
  parsePaginatedResponse,
  requireArray,
  requireBoolean,
  requireNumber,
  requireString,
} from '../../lib/api/parse.ts'
import {
  ASSIGNMENT_STATUSES,
  COMPLAINT_STATUSES,
  DIAGNOSTIC_STATUSES,
  EVIDENCE_STATUSES,
  INGESTION_STATUSES,
  PRIORITIES,
  WORKFLOW_RUN_STATUSES,
  WORKFLOW_RUN_TYPES,
  WORK_ORDER_PROPOSAL_STATUSES,
  WORK_ORDER_STATUSES,
  type AssignmentStatus,
  type ComplaintStatus,
  type DiagnosticStatus,
  type EvidenceStatus,
  type IngestionStatus,
  type PaginatedResponse,
  type Priority,
  type WorkOrderProposalStatus,
  type WorkOrderStatus,
  type WorkflowRunStatus,
  type WorkflowRunType,
} from '../../lib/api/types.ts'
import type { Assignment, TechnicianSummary } from '../assignments/types'
import type { Complaint, ComplaintHistory } from '../complaints/types'
import type { CustomerProfile } from '../customers/types'
import type {
  DocumentChunk,
  DocumentMetadata,
  DocumentUpdateRequest,
  DocumentUploadFields,
} from '../documents/types'
import type {
  Equipment,
  EquipmentCreateRequest,
  EquipmentUpdateRequest,
} from '../equipment/types'
import type { Citation } from '../knowledge/types'
import type {
  CompletionReport,
  CompletionReportUpdateRequest,
  ServiceRecord,
  TechnicianRecommendation,
  WorkOrder,
  WorkOrderCreateRequest,
  WorkOrderProposal,
  WorkOrderUpdateRequest,
} from '../work-orders/types'
import type { WorkflowRun, WorkflowRunAccepted } from '../workflows/types'
import type {
  AdminAssignmentListQuery,
  AdminComplaintListQuery,
  AdminCompletionReportListQuery,
  AdminDocumentListQuery,
  AdminEquipmentListQuery,
  AdminProposalListQuery,
  AdminTechnicianListQuery,
  AdminWorkflowRunListQuery,
  AdminWorkOrderListQuery,
} from './types'

function invalidResponse(message: string): ApiError {
  return new ApiError(500, 'invalid_response', message)
}

function isOneOf<T extends string>(
  values: readonly T[],
  value: unknown,
): value is T {
  return (
    typeof value === 'string' &&
    (values as readonly string[]).includes(value)
  )
}

function optionalNumber(value: unknown, field: string): number | null {
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw invalidResponse(`The API returned an invalid "${field}" field.`)
  }
  return value
}

function requireStringArray(value: unknown, field: string): string[] {
  return requireArray(value, field).map((item) =>
    requireString(item, field),
  )
}

function requireRecord(
  value: unknown,
  field: string,
): Record<string, unknown> {
  if (!isRecord(value)) {
    throw invalidResponse(`The API returned an invalid "${field}" field.`)
  }
  return value
}

export function parseComplaintHistory(payload: unknown): ComplaintHistory {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid complaint history.')
  }

  const fromStatus = payload.from_status
  const toStatus = payload.to_status

  return {
    id: requireString(payload.id, 'id'),
    complaint_id: requireString(payload.complaint_id, 'complaint_id'),
    sequence_number: requireNumber(
      payload.sequence_number,
      'sequence_number',
    ),
    event_type: requireString(payload.event_type, 'event_type'),
    from_status:
      fromStatus === null || fromStatus === undefined
        ? null
        : isOneOf(COMPLAINT_STATUSES, fromStatus)
          ? fromStatus
          : (() => {
              throw invalidResponse(
                'The API returned an invalid complaint history status.',
              )
            })(),
    to_status:
      toStatus === null || toStatus === undefined
        ? null
        : isOneOf(COMPLAINT_STATUSES, toStatus)
          ? toStatus
          : (() => {
              throw invalidResponse(
                'The API returned an invalid complaint history status.',
              )
            })(),
    changed_fields: requireRecord(
      payload.changed_fields,
      'changed_fields',
    ),
    actor_id: optionalString(payload.actor_id, 'actor_id'),
    created_at: requireString(payload.created_at, 'created_at'),
  }
}

export interface ComplaintHistoryPage {
  items: ComplaintHistory[]
  total: number
}

export function parseComplaintHistoryPage(
  payload: unknown,
): ComplaintHistoryPage {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid complaint history.')
  }
  return {
    items: requireArray(payload.items, 'items').map(parseComplaintHistory),
    total: requireNumber(payload.total, 'total'),
  }
}

export function parseCitation(payload: unknown): Citation {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid citation.')
  }
  return {
    source_id: requireString(payload.source_id, 'source_id'),
    chunk_id: requireString(payload.chunk_id, 'chunk_id'),
    document_id: requireString(payload.document_id, 'document_id'),
    document_name: requireString(
      payload.document_name,
      'document_name',
    ),
    manufacturer: requireString(payload.manufacturer, 'manufacturer'),
    model: requireString(payload.model, 'model'),
    version: optionalString(payload.version, 'version'),
    page_number: optionalNumber(payload.page_number, 'page_number'),
    chunk_index: requireNumber(payload.chunk_index, 'chunk_index'),
    excerpt: requireString(payload.excerpt, 'excerpt'),
  }
}

export function parseTechnicianRecommendation(
  payload: unknown,
): TechnicianRecommendation {
  if (!isRecord(payload)) {
    throw invalidResponse(
      'The API returned an invalid technician recommendation.',
    )
  }
  return {
    technician_id: requireString(payload.technician_id, 'technician_id'),
    full_name: requireString(payload.full_name, 'full_name'),
    eligible: requireBoolean(payload.eligible, 'eligible'),
    matching_skills: requireStringArray(
      payload.matching_skills,
      'matching_skills',
    ),
    missing_skills: requireStringArray(
      payload.missing_skills,
      'missing_skills',
    ),
    active_workload: requireNumber(
      payload.active_workload,
      'active_workload',
    ),
    availability_status: requireString(
      payload.availability_status,
      'availability_status',
    ),
    reasons: requireStringArray(payload.reasons, 'reasons'),
    rank: requireNumber(payload.rank, 'rank'),
  }
}

export function parseWorkOrderProposal(payload: unknown): WorkOrderProposal {
  if (!isRecord(payload)) {
    throw invalidResponse(
      'The API returned an invalid work-order proposal.',
    )
  }

  if (!isOneOf(WORK_ORDER_PROPOSAL_STATUSES, payload.status)) {
    throw invalidResponse(
      'The API returned an invalid proposal status.',
    )
  }
  if (!isOneOf(PRIORITIES, payload.priority)) {
    throw invalidResponse(
      'The API returned an invalid proposal priority.',
    )
  }
  if (!isOneOf(DIAGNOSTIC_STATUSES, payload.diagnostic_status)) {
    throw invalidResponse(
      'The API returned an invalid diagnostic status.',
    )
  }

  return {
    id: requireString(payload.id, 'id'),
    complaint_id: requireString(payload.complaint_id, 'complaint_id'),
    status: payload.status,
    title: requireString(payload.title, 'title'),
    problem_description: requireString(
      payload.problem_description,
      'problem_description',
    ),
    proposed_scope: requireString(
      payload.proposed_scope,
      'proposed_scope',
    ),
    technical_findings: requireString(
      payload.technical_findings,
      'technical_findings',
    ),
    recommended_actions: requireStringArray(
      payload.recommended_actions,
      'recommended_actions',
    ),
    required_skills: requireStringArray(
      payload.required_skills,
      'required_skills',
    ),
    required_parts: requireStringArray(
      payload.required_parts,
      'required_parts',
    ),
    priority: payload.priority,
    estimated_duration_minutes: optionalNumber(
      payload.estimated_duration_minutes,
      'estimated_duration_minutes',
    ),
    safety_warnings: requireStringArray(
      payload.safety_warnings,
      'safety_warnings',
    ),
    missing_information: requireStringArray(
      payload.missing_information,
      'missing_information',
    ),
    generation_warnings: requireStringArray(
      payload.generation_warnings,
      'generation_warnings',
    ),
    diagnostic_status: payload.diagnostic_status,
    diagnostic_summary: requireString(
      payload.diagnostic_summary,
      'diagnostic_summary',
    ),
    diagnostic_snapshot: requireRecord(
      payload.diagnostic_snapshot,
      'diagnostic_snapshot',
    ),
    citations: requireArray(payload.citations, 'citations').map(
      parseCitation,
    ),
    requires_escalation: requireBoolean(
      payload.requires_escalation,
      'requires_escalation',
    ),
    escalation_reason: optionalString(
      payload.escalation_reason,
      'escalation_reason',
    ),
    technician_recommendations: requireArray(
      payload.technician_recommendations,
      'technician_recommendations',
    ).map(parseTechnicianRecommendation),
    selected_technician_id: optionalString(
      payload.selected_technician_id,
      'selected_technician_id',
    ),
    created_by_id: optionalString(payload.created_by_id, 'created_by_id'),
    reviewed_by_id: optionalString(
      payload.reviewed_by_id,
      'reviewed_by_id',
    ),
    reviewed_at: optionalString(payload.reviewed_at, 'reviewed_at'),
    rejection_reason: optionalString(
      payload.rejection_reason,
      'rejection_reason',
    ),
    resulting_work_order_id: optionalString(
      payload.resulting_work_order_id,
      'resulting_work_order_id',
    ),
    resulting_assignment_id: optionalString(
      payload.resulting_assignment_id,
      'resulting_assignment_id',
    ),
    created_at: requireString(payload.created_at, 'created_at'),
    updated_at: requireString(payload.updated_at, 'updated_at'),
  }
}

export function parseWorkflowRun(payload: unknown): WorkflowRun {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid workflow run.')
  }
  if (!isOneOf(WORKFLOW_RUN_STATUSES, payload.status)) {
    throw invalidResponse('The API returned an invalid workflow status.')
  }

  const workflowType = payload.workflow_type
  if (
    workflowType !== null &&
    workflowType !== undefined &&
    !isOneOf(WORKFLOW_RUN_TYPES, workflowType)
  ) {
    throw invalidResponse('The API returned an invalid workflow type.')
  }

  return {
    id: requireString(payload.id, 'id'),
    complaint_id: requireString(payload.complaint_id, 'complaint_id'),
    workflow_type:
      workflowType === null || workflowType === undefined
        ? null
        : workflowType,
    status: payload.status,
    current_step: optionalString(payload.current_step, 'current_step'),
    started_at: requireString(payload.started_at, 'started_at'),
    finished_at: optionalString(payload.finished_at, 'finished_at'),
    error_message: optionalString(payload.error_message, 'error_message'),
  }
}

export function parseWorkflowRunAccepted(
  payload: unknown,
): WorkflowRunAccepted {
  if (!isRecord(payload)) {
    throw invalidResponse(
      'The API returned an invalid workflow acceptance response.',
    )
  }
  if (!isOneOf(WORKFLOW_RUN_TYPES, payload.workflow_type)) {
    throw invalidResponse('The API returned an invalid workflow type.')
  }
  if (!isOneOf(WORKFLOW_RUN_STATUSES, payload.status)) {
    throw invalidResponse('The API returned an invalid workflow status.')
  }
  return {
    workflow_run_id: requireString(
      payload.workflow_run_id,
      'workflow_run_id',
    ),
    complaint_id: requireString(payload.complaint_id, 'complaint_id'),
    workflow_type: payload.workflow_type,
    status: payload.status,
    current_step: optionalString(payload.current_step, 'current_step'),
  }
}

export function parseTechnicianSummary(payload: unknown): TechnicianSummary {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid technician.')
  }
  return {
    id: requireString(payload.id, 'id'),
    user_id: requireString(payload.user_id, 'user_id'),
    full_name: requireString(payload.full_name, 'full_name'),
    email: optionalString(payload.email, 'email'),
    skills: requireRecord(payload.skills, 'skills'),
    service_area: optionalString(payload.service_area, 'service_area'),
    is_available: requireBoolean(payload.is_available, 'is_available'),
  }
}

export function parseDocumentMetadata(payload: unknown): DocumentMetadata {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid document.')
  }
  if (!isOneOf(INGESTION_STATUSES, payload.ingestion_status)) {
    throw invalidResponse(
      'The API returned an invalid ingestion status.',
    )
  }
  return {
    id: requireString(payload.id, 'id'),
    manufacturer: requireString(payload.manufacturer, 'manufacturer'),
    model: requireString(payload.model, 'model'),
    document_name: requireString(
      payload.document_name,
      'document_name',
    ),
    version: optionalString(payload.version, 'version'),
    original_filename: optionalString(
      payload.original_filename,
      'original_filename',
    ),
    content_type: optionalString(payload.content_type, 'content_type'),
    byte_size: optionalNumber(payload.byte_size, 'byte_size'),
    checksum_sha256: optionalString(
      payload.checksum_sha256,
      'checksum_sha256',
    ),
    uploaded_by_id: optionalString(
      payload.uploaded_by_id,
      'uploaded_by_id',
    ),
    ingestion_status: payload.ingestion_status,
    ingestion_error: optionalString(
      payload.ingestion_error,
      'ingestion_error',
    ),
    ingested_at: optionalString(payload.ingested_at, 'ingested_at'),
    is_active: requireBoolean(payload.is_active, 'is_active'),
    created_at: requireString(payload.created_at, 'created_at'),
  }
}

export function parseDocumentChunk(payload: unknown): DocumentChunk {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid document chunk.')
  }
  return {
    id: requireString(payload.id, 'id'),
    document_id: requireString(payload.document_id, 'document_id'),
    chunk_index: requireNumber(payload.chunk_index, 'chunk_index'),
    content: requireString(payload.content, 'content'),
    page_number: optionalNumber(payload.page_number, 'page_number'),
    metadata: requireRecord(payload.metadata, 'metadata'),
  }
}

function toEquipmentQuery(
  query: AdminEquipmentListQuery,
): Record<string, string | number | undefined> {
  return {
    customer_id: query.customer_id,
    equipment_type: query.equipment_type,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function getAdminCustomer(
  client: ApiClient,
  customerId: string,
  signal?: AbortSignal,
): Promise<CustomerProfile> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/customers/${encodeURIComponent(customerId)}`,
    { signal },
  )
  return parseCustomerProfile(payload)
}

export function parseCustomerProfile(payload: unknown): CustomerProfile {
  if (!isRecord(payload)) {
    throw invalidResponse(
      'The API returned an invalid customer profile.',
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

export async function listAdminCustomerEquipment(
  client: ApiClient,
  customerId: string,
  query: AdminEquipmentListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<Equipment>> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/customers/${encodeURIComponent(customerId)}/equipment`,
    { query: toEquipmentQuery(query), signal },
  )
  return parseEquipmentList(payload)
}

export async function createAdminCustomerEquipment(
  client: ApiClient,
  customerId: string,
  data: EquipmentCreateRequest,
): Promise<Equipment> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/customers/${encodeURIComponent(customerId)}/equipment`,
    { json: data },
  )
  return parseEquipment(payload)
}

export async function listAdminEquipment(
  client: ApiClient,
  query: AdminEquipmentListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<Equipment>> {
  const payload = await client.get<unknown>('/api/v1/admin/equipment', {
    query: toEquipmentQuery(query),
    signal,
  })
  return parseEquipmentList(payload)
}

export async function getAdminEquipment(
  client: ApiClient,
  equipmentId: string,
  signal?: AbortSignal,
): Promise<Equipment> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/equipment/${encodeURIComponent(equipmentId)}`,
    { signal },
  )
  return parseEquipment(payload)
}

export async function updateAdminEquipment(
  client: ApiClient,
  equipmentId: string,
  data: EquipmentUpdateRequest,
): Promise<Equipment> {
  const payload = await client.patch<unknown>(
    `/api/v1/admin/equipment/${encodeURIComponent(equipmentId)}`,
    { json: data },
  )
  return parseEquipment(payload)
}

export async function deleteAdminEquipment(
  client: ApiClient,
  equipmentId: string,
): Promise<void> {
  await client.delete<void>(
    `/api/v1/admin/equipment/${encodeURIComponent(equipmentId)}`,
    { responseType: 'none' },
  )
}

export function parseEquipment(payload: unknown): Equipment {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid equipment record.')
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

function toComplaintQuery(
  query: AdminComplaintListQuery,
): Record<string, string | number | undefined> {
  return {
    customer_id: query.customer_id,
    status: query.status,
    equipment_id: query.equipment_id,
    created_from: query.created_from,
    created_to: query.created_to,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function listAdminComplaints(
  client: ApiClient,
  query: AdminComplaintListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<Complaint>> {
  const payload = await client.get<unknown>('/api/v1/admin/complaints', {
    query: toComplaintQuery(query),
    signal,
  })
  return parseComplaintList(payload)
}

export async function getAdminComplaint(
  client: ApiClient,
  complaintId: string,
  signal?: AbortSignal,
): Promise<Complaint> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/complaints/${encodeURIComponent(complaintId)}`,
    { signal },
  )
  return parseComplaint(payload)
}

export async function listAdminComplaintHistory(
  client: ApiClient,
  complaintId: string,
  signal?: AbortSignal,
): Promise<ComplaintHistoryPage> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/complaints/${encodeURIComponent(complaintId)}/history`,
    { signal },
  )
  return parseComplaintHistoryPage(payload)
}

export function parseComplaint(payload: unknown): Complaint {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid complaint.')
  }
  if (!isOneOf(COMPLAINT_STATUSES, payload.status)) {
    throw invalidResponse('The API returned an invalid complaint status.')
  }
  if (!isOneOf(PRIORITIES, payload.priority)) {
    throw invalidResponse(
      'The API returned an invalid complaint priority.',
    )
  }
  if (payload.channel !== 'web' && payload.channel !== 'whatsapp') {
    throw invalidResponse('The API returned an invalid complaint channel.')
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

function toWorkOrderQuery(
  query: AdminWorkOrderListQuery,
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

export async function listAdminWorkOrders(
  client: ApiClient,
  query: AdminWorkOrderListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<WorkOrder>> {
  const payload = await client.get<unknown>('/api/v1/admin/work-orders', {
    query: toWorkOrderQuery(query),
    signal,
  })
  return parseWorkOrderList(payload)
}

export async function getAdminWorkOrder(
  client: ApiClient,
  workOrderId: string,
  signal?: AbortSignal,
): Promise<WorkOrder> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/work-orders/${encodeURIComponent(workOrderId)}`,
    { signal },
  )
  return parseWorkOrder(payload)
}

export async function createWorkOrderFromComplaint(
  client: ApiClient,
  complaintId: string,
  data: WorkOrderCreateRequest,
): Promise<WorkOrder> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/complaints/${encodeURIComponent(
      complaintId,
    )}/work-orders`,
    { json: data },
  )
  return parseWorkOrder(payload)
}

export async function updateAdminWorkOrder(
  client: ApiClient,
  workOrderId: string,
  data: WorkOrderUpdateRequest,
): Promise<WorkOrder> {
  const payload = await client.patch<unknown>(
    `/api/v1/admin/work-orders/${encodeURIComponent(workOrderId)}`,
    { json: data },
  )
  return parseWorkOrder(payload)
}

export async function updateAdminWorkOrderStatus(
  client: ApiClient,
  workOrderId: string,
  status: WorkOrderStatus,
): Promise<WorkOrder> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/work-orders/${encodeURIComponent(
      workOrderId,
    )}/status`,
    { json: { status } },
  )
  return parseWorkOrder(payload)
}

export function parseWorkOrder(payload: unknown): WorkOrder {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid work order.')
  }
  if (!isOneOf(WORK_ORDER_STATUSES, payload.status)) {
    throw invalidResponse('The API returned an invalid work-order status.')
  }
  if (!isOneOf(PRIORITIES, payload.priority)) {
    throw invalidResponse(
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

function toAssignmentQuery(
  query: AdminAssignmentListQuery,
): Record<string, string | number | undefined> {
  return {
    status: query.status,
    work_order_id: query.work_order_id,
    technician_id: query.technician_id,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function listAdminAssignments(
  client: ApiClient,
  query: AdminAssignmentListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<Assignment>> {
  const payload = await client.get<unknown>('/api/v1/admin/assignments', {
    query: toAssignmentQuery(query),
    signal,
  })
  return parsePaginatedResponse(payload, parseAssignment, 'assignment')
}

export async function getAdminAssignment(
  client: ApiClient,
  assignmentId: string,
  signal?: AbortSignal,
): Promise<Assignment> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/assignments/${encodeURIComponent(assignmentId)}`,
    { signal },
  )
  return parseAssignment(payload)
}

export async function createAdminAssignment(
  client: ApiClient,
  workOrderId: string,
  technicianId: string,
): Promise<Assignment> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/work-orders/${encodeURIComponent(
      workOrderId,
    )}/assignments`,
    { json: { technician_id: technicianId } },
  )
  return parseAssignment(payload)
}

export async function reassignAdminAssignment(
  client: ApiClient,
  workOrderId: string,
  technicianId: string,
): Promise<Assignment> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/work-orders/${encodeURIComponent(
      workOrderId,
    )}/assignments/reassign`,
    { json: { technician_id: technicianId } },
  )
  return parseAssignment(payload)
}

export async function withdrawAdminAssignment(
  client: ApiClient,
  assignmentId: string,
): Promise<Assignment> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/assignments/${encodeURIComponent(
      assignmentId,
    )}/withdraw`,
  )
  return parseAssignment(payload)
}

export function parseAssignment(payload: unknown): Assignment {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid assignment.')
  }
  if (!isOneOf(ASSIGNMENT_STATUSES, payload.assignment_status)) {
    throw invalidResponse(
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

function toCompletionReportQuery(
  query: AdminCompletionReportListQuery,
): Record<string, string | number | undefined> {
  return {
    work_order_id: query.work_order_id,
    service_record_id: query.service_record_id,
    evidence_status: query.evidence_status,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function listAdminCompletionReports(
  client: ApiClient,
  query: AdminCompletionReportListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<CompletionReport>> {
  const payload = await client.get<unknown>(
    '/api/v1/admin/completion-reports',
    { query: toCompletionReportQuery(query), signal },
  )
  return parseCompletionReportList(payload)
}

export async function getAdminCompletionReport(
  client: ApiClient,
  completionReportId: string,
  signal?: AbortSignal,
): Promise<CompletionReport> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/completion-reports/${encodeURIComponent(
      completionReportId,
    )}`,
    { signal },
  )
  return parseCompletionReport(payload)
}

export async function updateAdminCompletionReport(
  client: ApiClient,
  completionReportId: string,
  data: CompletionReportUpdateRequest,
): Promise<CompletionReport> {
  const payload = await client.patch<unknown>(
    `/api/v1/admin/completion-reports/${encodeURIComponent(
      completionReportId,
    )}`,
    { json: data },
  )
  return parseCompletionReport(payload)
}

export function parseCompletionReport(payload: unknown): CompletionReport {
  if (!isRecord(payload)) {
    throw invalidResponse(
      'The API returned an invalid completion report.',
    )
  }
  if (!isOneOf(EVIDENCE_STATUSES, payload.evidence_status)) {
    throw invalidResponse('The API returned an invalid evidence status.')
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
  return parsePaginatedResponse(
    payload,
    parseCompletionReport,
    'completion-report',
  )
}

export async function listAdminWorkOrderCompletionReports(
  client: ApiClient,
  workOrderId: string,
  query: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<CompletionReport>> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/work-orders/${encodeURIComponent(
      workOrderId,
    )}/completion-reports`,
    {
      query: { limit: query.limit, offset: query.offset },
      signal,
    },
  )
  return parseCompletionReportList(payload)
}

export async function listAdminServiceRecords(
  client: ApiClient,
  query: {
    work_order_id?: string
    equipment_id?: string
    technician_id?: string
    limit?: number
    offset?: number
  } = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<ServiceRecord>> {
  const payload = await client.get<unknown>(
    '/api/v1/admin/service-records',
    { query, signal },
  )
  return parsePaginatedResponse(
    payload,
    parseServiceRecord,
    'service-record',
  )
}

export function parseServiceRecord(payload: unknown): ServiceRecord {
  if (!isRecord(payload)) {
    throw invalidResponse('The API returned an invalid service record.')
  }
  return {
    id: requireString(payload.id, 'id'),
    equipment_id: requireString(payload.equipment_id, 'equipment_id'),
    work_order_id: requireString(payload.work_order_id, 'work_order_id'),
    technician_id: requireString(payload.technician_id, 'technician_id'),
    findings: optionalString(payload.findings, 'findings'),
    work_performed: optionalString(
      payload.work_performed,
      'work_performed',
    ),
    parts_used: requireArray(payload.parts_used, 'parts_used'),
    recorded_at: requireString(payload.recorded_at, 'recorded_at'),
  }
}

function toProposalQuery(
  query: AdminProposalListQuery,
): Record<string, string | number | undefined> {
  return {
    status: query.status,
    complaint_id: query.complaint_id,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function listAdminProposals(
  client: ApiClient,
  query: AdminProposalListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<WorkOrderProposal>> {
  const payload = await client.get<unknown>(
    '/api/v1/admin/work-order-proposals',
    { query: toProposalQuery(query), signal },
  )
  return parsePaginatedResponse(
    payload,
    parseWorkOrderProposal,
    'work-order proposal',
  )
}

export async function getAdminProposal(
  client: ApiClient,
  proposalId: string,
  signal?: AbortSignal,
): Promise<WorkOrderProposal> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/work-order-proposals/${encodeURIComponent(proposalId)}`,
    { signal },
  )
  return parseWorkOrderProposal(payload)
}

export async function generateAdminProposal(
  client: ApiClient,
  complaintId: string,
): Promise<WorkflowRunAccepted> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/complaints/${encodeURIComponent(
      complaintId,
    )}/work-order-proposals`,
  )
  return parseWorkflowRunAccepted(payload)
}

export async function approveAdminProposal(
  client: ApiClient,
  proposalId: string,
  technicianId: string | null,
): Promise<WorkOrderProposal> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/work-order-proposals/${encodeURIComponent(
      proposalId,
    )}/approve`,
    { json: { technician_id: technicianId } },
  )
  return parseWorkOrderProposal(payload)
}

export async function rejectAdminProposal(
  client: ApiClient,
  proposalId: string,
  reason: string,
): Promise<WorkOrderProposal> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/work-order-proposals/${encodeURIComponent(
      proposalId,
    )}/reject`,
    { json: { reason } },
  )
  return parseWorkOrderProposal(payload)
}

function toDocumentQuery(
  query: AdminDocumentListQuery,
): Record<string, string | number | boolean | undefined> {
  return {
    manufacturer: query.manufacturer,
    model: query.model,
    equipment_id: query.equipment_id,
    is_active: query.is_active,
    limit: query.limit,
    offset: query.offset,
  }
}

export async function listAdminDocuments(
  client: ApiClient,
  query: AdminDocumentListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<DocumentMetadata>> {
  const payload = await client.get<unknown>('/api/v1/admin/documents', {
    query: toDocumentQuery(query),
    signal,
  })
  return parsePaginatedResponse(
    payload,
    parseDocumentMetadata,
    'document',
  )
}

export async function getAdminDocument(
  client: ApiClient,
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentMetadata> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/documents/${encodeURIComponent(documentId)}`,
    { signal },
  )
  return parseDocumentMetadata(payload)
}

export async function uploadAdminDocument(
  client: ApiClient,
  fields: DocumentUploadFields,
): Promise<DocumentMetadata> {
  const formData = new FormData()
  formData.set('file', fields.file)
  formData.set('manufacturer', fields.manufacturer)
  formData.set('model', fields.model)
  formData.set('document_name', fields.document_name)
  if (fields.version) {
    formData.set('version', fields.version)
  }

  const payload = await client.post<unknown>('/api/v1/admin/documents', {
    formData,
  })
  return parseDocumentMetadata(payload)
}

export async function updateAdminDocument(
  client: ApiClient,
  documentId: string,
  data: DocumentUpdateRequest,
): Promise<DocumentMetadata> {
  const payload = await client.patch<unknown>(
    `/api/v1/admin/documents/${encodeURIComponent(documentId)}`,
    { json: data },
  )
  return parseDocumentMetadata(payload)
}

export async function deleteAdminDocument(
  client: ApiClient,
  documentId: string,
): Promise<void> {
  await client.delete<void>(
    `/api/v1/admin/documents/${encodeURIComponent(documentId)}`,
    { responseType: 'none' },
  )
}

export async function ingestAdminDocument(
  client: ApiClient,
  documentId: string,
): Promise<DocumentMetadata> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/documents/${encodeURIComponent(documentId)}/ingest`,
  )
  return parseDocumentMetadata(payload)
}

export async function activateAdminDocument(
  client: ApiClient,
  documentId: string,
): Promise<DocumentMetadata> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/documents/${encodeURIComponent(documentId)}/activate`,
  )
  return parseDocumentMetadata(payload)
}

export async function deactivateAdminDocument(
  client: ApiClient,
  documentId: string,
): Promise<DocumentMetadata> {
  const payload = await client.post<unknown>(
    `/api/v1/admin/documents/${encodeURIComponent(documentId)}/deactivate`,
  )
  return parseDocumentMetadata(payload)
}

export async function listAdminDocumentChunks(
  client: ApiClient,
  documentId: string,
  query: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<DocumentChunk>> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/documents/${encodeURIComponent(documentId)}/chunks`,
    {
      query: { limit: query.limit, offset: query.offset },
      signal,
    },
  )
  return parsePaginatedResponse(
    payload,
    parseDocumentChunk,
    'document chunk',
  )
}

export async function listAdminTechnicians(
  client: ApiClient,
  query: AdminTechnicianListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<TechnicianSummary>> {
  const payload = await client.get<unknown>('/api/v1/admin/technicians', {
    query: { limit: query.limit, offset: query.offset },
    signal,
  })
  return parsePaginatedResponse(
    payload,
    parseTechnicianSummary,
    'technician',
  )
}

export async function listAdminWorkflowRuns(
  client: ApiClient,
  query: AdminWorkflowRunListQuery = {},
  signal?: AbortSignal,
): Promise<PaginatedResponse<WorkflowRun>> {
  const payload = await client.get<unknown>('/api/v1/admin/workflow-runs', {
    query: {
      complaint_id: query.complaint_id,
      status: query.status,
      limit: query.limit,
      offset: query.offset,
    },
    signal,
  })
  return parsePaginatedResponse(
    payload,
    parseWorkflowRun,
    'workflow run',
  )
}

export async function getAdminWorkflowRun(
  client: ApiClient,
  workflowRunId: string,
  signal?: AbortSignal,
): Promise<WorkflowRun> {
  const payload = await client.get<unknown>(
    `/api/v1/admin/workflow-runs/${encodeURIComponent(workflowRunId)}`,
    { signal },
  )
  return parseWorkflowRun(payload)
}

export type {
  AssignmentStatus,
  ComplaintStatus,
  DiagnosticStatus,
  EvidenceStatus,
  IngestionStatus,
  Priority,
  WorkOrderProposalStatus,
  WorkOrderStatus,
  WorkflowRunStatus,
  WorkflowRunType,
}
