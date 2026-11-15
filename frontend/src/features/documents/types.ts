import type { IngestionStatus } from '../../lib/api/types'

export interface DocumentMetadata {
  id: string
  manufacturer: string
  model: string
  document_name: string
  version: string | null
  original_filename: string | null
  content_type: string | null
  byte_size: number | null
  checksum_sha256: string | null
  uploaded_by_id: string | null
  ingestion_status: IngestionStatus
  ingestion_error: string | null
  ingested_at: string | null
  is_active: boolean
  created_at: string
}

export interface DocumentUpdateRequest {
  manufacturer?: string
  model?: string
  document_name?: string
  version?: string | null
}

export interface DocumentUploadFields {
  file: File
  manufacturer: string
  model: string
  document_name: string
  version?: string | null
}

export interface DocumentChunk {
  id: string
  document_id: string
  chunk_index: number
  content: string
  page_number: number | null
  metadata: Record<string, unknown>
}

export interface DocumentListQuery {
  manufacturer?: string
  model?: string
  equipment_id?: string
  is_active?: boolean
  limit?: number
  offset?: number
}
