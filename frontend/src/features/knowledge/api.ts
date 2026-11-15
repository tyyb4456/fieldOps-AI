import type { ApiClient } from '../../lib/api/client.ts'
import { ApiError } from '../../lib/api/errors.ts'
import {
  isRecord,
  optionalString,
  requireArray,
  requireBoolean,
  requireNumber,
  requireString,
} from '../../lib/api/parse.ts'
import { isAnswerStatus } from '../../lib/api/types.ts'
import type {
  Citation,
  KnowledgeAnswer,
  KnowledgeAnswerRequest,
  RetrievalResult,
  RetrievalSearchRequest,
  RetrievalSearchResponse,
} from './types'

export function parseRetrievalResult(payload: unknown): RetrievalResult {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid knowledge-search result.',
    )
  }

  return {
    chunk_id: requireString(payload.chunk_id, 'chunk_id'),
    document_id: requireString(payload.document_id, 'document_id'),
    document_name: requireString(payload.document_name, 'document_name'),
    manufacturer: requireString(payload.manufacturer, 'manufacturer'),
    model: requireString(payload.model, 'model'),
    version: optionalString(payload.version, 'version'),
    page_number:
      payload.page_number === null || payload.page_number === undefined
        ? null
        : requireNumber(payload.page_number, 'page_number'),
    chunk_index: requireNumber(payload.chunk_index, 'chunk_index'),
    content: requireString(payload.content, 'content'),
    distance: requireNumber(payload.distance, 'distance'),
    similarity: requireNumber(payload.similarity, 'similarity'),
  }
}

export function parseRetrievalSearchResponse(
  payload: unknown,
): RetrievalSearchResponse {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid knowledge-search response.',
    )
  }

  return {
    items: requireArray(payload.items, 'items').map(parseRetrievalResult),
    top_k: requireNumber(payload.top_k, 'top_k'),
  }
}

export async function searchKnowledge(
  client: ApiClient,
  data: RetrievalSearchRequest,
): Promise<RetrievalSearchResponse> {
  const payload = await client.post<unknown>('/api/v1/knowledge/search', {
    json: data,
  })
  return parseRetrievalSearchResponse(payload)
}

export function parseCitation(payload: unknown): Citation {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid citation.',
    )
  }

  return {
    source_id: requireString(payload.source_id, 'source_id'),
    chunk_id: requireString(payload.chunk_id, 'chunk_id'),
    document_id: requireString(payload.document_id, 'document_id'),
    document_name: requireString(payload.document_name, 'document_name'),
    manufacturer: requireString(payload.manufacturer, 'manufacturer'),
    model: requireString(payload.model, 'model'),
    version: optionalString(payload.version, 'version'),
    page_number:
      payload.page_number === null || payload.page_number === undefined
        ? null
        : requireNumber(payload.page_number, 'page_number'),
    chunk_index: requireNumber(payload.chunk_index, 'chunk_index'),
    excerpt: requireString(payload.excerpt, 'excerpt'),
  }
}

export function parseKnowledgeAnswer(payload: unknown): KnowledgeAnswer {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid knowledge-answer response.',
    )
  }

  if (!isAnswerStatus(payload.status)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid knowledge-answer status.',
    )
  }

  return {
    answer: requireString(payload.answer, 'answer'),
    status: payload.status,
    citations: requireArray(payload.citations, 'citations').map(parseCitation),
    evidence_summary: optionalString(
      payload.evidence_summary,
      'evidence_summary',
    ),
    insufficient_evidence: requireBoolean(
      payload.insufficient_evidence,
      'insufficient_evidence',
    ),
    missing_information: requireArray(
      payload.missing_information ?? [],
      'missing_information',
    ).map((item) => String(item)),
    warnings: requireArray(payload.warnings ?? [], 'warnings').map((item) =>
      String(item),
    ),
  }
}

export async function answerKnowledge(
  client: ApiClient,
  data: KnowledgeAnswerRequest,
): Promise<KnowledgeAnswer> {
  const payload = await client.post<unknown>('/api/v1/knowledge/answer', {
    json: data,
  })
  return parseKnowledgeAnswer(payload)
}
