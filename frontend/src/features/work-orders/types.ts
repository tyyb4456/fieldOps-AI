import type {
  EvidenceStatus,
  Priority,
  WorkOrderProposalStatus,
  WorkOrderStatus,
} from '../../lib/api/types'
import type { DiagnosticStatus } from '../../lib/api/types'
import type { Citation } from '../knowledge/types'

export interface WorkOrder {
  id: string
  complaint_id: string
  equipment_id: string
  title: string
  description: string
  diagnostic_checklist: unknown[]
  priority: Priority
  status: WorkOrderStatus
  created_at: string
  updated_at: string
}

export interface WorkOrderCreateRequest {
  title: string
  description: string
  diagnostic_checklist?: unknown[]
  priority?: Priority | null
}

export interface WorkOrderUpdateRequest {
  title?: string
  description?: string
  diagnostic_checklist?: unknown[]
  priority?: Priority
}

export interface WorkOrderStatusUpdateRequest {
  status: WorkOrderStatus
}

export interface WorkOrderListQuery {
  status?: WorkOrderStatus
  priority?: Priority
  complaint_id?: string
  equipment_id?: string
  limit?: number
  offset?: number
}

export interface ServiceRecord {
  id: string
  equipment_id: string
  work_order_id: string
  technician_id: string
  findings: string | null
  work_performed: string | null
  parts_used: unknown[]
  recorded_at: string
}

export interface ServiceRecordCreateRequest {
  findings?: string | null
  work_performed?: string | null
  parts_used?: unknown[]
}

export interface ServiceRecordUpdateRequest {
  findings?: string | null
  work_performed?: string | null
  parts_used?: unknown[]
}

export interface CompletionReport {
  id: string
  work_order_id: string
  service_record_id: string | null
  summary: string
  evidence_status: EvidenceStatus
  verification_notes: string | null
  submitted_at: string
  verified_at: string | null
}

export interface CompletionReportCreateRequest {
  service_record_id: string
  summary: string
}

export interface CompletionReportUpdateRequest {
  summary?: string
  evidence_status?: EvidenceStatus
  verification_notes?: string | null
}

export interface TechnicianRecommendation {
  technician_id: string
  full_name: string
  eligible: boolean
  matching_skills: string[]
  missing_skills: string[]
  active_workload: number
  availability_status: string
  reasons: string[]
  rank: number
}

export interface WorkOrderProposal {
  id: string
  complaint_id: string
  status: WorkOrderProposalStatus
  title: string
  problem_description: string
  proposed_scope: string
  technical_findings: string
  recommended_actions: string[]
  required_skills: string[]
  required_parts: string[]
  priority: Priority
  estimated_duration_minutes: number | null
  safety_warnings: string[]
  missing_information: string[]
  generation_warnings: string[]
  diagnostic_status: DiagnosticStatus
  diagnostic_summary: string
  diagnostic_snapshot: Record<string, object>
  citations: Citation[]
  requires_escalation: boolean
  escalation_reason: string | null
  technician_recommendations: TechnicianRecommendation[]
  selected_technician_id: string | null
  created_by_id: string | null
  reviewed_by_id: string | null
  reviewed_at: string | null
  rejection_reason: string | null
  resulting_work_order_id: string | null
  resulting_assignment_id: string | null
  created_at: string
  updated_at: string
}

export interface WorkOrderProposalApproveRequest {
  technician_id?: string | null
}

export interface WorkOrderProposalRejectRequest {
  reason: string
}

export interface WorkOrderProposalListQuery {
  status?: WorkOrderProposalStatus
  complaint_id?: string
  limit?: number
  offset?: number
}
