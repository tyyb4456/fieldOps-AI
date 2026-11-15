import type {
  DiagnosticStatus,
} from '../../lib/api/types'
import type { Citation } from '../knowledge/types'

export interface DiagnosticCause {
  cause: string
  basis: string
  evidence_chunk_ids: string[]
}

export interface DiagnosticCheck {
  step: string
  safety_note: string | null
  evidence_chunk_ids: string[]
}

export interface DiagnosticInvestigation {
  complaint_id: string
  status: DiagnosticStatus
  summary: string
  probable_causes: DiagnosticCause[]
  recommended_checks: DiagnosticCheck[]
  missing_information: string[]
  safety_warnings: string[]
  conflicting_evidence_notes: string[]
  requires_escalation: boolean
  escalation_reason: string | null
  citations: Citation[]
  warnings: string[]
  disclaimer: string
}

export interface DiagnosticInvestigationRequest {
  complaint_id: string
  focus?: string | null
}
