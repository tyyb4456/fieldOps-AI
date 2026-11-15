import { Badge } from '../../../components/Badge'
import type {
  DiagnosticStatus,
  IngestionStatus,
  WorkOrderProposalStatus,
  WorkflowRunStatus,
} from '../../../lib/api/types'
import {
  diagnosticStatusLabel,
  diagnosticStatusTone,
  ingestionStatusLabel,
  ingestionStatusTone,
  proposalStatusLabel,
  proposalStatusTone,
  workflowStatusLabel,
  workflowStatusTone,
} from '../labels'

export function ProposalStatusBadge({
  status,
}: {
  status: WorkOrderProposalStatus
}) {
  return (
    <Badge tone={proposalStatusTone(status)}>
      {proposalStatusLabel(status)}
    </Badge>
  )
}

export function WorkflowStatusBadge({
  status,
}: {
  status: WorkflowRunStatus
}) {
  return (
    <Badge tone={workflowStatusTone(status)}>
      {workflowStatusLabel(status)}
    </Badge>
  )
}

export function IngestionStatusBadge({
  status,
}: {
  status: IngestionStatus
}) {
  return (
    <Badge tone={ingestionStatusTone(status)}>
      {ingestionStatusLabel(status)}
    </Badge>
  )
}

export function DiagnosticStatusBadge({
  status,
}: {
  status: DiagnosticStatus
}) {
  return (
    <Badge tone={diagnosticStatusTone(status)}>
      {diagnosticStatusLabel(status)}
    </Badge>
  )
}

export function ActiveBadge({ isActive }: { isActive: boolean }) {
  return (
    <Badge tone={isActive ? 'success' : 'neutral'}>
      {isActive ? 'Active' : 'Inactive'}
    </Badge>
  )
}

export function AvailabilityBadge({ isAvailable }: { isAvailable: boolean }) {
  return (
    <Badge tone={isAvailable ? 'success' : 'neutral'}>
      {isAvailable ? 'Available' : 'Unavailable'}
    </Badge>
  )
}

export function RecordStatusBadge({
  label,
  tone,
}: {
  label: string
  tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger'
}) {
  return <Badge tone={tone}>{label}</Badge>
}
