import { resolveApiBaseUrl } from './base-url'

export function configuredApiBaseUrl(): string {
  return resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL, {
    isProduction: import.meta.env.PROD,
  })
}
