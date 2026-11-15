import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/',
})

const globalObject = globalThis as typeof globalThis & {
  IS_REACT_ACT_ENVIRONMENT?: boolean
}

const window = dom.window as unknown as Window & typeof globalThis

for (const key of [
  'window',
  'document',
  'navigator',
  'HTMLElement',
  'HTMLInputElement',
  'HTMLTextAreaElement',
  'HTMLSelectElement',
  'HTMLFormElement',
  'Element',
  'DocumentFragment',
  'Node',
  'NodeList',
  'Event',
  'MouseEvent',
  'KeyboardEvent',
  'CustomEvent',
  'MutationObserver',
  'SVGElement',
] as const) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    writable: true,
    value: window[key as keyof typeof window],
  })
}

Object.defineProperty(globalThis, 'getComputedStyle', {
  configurable: true,
  writable: true,
  value: window.getComputedStyle.bind(window),
})

Object.defineProperty(globalThis, 'requestAnimationFrame', {
  configurable: true,
  writable: true,
  value: (callback: FrameRequestCallback) => setTimeout(callback, 0),
})

Object.defineProperty(globalThis, 'cancelAnimationFrame', {
  configurable: true,
  writable: true,
  value: (handle: number) => clearTimeout(handle),
})

globalObject.IS_REACT_ACT_ENVIRONMENT = true
