import type { ApiClient } from '../../lib/api/client.ts'
import type { PaginatedResponse } from '../../lib/api/types.ts'
import {
  listAdminComplaints,
  listAdminCompletionReports,
  listAdminDocuments,
  listAdminProposals,
  listAdminTechnicians,
  listAdminWorkflowRuns,
  listAdminWorkOrders,
} from './api'
import type { Complaint } from '../complaints/types'
import type { DocumentMetadata } from '../documents/types'
import type { WorkOrder, WorkOrderProposal } from '../work-orders/types'
import type { WorkflowRun } from '../workflows/types'

const DASHBOARD_PAGE_SIZE = 100

export interface AdminDashboardData {
  complaints: PaginatedResponse<Complaint>
  workOrders: PaginatedResponse<WorkOrder>
  proposals: PaginatedResponse<WorkOrderProposal>
  pendingProposals: PaginatedResponse<WorkOrderProposal>
  pendingEvidence: PaginatedResponse<unknown>
  failedWorkflows: PaginatedResponse<WorkflowRun>
  runningWorkflows: PaginatedResponse<WorkflowRun>
  documents: PaginatedResponse<DocumentMetadata>
  technicians: PaginatedResponse<unknown>
}

export interface AdminDashboardSummary {
  complaintTotal: number
  activeWorkOrderTotal: number
  workOrderTotal: number
  workOrderLoadedCount: number
  workOrderTruncatedNote: string | null
  pendingProposalTotal: number
  pendingEvidenceTotal: number
  failedWorkflowTotal: number
  runningWorkflowTotal: number
  eligibleTechnicianTotal: number
  documentTotal: number
  activeDocumentCount: number
  documentTruncatedNote: string | null
}

export interface AdminDashboardPreviews {
  complaints: Complaint[]
  workOrders: WorkOrder[]
  proposals: WorkOrderProposal[]
}

const ACTIVE_WORK_ORDER_STATUSES = new Set<WorkOrder['status']>([
  'assigned',
  'accepted',
  'in_progress',
  'awaiting_parts',
  'pending_verification',
  'escalated',
])

function isTruncated<T>(page: PaginatedResponse<T>): boolean {
  return page.offset + page.items.length < page.total
}

export async function loadAdminDashboard(
  client: ApiClient,
  signal?: AbortSignal,
): Promise<AdminDashboardData> {
  const [
    complaints,
    workOrders,
    proposals,
    pendingProposals,
    pendingEvidence,
    failedWorkflows,
    runningWorkflows,
    documents,
    technicians,
  ] = await Promise.all([
    listAdminComplaints(
      client,
      { limit: DASHBOARD_PAGE_SIZE, offset: 0 },
      signal,
    ),
    listAdminWorkOrders(
      client,
      { limit: DASHBOARD_PAGE_SIZE, offset: 0 },
      signal,
    ),
    listAdminProposals(
      client,
      { limit: DASHBOARD_PAGE_SIZE, offset: 0 },
      signal,
    ),
    listAdminProposals(
      client,
      { status: 'pending_approval', limit: 1, offset: 0 },
      signal,
    ),
    listAdminCompletionReports(
      client,
      { evidence_status: 'pending', limit: 1, offset: 0 },
      signal,
    ),
    listAdminWorkflowRuns(
      client,
      { status: 'failed', limit: 1, offset: 0 },
      signal,
    ),
    listAdminWorkflowRuns(
      client,
      { status: 'running', limit: 1, offset: 0 },
      signal,
    ),
    listAdminDocuments(
      client,
      { limit: DASHBOARD_PAGE_SIZE, offset: 0 },
      signal,
    ),
    listAdminTechnicians(client, { limit: 1, offset: 0 }, signal),
  ])

  return {
    complaints,
    workOrders,
    proposals,
    pendingProposals,
    pendingEvidence,
    failedWorkflows,
    runningWorkflows,
    documents,
    technicians,
  }
}

export function summarizeAdminDashboard(
  data: AdminDashboardData,
): AdminDashboardSummary {
  const workOrders = data.workOrders
  const workOrdersTruncated = isTruncated(workOrders)
  const documentsTruncated = isTruncated(data.documents)

  return {
    complaintTotal: data.complaints.total,
    activeWorkOrderTotal: workOrders.items.filter((workOrder) =>
      ACTIVE_WORK_ORDER_STATUSES.has(workOrder.status),
    ).length,
    workOrderTotal: workOrders.total,
    workOrderLoadedCount: workOrders.items.length,
    workOrderTruncatedNote: workOrdersTruncated
      ? `Active count is based on ${workOrders.items.length} of ${workOrders.total} work orders loaded in this view.`
      : null,
    pendingProposalTotal: data.pendingProposals.total,
    pendingEvidenceTotal: data.pendingEvidence.total,
    failedWorkflowTotal: data.failedWorkflows.total,
    runningWorkflowTotal: data.runningWorkflows.total,
    eligibleTechnicianTotal: data.technicians.total,
    documentTotal: data.documents.total,
    activeDocumentCount: data.documents.items.filter(
      (document) => document.is_active,
    ).length,
    documentTruncatedNote: documentsTruncated
      ? `Active count is based on ${data.documents.items.length} of ${data.documents.total} documents loaded in this view.`
      : null,
  }
}

export function selectAdminDashboardPreviews(
  data: AdminDashboardData,
): AdminDashboardPreviews {
  return {
    complaints: data.complaints.items.slice(0, 5),
    workOrders: data.workOrders.items.slice(0, 5),
    proposals: data.proposals.items.slice(0, 5),
  }
}
