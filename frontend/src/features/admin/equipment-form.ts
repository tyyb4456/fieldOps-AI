import type { EquipmentFormValues } from './validation'

export function equipmentToFormValues(equipment: {
  manufacturer: string
  model: string
  serial_number: string | null
  equipment_type: string
  installation_date: string | null
}): EquipmentFormValues {
  return {
    manufacturer: equipment.manufacturer,
    model: equipment.model,
    serialNumber: equipment.serial_number ?? '',
    equipmentType: equipment.equipment_type,
    installationDate: equipment.installation_date ?? '',
  }
}

export const EMPTY_EQUIPMENT_FORM: EquipmentFormValues = {
  manufacturer: '',
  model: '',
  serialNumber: '',
  equipmentType: '',
  installationDate: '',
}
