import type { AssignmentStatus } from '../../lib/api/types'

export interface Assignment {
  id: string
  work_order_id: string
  technician_id: string
  assignment_status: AssignmentStatus
  assigned_at: string
  accepted_at: string | null
  rejected_at: string | null
}

export interface AssignmentCreateRequest {
  technician_id: string
}

export interface AssignmentListQuery {
  status?: AssignmentStatus
  work_order_id?: string
  technician_id?: string
  limit?: number
  offset?: number
}

export interface TechnicianSummary {
  id: string
  user_id: string
  full_name: string
  email: string | null
  skills: Record<string, unknown>
  service_area: string | null
  is_available: boolean
}
