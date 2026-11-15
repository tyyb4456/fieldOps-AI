import { Badge } from '../../../components/Badge'
import type { AssignmentStatus, EvidenceStatus, WorkOrderStatus } from '../../../lib/api/types'
import {
  assignmentStatusLabel,
  assignmentStatusTone,
  evidenceStatusLabel,
  evidenceStatusTone,
  workOrderStatusLabel,
  workOrderStatusTone,
} from '../labels'

export function WorkOrderStatusBadge({
  status,
}: {
  status: WorkOrderStatus
}) {
  return (
    <Badge tone={workOrderStatusTone(status)}>
      {workOrderStatusLabel(status)}
    </Badge>
  )
}

export function AssignmentStatusBadge({
  status,
}: {
  status: AssignmentStatus
}) {
  return (
    <Badge tone={assignmentStatusTone(status)}>
      {assignmentStatusLabel(status)}
    </Badge>
  )
}

export function EvidenceStatusBadge({
  status,
}: {
  status: EvidenceStatus
}) {
  return (
    <Badge tone={evidenceStatusTone(status)}>
      {evidenceStatusLabel(status)}
    </Badge>
  )
}
