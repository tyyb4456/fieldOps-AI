export const TECHNICIAN_ROUTES = {
  dashboard: '/technician',
  assignments: '/technician/assignments',
  workOrders: '/technician/work-orders',
  serviceRecords: '/technician/service-records',
  technicalReferences: '/technician/technical-references',
} as const

export function technicianWorkOrderPath(workOrderId: string): string {
  return `${TECHNICIAN_ROUTES.workOrders}/${encodeURIComponent(workOrderId)}`
}

export function technicianServiceRecordPath(serviceRecordId: string): string {
  return `${TECHNICIAN_ROUTES.serviceRecords}/${encodeURIComponent(serviceRecordId)}`
}
