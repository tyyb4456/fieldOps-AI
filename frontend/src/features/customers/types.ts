export interface CustomerProfile {
  id: string
  full_name: string
  email: string | null
  phone: string | null
  address: string | null
  preferred_language: string | null
  is_active: boolean
  created_at: string
}

export interface CustomerUpdateRequest {
  address?: string | null
  preferred_language?: string | null
}
