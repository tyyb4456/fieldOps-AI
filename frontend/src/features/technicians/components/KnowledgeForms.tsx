import { useRef, useState, type FormEvent } from 'react'
import { FormError } from '../../../components/Feedback'
import {
  FormField,
  inputClassName,
} from '../../../components/FormField'
import { createSubmissionGuard } from '../../../lib/forms/submission-guard'
import type { FieldErrors } from '../../../lib/forms/validation'
import type {
  KnowledgeAnswerRequest,
  RetrievalSearchRequest,
} from '../../knowledge/types'

const TEXT_MAX_LENGTH = 2000
const FILTER_MAX_LENGTH = 150

const TOP_K_OPTIONS = [5, 10, 20]

function FilterFields({
  manufacturer,
  model,
  topK,
  onManufacturer,
  onModel,
  onTopK,
  idPrefix,
}: {
  manufacturer: string
  model: string
  topK: number
  onManufacturer: (value: string) => void
  onModel: (value: string) => void
  onTopK: (value: number) => void
  idPrefix: string
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <FormField
        id={`${idPrefix}-manufacturer`}
        label="Manufacturer"
        hint="Optional."
      >
        <input
          id={`${idPrefix}-manufacturer`}
          className={inputClassName}
          value={manufacturer}
          maxLength={FILTER_MAX_LENGTH}
          onChange={(event) => onManufacturer(event.target.value)}
        />
      </FormField>

      <FormField id={`${idPrefix}-model`} label="Model" hint="Optional.">
        <input
          id={`${idPrefix}-model`}
          className={inputClassName}
          value={model}
          maxLength={FILTER_MAX_LENGTH}
          onChange={(event) => onModel(event.target.value)}
        />
      </FormField>

      <FormField id={`${idPrefix}-top-k`} label="Results" hint="1 to 20.">
        <select
          id={`${idPrefix}-top-k`}
          className={inputClassName}
          value={String(topK)}
          onChange={(event) => onTopK(Number(event.target.value))}
        >
          {TOP_K_OPTIONS.map((option) => (
            <option key={option} value={String(option)}>
              {option}
            </option>
          ))}
        </select>
      </FormField>
    </div>
  )
}

export function KnowledgeSearchForm({
  isSearching,
  onSearch,
}: {
  isSearching: boolean
  onSearch: (payload: RetrievalSearchRequest) => Promise<void>
}) {
  const [query, setQuery] = useState('')
  const [manufacturer, setManufacturer] = useState('')
  const [model, setModel] = useState('')
  const [topK, setTopK] = useState(5)
  const [errors, setErrors] = useState<FieldErrors>({})
  const guardRef = useRef(createSubmissionGuard())

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!guardRef.current.begin()) {
      return
    }

    const trimmed = query.trim()
    const nextErrors: FieldErrors = {}
    if (!trimmed) {
      nextErrors.query = 'Enter a search query.'
    } else if (trimmed.length > TEXT_MAX_LENGTH) {
      nextErrors.query = `Query must be ${TEXT_MAX_LENGTH} characters or fewer.`
    }
    if (manufacturer.length > FILTER_MAX_LENGTH) {
      nextErrors.manufacturer = `Manufacturer must be ${FILTER_MAX_LENGTH} characters or fewer.`
    }
    if (model.length > FILTER_MAX_LENGTH) {
      nextErrors.model = `Model must be ${FILTER_MAX_LENGTH} characters or fewer.`
    }

    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) {
      guardRef.current.end()
      return
    }

    try {
      await onSearch({
        query: trimmed,
        manufacturer: manufacturer.trim() || null,
        model: model.trim() || null,
        top_k: topK,
      })
    } finally {
      guardRef.current.end()
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-4">
      <FormError message={errors.query ?? null} />

      <FormField
        id="knowledge-search-query"
        label="Search technical documents"
        required
        hint="Search active indexed manuals and technical documents."
      >
        <textarea
          id="knowledge-search-query"
          className={`${inputClassName} min-h-24 resize-y`}
          value={query}
          maxLength={TEXT_MAX_LENGTH}
          required
          aria-invalid={errors.query ? true : undefined}
          onChange={(event) => setQuery(event.target.value)}
        />
      </FormField>

      <FilterFields
        manufacturer={manufacturer}
        model={model}
        topK={topK}
        onManufacturer={setManufacturer}
        onModel={setModel}
        onTopK={setTopK}
        idPrefix="knowledge-search"
      />

      <FormError message={errors.manufacturer ?? errors.model ?? null} />

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSearching}
          className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSearching ? 'Searching...' : 'Search documents'}
        </button>
      </div>
    </form>
  )
}

export function KnowledgeAnswerForm({
  isAnswering,
  onAnswer,
}: {
  isAnswering: boolean
  onAnswer: (payload: KnowledgeAnswerRequest) => Promise<void>
}) {
  const [question, setQuestion] = useState('')
  const [manufacturer, setManufacturer] = useState('')
  const [model, setModel] = useState('')
  const [topK, setTopK] = useState(5)
  const [errors, setErrors] = useState<FieldErrors>({})
  const guardRef = useRef(createSubmissionGuard())

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!guardRef.current.begin()) {
      return
    }

    const trimmed = question.trim()
    const nextErrors: FieldErrors = {}
    if (!trimmed) {
      nextErrors.question = 'Enter a question.'
    } else if (trimmed.length > TEXT_MAX_LENGTH) {
      nextErrors.question = `Question must be ${TEXT_MAX_LENGTH} characters or fewer.`
    }
    if (manufacturer.length > FILTER_MAX_LENGTH) {
      nextErrors.manufacturer = `Manufacturer must be ${FILTER_MAX_LENGTH} characters or fewer.`
    }
    if (model.length > FILTER_MAX_LENGTH) {
      nextErrors.model = `Model must be ${FILTER_MAX_LENGTH} characters or fewer.`
    }

    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) {
      guardRef.current.end()
      return
    }

    try {
      await onAnswer({
        question: trimmed,
        manufacturer: manufacturer.trim() || null,
        model: model.trim() || null,
        top_k: topK,
      })
    } finally {
      guardRef.current.end()
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-4">
      <FormError message={errors.question ?? null} />

      <FormField
        id="knowledge-answer-question"
        label="Ask a technical question"
        required
        hint="The answer is grounded in active indexed documents and includes citations."
      >
        <textarea
          id="knowledge-answer-question"
          className={`${inputClassName} min-h-24 resize-y`}
          value={question}
          maxLength={TEXT_MAX_LENGTH}
          required
          aria-invalid={errors.question ? true : undefined}
          onChange={(event) => setQuestion(event.target.value)}
        />
      </FormField>

      <FilterFields
        manufacturer={manufacturer}
        model={model}
        topK={topK}
        onManufacturer={setManufacturer}
        onModel={setModel}
        onTopK={setTopK}
        idPrefix="knowledge-answer"
      />

      <FormError message={errors.manufacturer ?? errors.model ?? null} />

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isAnswering}
          className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isAnswering ? 'Answering...' : 'Get grounded answer'}
        </button>
      </div>
    </form>
  )
}
