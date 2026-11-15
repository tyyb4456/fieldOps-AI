import type { AnswerStatus } from '../../lib/api/types'

export interface Citation {
  source_id: string
  chunk_id: string
  document_id: string
  document_name: string
  manufacturer: string
  model: string
  version: string | null
  page_number: number | null
  chunk_index: number
  excerpt: string
}

export interface RetrievalSearchRequest {
  query: string
  manufacturer?: string | null
  model?: string | null
  top_k?: number
}

export interface RetrievalResult {
  chunk_id: string
  document_id: string
  document_name: string
  manufacturer: string
  model: string
  version: string | null
  page_number: number | null
  chunk_index: number
  content: string
  distance: number
  similarity: number
}

export interface RetrievalSearchResponse {
  items: RetrievalResult[]
  top_k: number
}

export interface KnowledgeAnswerRequest {
  question: string
  manufacturer?: string | null
  model?: string | null
  top_k?: number
}

export interface KnowledgeAnswer {
  answer: string
  status: AnswerStatus
  citations: Citation[]
  evidence_summary: string | null
  insufficient_evidence: boolean
  missing_information: string[]
  warnings: string[]
}
