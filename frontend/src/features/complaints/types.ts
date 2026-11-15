import type {
  ComplaintChannel,
  ComplaintStatus,
  Priority,
} from '../../lib/api/types'

export interface Complaint {
  id: string
  customer_id: string
  equipment_id: string | null
  description: string
  reported_symptoms: unknown[]
  reported_error_code: string | null
  channel: ComplaintChannel
  status: ComplaintStatus
  priority: Priority
  created_at: string
  updated_at: string
}

export interface ComplaintCreateRequest {
  description: string
  equipment_id?: string | null
  reported_error_code?: string | null
  channel?: ComplaintChannel
}

export interface ComplaintUpdateRequest {
  description?: string
  reported_error_code?: string | null
}

export interface ComplaintHistory {
  id: string
  complaint_id: string
  sequence_number: number
  event_type: string
  from_status: ComplaintStatus | null
  to_status: ComplaintStatus | null
  changed_fields: Record<string, unknown>
  actor_id: string | null
  created_at: string
}

export interface ComplaintListQuery {
  status?: ComplaintStatus
  equipment_id?: string
  created_from?: string
  created_to?: string
  customer_id?: string
  limit?: number
  offset?: number
}
