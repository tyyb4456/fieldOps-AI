import type { UserRole } from '../lib/api/types.ts'
import { isUserRole } from '../lib/api/types.ts'

export interface AppNavItem {
  label: string
  to: string
  roles: readonly UserRole[]
  end?: boolean
}

export const APP_NAV_ITEMS: readonly AppNavItem[] = [
  {
    label: 'Dashboard',
    to: '/dashboard',
    roles: ['customer', 'technician', 'admin'],
  },
  {
    label: 'Customer workspace',
    to: '/customer',
    roles: ['customer'],
  },
  {
    label: 'Technician workspace',
    to: '/technician',
    roles: ['technician'],
  },
  {
    label: 'Administrator workspace',
    to: '/admin',
    roles: ['admin'],
  },
]

const ROLE_LABELS: Record<UserRole, string> = {
  customer: 'Customer',
  technician: 'Technician',
  admin: 'Administrator',
}

const ROLE_HOME_PATHS: Record<UserRole, string> = {
  customer: '/customer',
  technician: '/technician',
  admin: '/admin',
}

export function navigationForRole(
  role: UserRole | null | undefined,
): AppNavItem[] {
  if (!isUserRole(role)) {
    return []
  }

  return APP_NAV_ITEMS.filter((item) => item.roles.includes(role))
}

export function homePathForRole(
  role: UserRole | null | undefined,
): string | null {
  if (!isUserRole(role)) {
    return null
  }
  return ROLE_HOME_PATHS[role]
}

export function roleLabel(role: UserRole | null | undefined): string | null {
  if (!isUserRole(role)) {
    return null
  }
  return ROLE_LABELS[role]
}
