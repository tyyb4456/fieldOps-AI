export interface Equipment {
  id: string
  customer_id: string
  manufacturer: string
  model: string
  serial_number: string | null
  equipment_type: string
  installation_date: string | null
  created_at: string
}

export interface EquipmentCreateRequest {
  manufacturer: string
  model: string
  serial_number?: string | null
  equipment_type: string
  installation_date?: string | null
}

export interface EquipmentUpdateRequest {
  manufacturer?: string
  model?: string
  serial_number?: string | null
  equipment_type?: string
  installation_date?: string | null
}

export interface EquipmentListQuery {
  equipment_type?: string
  limit?: number
  offset?: number
}
