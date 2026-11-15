export const ADMIN_ROUTES = {
  dashboard: '/admin',
  complaints: '/admin/complaints',
  workOrders: '/admin/work-orders',
  proposals: '/admin/proposals',
  assignments: '/admin/assignments',
  completionReports: '/admin/completion-reports',
  documents: '/admin/documents',
  technicians: '/admin/technicians',
  customers: '/admin/customers',
  workflows: '/admin/workflows',
} as const

export function adminComplaintPath(complaintId: string): string {
  return `${ADMIN_ROUTES.complaints}/${encodeURIComponent(complaintId)}`
}

export function adminWorkOrderPath(workOrderId: string): string {
  return `${ADMIN_ROUTES.workOrders}/${encodeURIComponent(workOrderId)}`
}

export function adminProposalPath(proposalId: string): string {
  return `${ADMIN_ROUTES.proposals}/${encodeURIComponent(proposalId)}`
}

export function adminCompletionReportPath(
  completionReportId: string,
): string {
  return `${ADMIN_ROUTES.completionReports}/${encodeURIComponent(
    completionReportId,
  )}`
}

export function adminDocumentPath(documentId: string): string {
  return `${ADMIN_ROUTES.documents}/${encodeURIComponent(documentId)}`
}

export function adminCustomerPath(customerId: string): string {
  return `${ADMIN_ROUTES.customers}/${encodeURIComponent(customerId)}`
}

export function adminEquipmentPath(equipmentId: string): string {
  return `/admin/equipment/${encodeURIComponent(equipmentId)}`
}

export function adminWorkflowPath(workflowRunId: string): string {
  return `${ADMIN_ROUTES.workflows}/${encodeURIComponent(workflowRunId)}`
}
