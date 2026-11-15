export const CUSTOMER_ROUTES = {
  dashboard: '/customer',
  equipment: '/customer/equipment',
  newEquipment: '/customer/equipment/new',
  complaints: '/customer/complaints',
  newComplaint: '/customer/complaints/new',
  profile: '/customer/profile',
} as const

export function customerEquipmentPath(equipmentId: string): string {
  return `${CUSTOMER_ROUTES.equipment}/${encodeURIComponent(equipmentId)}`
}

export function customerEquipmentEditPath(equipmentId: string): string {
  return `${customerEquipmentPath(equipmentId)}/edit`
}

export function customerComplaintPath(complaintId: string): string {
  return `${CUSTOMER_ROUTES.complaints}/${encodeURIComponent(complaintId)}`
}
