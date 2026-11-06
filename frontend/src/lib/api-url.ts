const LOCAL_API_BASE_URL = 'http://localhost:8000'

function isLoopbackHost(hostname: string): boolean {
  const host = hostname.replace(/^\[|\]$/g, '').toLowerCase()
  if (host === 'localhost' || host === '::1' || host === '0.0.0.0') {
    return true
  }
  return /^127\./.test(host)
}

export interface ApiBaseUrlOptions {
  isProduction: boolean
}

export function resolveApiBaseUrl(
  rawBaseUrl: string | undefined,
  { isProduction }: ApiBaseUrlOptions,
): string {
  const trimmed = rawBaseUrl?.trim()

  if (!trimmed) {
    if (isProduction) {
      throw new Error(
        'VITE_API_BASE_URL must be set to the production API origin. ' +
          'The localhost fallback is only available in development.',
      )
    }
    return LOCAL_API_BASE_URL
  }

  let parsed: URL
  try {
    parsed = new URL(trimmed)
  } catch {
    throw new Error(
      'VITE_API_BASE_URL must be a valid absolute http(s) URL.',
    )
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error(
      'VITE_API_BASE_URL must use the http or https protocol.',
    )
  }

  if (isProduction && isLoopbackHost(parsed.hostname)) {
    throw new Error(
      'VITE_API_BASE_URL must not point to a loopback address in ' +
        'production. The localhost fallback is only available in development.',
    )
  }

  if (parsed.username || parsed.password) {
    throw new Error(
      'VITE_API_BASE_URL must not contain embedded credentials.',
    )
  }

  return trimmed.replace(/\/+$/, '')
}
