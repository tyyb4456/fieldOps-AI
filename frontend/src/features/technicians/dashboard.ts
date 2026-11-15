import type { ApiClient } from '../../lib/api/client.ts'
import type { PaginatedResponse } from '../../lib/api/types.ts'
import { listAssignments } from '../assignments/api.ts'
import type { Assignment } from '../assignments/types.ts'
import { listWorkOrders } from '../work-orders/api.ts'
import type { WorkOrder } from '../work-orders/types.ts'

const DASHBOARD_PAGE_SIZE = 100

export interface TechnicianDashboardData {
  workOrders: PaginatedResponse<WorkOrder>
  offeredAssignments: PaginatedResponse<Assignment>
}

export interface TechnicianDashboardSummary {
  assignedWorkOrderTotal: number
  workOrderLoadedCount: number
  workOrderTruncatedNote: string | null
  offeredAssignmentTotal: number
  offeredAssignmentLoadedCount: number
  offeredTruncatedNote: string | null
  acceptedCount: number
  inProgressCount: number
  attentionCount: number
  pendingVerificationCount: number
  completedCount: number
  cancelledCount: number
  loadedStatusNote: string | null
}

export interface TechnicianDashboardPreviews {
  active: WorkOrder[]
  completed: WorkOrder[]
  offered: { assignment: Assignment; workOrder: WorkOrder | null }[]
}

const ACTIVE_STATUSES = new Set<WorkOrder['status']>([
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

export async function loadTechnicianDashboard(
  client: ApiClient,
  signal?: AbortSignal,
): Promise<TechnicianDashboardData> {
  const [workOrders, offeredAssignments] = await Promise.all([
    listWorkOrders(
      client,
      { limit: DASHBOARD_PAGE_SIZE, offset: 0 },
      signal,
    ),
    listAssignments(
      client,
      { status: 'offered', limit: DASHBOARD_PAGE_SIZE, offset: 0 },
      signal,
    ),
  ])

  return { workOrders, offeredAssignments }
}

export function summarizeTechnicianDashboard(
  workOrders: PaginatedResponse<WorkOrder>,
  offeredAssignments: PaginatedResponse<Assignment>,
): TechnicianDashboardSummary {
  const workOrderLoaded = workOrders.items.length
  const offeredLoaded = offeredAssignments.items.length
  const workOrdersTruncated = isTruncated(workOrders)
  const offeredTruncated = isTruncated(offeredAssignments)

  let acceptedCount = 0
  let inProgressCount = 0
  let attentionCount = 0
  let pendingVerificationCount = 0
  let completedCount = 0
  let cancelledCount = 0

  for (const workOrder of workOrders.items) {
    switch (workOrder.status) {
      case 'accepted':
        acceptedCount += 1
        break
      case 'in_progress':
        inProgressCount += 1
        break
      case 'awaiting_parts':
      case 'escalated':
        attentionCount += 1
        break
      case 'pending_verification':
        pendingVerificationCount += 1
        break
      case 'completed':
        completedCount += 1
        break
      case 'cancelled':
        cancelledCount += 1
        break
      default:
        break
    }
  }

  return {
    assignedWorkOrderTotal: workOrders.total,
    workOrderLoadedCount: workOrderLoaded,
    workOrderTruncatedNote: workOrdersTruncated
      ? `Total reported by the API. ${workOrderLoaded} of ${workOrders.total} work orders loaded in this view.`
      : null,
    offeredAssignmentTotal: offeredAssignments.total,
    offeredAssignmentLoadedCount: offeredLoaded,
    offeredTruncatedNote: offeredTruncated
      ? `Total reported by the API. ${offeredLoaded} of ${offeredAssignments.total} offered assignments loaded in this view.`
      : null,
    acceptedCount,
    inProgressCount,
    attentionCount,
    pendingVerificationCount,
    completedCount,
    cancelledCount,
    loadedStatusNote: workOrdersTruncated
      ? `Status counts are based on the ${workOrderLoaded} work orders loaded in this view (of ${workOrders.total} total).`
      : null,
  }
}

export function selectDashboardPreviews(
  workOrders: PaginatedResponse<WorkOrder>,
  offeredAssignments: PaginatedResponse<Assignment>,
): TechnicianDashboardPreviews {
  const workOrderById = new Map(
    workOrders.items.map((workOrder) => [workOrder.id, workOrder]),
  )

  const active = workOrders.items
    .filter((workOrder) => ACTIVE_STATUSES.has(workOrder.status))
    .slice(0, 5)

  const completed = workOrders.items
    .filter((workOrder) => workOrder.status === 'completed')
    .slice()
    .sort((left, right) =>
      right.updated_at.localeCompare(left.updated_at),
    )
    .slice(0, 5)

  const offered = offeredAssignments.items
    .slice(0, 5)
    .map((assignment) => ({
      assignment,
      workOrder: workOrderById.get(assignment.work_order_id) ?? null,
    }))

  return { active, completed, offered }
}
