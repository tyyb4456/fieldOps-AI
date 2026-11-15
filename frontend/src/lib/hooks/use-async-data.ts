import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
} from 'react'
import { isAbortError } from '../api/errors.ts'

export interface AsyncDataState<T> {
  data: T | null
  error: unknown
  isLoading: boolean
  reload: () => void
  setData: (data: T | null) => void
}

interface InternalState<T> {
  data: T | null
  error: unknown
  isLoading: boolean
}

type AsyncAction<T> =
  | { type: 'start' }
  | { type: 'success'; data: T }
  | { type: 'error'; error: unknown }
  | { type: 'setData'; data: T | null }

function asyncDataReducer<T>(
  state: InternalState<T>,
  action: AsyncAction<T>,
): InternalState<T> {
  switch (action.type) {
    case 'start':
      return { data: null, error: null, isLoading: true }
    case 'success':
      return { data: action.data, error: null, isLoading: false }
    case 'error':
      return { data: null, error: action.error, isLoading: false }
    case 'setData':
      return { ...state, data: action.data }
  }
}

export function useAsyncData<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
): AsyncDataState<T> {
  const loaderRef = useRef(loader)
  const [state, dispatch] = useReducer(asyncDataReducer<T>, {
    data: null,
    error: null,
    isLoading: true,
  })
  const [reloadKey, setReloadKey] = useState(0)

  const reload = useCallback(() => {
    setReloadKey((key) => key + 1)
  }, [])

  const setData = useCallback((data: T | null) => {
    dispatch({ type: 'setData', data })
  }, [])

  useEffect(() => {
    loaderRef.current = loader
  })

  useEffect(() => {
    const controller = new AbortController()
    let active = true

    dispatch({ type: 'start' })

    loaderRef
      .current(controller.signal)
      .then((next) => {
        if (!active) {
          return
        }
        dispatch({ type: 'success', data: next })
      })
      .catch((caught: unknown) => {
        if (!active || isAbortError(caught)) {
          return
        }
        dispatch({ type: 'error', error: caught })
      })

    return () => {
      active = false
      controller.abort()
    }
    // Caller-supplied dependency values are spread deliberately: they describe
    // the loader's inputs and may vary in name between feature pages.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadKey, ...deps])

  return {
    data: state.data,
    error: state.error,
    isLoading: state.isLoading,
    reload,
    setData,
  }
}
