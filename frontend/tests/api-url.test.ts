import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveApiBaseUrl } from '../src/lib/api-url.ts'

test('uses the localhost fallback in development', () => {
  assert.equal(
    resolveApiBaseUrl(undefined, { isProduction: false }),
    'http://localhost:8000',
  )
})

test('trims trailing slashes from a configured URL', () => {
  assert.equal(
    resolveApiBaseUrl('https://api.example.com///', {
      isProduction: true,
    }),
    'https://api.example.com',
  )
})

test('requires an explicit URL in production', () => {
  assert.throws(
    () =>
      resolveApiBaseUrl(undefined, { isProduction: true }),
    /VITE_API_BASE_URL must be set/,
  )
})

test('rejects a malformed URL', () => {
  assert.throws(
    () =>
      resolveApiBaseUrl('not-a-url', { isProduction: true }),
    /valid absolute/,
  )
})

test('rejects a loopback URL in production', () => {
  assert.throws(
    () =>
      resolveApiBaseUrl('http://localhost:8000', {
        isProduction: true,
      }),
    /loopback address/,
  )
  assert.throws(
    () =>
      resolveApiBaseUrl('http://127.0.0.1:8000', {
        isProduction: true,
      }),
    /loopback address/,
  )
  assert.throws(
    () =>
      resolveApiBaseUrl('http://[::1]:8000', {
        isProduction: true,
      }),
    /loopback address/,
  )
})

test('allows a loopback URL in development', () => {
  assert.equal(
    resolveApiBaseUrl('http://localhost:8080', { isProduction: false }),
    'http://localhost:8080',
  )
})

test('rejects non-http protocols', () => {
  assert.throws(
    () =>
      resolveApiBaseUrl('ftp://api.example.com', {
        isProduction: true,
      }),
    /http or https/,
  )
})

test('rejects embedded credentials', () => {
  assert.throws(
    () =>
      resolveApiBaseUrl('https://user:pass@api.example.com', {
        isProduction: true,
      }),
    /embedded credentials/,
  )
})
