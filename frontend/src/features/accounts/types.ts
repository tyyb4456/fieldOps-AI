import type { UserRole } from '../../lib/api/types.ts'

export interface CurrentUser {
  id: string
  full_name: string
  email: string | null
  phone: string | null
  role: UserRole
  is_active: boolean
  customer_id: string | null
  technician_id: string | null
}
