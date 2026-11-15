import { Badge } from '../../../components/Badge'
import type { ComplaintStatus, Priority } from '../../../lib/api/types'
import {
  complaintStatusLabel,
  complaintStatusTone,
  priorityLabel,
  priorityTone,
} from '../labels'

export function ComplaintStatusBadge({ status }: { status: ComplaintStatus }) {
  return (
    <Badge tone={complaintStatusTone(status)}>
      {complaintStatusLabel(status)}
    </Badge>
  )
}

export function PriorityBadge({ priority }: { priority: Priority }) {
  return <Badge tone={priorityTone(priority)}>{priorityLabel(priority)}</Badge>
}
