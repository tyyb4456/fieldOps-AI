import type { ApiClient } from '../../lib/api/client.ts'
import {
  COMPLAINT_STATUSES,
  type ComplaintStatus,
  type PaginatedResponse,
} from '../../lib/api/types.ts'
import { listComplaints } from '../complaints/api.ts'
import type { Complaint } from '../complaints/types.ts'
import { listEquipment } from '../equipment/api.ts'
import type { Equipment } from '../equipment/types.ts'
import { fetchCustomerProfile } from './api.ts'
import type { CustomerProfile } from './types'

const DASHBOARD_PAGE_SIZE = 100

export interface CustomerDashboardData {
  profile: CustomerProfile
  equipment: PaginatedResponse<Equipment>
  complaints: PaginatedResponse<Complaint>
}

export interface CustomerDashboardSummary {
  equipmentTotal: number
  equipmentLoaded: number
  equipmentNote: string | null
  complaintTotal: number
  complaintLoaded: number
  complaintNote: string | null
  awaitingResponse: number
  awaitingResponseNote: string | null
  statusCounts: Partial<Record<ComplaintStatus, number>>
  visibleStatuses: ComplaintStatus[]
  statusBreakdownNote: string | null
}

export async function loadCustomerDashboard(
  client: ApiClient,
  signal?: AbortSignal,
): Promise<CustomerDashboardData> {
  const [profile, equipment, complaints] = await Promise.all([
    fetchCustomerProfile(client, signal),
    listEquipment(
      client,
      { limit: DASHBOARD_PAGE_SIZE, offset: 0 },
      signal,
    ),
    listComplaints(
      client,
      { limit: DASHBOARD_PAGE_SIZE, offset: 0 },
      signal,
    ),
  ])

  return { profile, equipment, complaints }
}

export function complaintStatusCounts(
  complaints: readonly Complaint[],
): Partial<Record<ComplaintStatus, number>> {
  const counts: Partial<Record<ComplaintStatus, number>> = {}

  for (const complaint of complaints) {
    counts[complaint.status] = (counts[complaint.status] ?? 0) + 1
  }

  return counts
}

function isTruncated<T>(page: PaginatedResponse<T>): boolean {
  return page.offset + page.items.length < page.total
}

export function summarizeCustomerDashboard(
  equipment: PaginatedResponse<Equipment>,
  complaints: PaginatedResponse<Complaint>,
): CustomerDashboardSummary {
  const statusCounts = complaintStatusCounts(complaints.items)
  const equipmentLoaded = equipment.items.length
  const complaintLoaded = complaints.items.length
  const equipmentTruncated = isTruncated(equipment)
  const complaintsTruncated = isTruncated(complaints)
  const visibleStatuses = COMPLAINT_STATUSES.filter(
    (status) => (statusCounts[status] ?? 0) > 0,
  )

  return {
    equipmentTotal: equipment.total,
    equipmentLoaded,
    equipmentNote: equipmentTruncated
      ? `Total reported by the API. ${equipmentLoaded} of ${equipment.total} equipment records loaded in this view.`
      : null,
    complaintTotal: complaints.total,
    complaintLoaded,
    complaintNote: complaintsTruncated
      ? `Total reported by the API. ${complaintLoaded} of ${complaints.total} complaints loaded in this view.`
      : null,
    awaitingResponse: statusCounts.awaiting_customer ?? 0,
    awaitingResponseNote: complaintsTruncated
      ? `Based on the ${complaintLoaded} complaints loaded in this view (of ${complaints.total} total).`
      : null,
    statusCounts,
    visibleStatuses,
    statusBreakdownNote: complaintsTruncated
      ? `Status breakdown is based on the ${complaintLoaded} complaints loaded in this view (of ${complaints.total} total).`
      : null,
  }
}
