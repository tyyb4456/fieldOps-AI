import type {
  AssignmentStatus,
  ComplaintStatus,
  EvidenceStatus,
  Priority,
  WorkOrderProposalStatus,
  WorkOrderStatus,
  WorkflowRunStatus,
} from '../../lib/api/types'

export interface AdminEquipmentListQuery {
  customer_id?: string
  equipment_type?: string
  limit?: number
  offset?: number
}

export interface AdminComplaintListQuery {
  customer_id?: string
  status?: ComplaintStatus
  equipment_id?: string
  created_from?: string
  created_to?: string
  limit?: number
  offset?: number
}

export interface AdminWorkOrderListQuery {
  status?: WorkOrderStatus
  priority?: Priority
  complaint_id?: string
  equipment_id?: string
  limit?: number
  offset?: number
}

export interface AdminAssignmentListQuery {
  status?: AssignmentStatus
  work_order_id?: string
  technician_id?: string
  limit?: number
  offset?: number
}

export interface AdminCompletionReportListQuery {
  work_order_id?: string
  service_record_id?: string
  evidence_status?: EvidenceStatus
  limit?: number
  offset?: number
}

export interface AdminProposalListQuery {
  status?: WorkOrderProposalStatus
  complaint_id?: string
  limit?: number
  offset?: number
}

export interface AdminWorkflowRunListQuery {
  complaint_id?: string
  status?: WorkflowRunStatus
  limit?: number
  offset?: number
}

export interface AdminTechnicianListQuery {
  limit?: number
  offset?: number
}

export interface AdminDocumentListQuery {
  manufacturer?: string
  model?: string
  equipment_id?: string
  is_active?: boolean
  limit?: number
  offset?: number
}
