import { useState } from 'react'
import { Badge } from '../../../components/Badge'
import { EmptyState } from '../../../components/EmptyState'
import { FormError, InlineWarning } from '../../../components/Feedback'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { formatSymptom } from '../../../lib/format'
import {
  answerKnowledge,
  searchKnowledge,
} from '../../knowledge/api'
import type {
  KnowledgeAnswer,
  KnowledgeAnswerRequest,
  RetrievalSearchRequest,
  RetrievalSearchResponse,
} from '../../knowledge/types'
import {
  KnowledgeAnswerForm,
  KnowledgeSearchForm,
} from '../components/KnowledgeForms'
import { knowledgeErrorMessage } from '../errors'
import { answerStatusLabel, answerStatusTone } from '../labels'

function CitationCard({
  eyebrow,
  title,
  details,
  content,
}: {
  eyebrow: string
  title: string
  details: string
  content: string
}) {
  return (
    <li className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-sky-400">
        {eyebrow}
      </p>
      <h3 className="mt-1 text-sm font-semibold text-white">{title}</h3>
      <p className="mt-1 text-xs text-slate-500">{details}</p>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-200">
        {content}
      </p>
    </li>
  )
}

export function TechnicianTechnicalReferencesPage() {
  const apiClient = useApiClient()
  const [searchResult, setSearchResult] =
    useState<RetrievalSearchResponse | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [isSearching, setIsSearching] = useState(false)
  const [answer, setAnswer] = useState<KnowledgeAnswer | null>(null)
  const [answerError, setAnswerError] = useState<string | null>(null)
  const [isAnswering, setIsAnswering] = useState(false)

  async function runSearch(payload: RetrievalSearchRequest) {
    setIsSearching(true)
    setSearchError(null)
    try {
      const result = await searchKnowledge(apiClient, payload)
      setSearchResult(result)
    } catch (caught) {
      setSearchResult(null)
      setSearchError(knowledgeErrorMessage(caught))
    } finally {
      setIsSearching(false)
    }
  }

  async function runAnswer(payload: KnowledgeAnswerRequest) {
    setIsAnswering(true)
    setAnswerError(null)
    try {
      const result = await answerKnowledge(apiClient, payload)
      setAnswer(result)
    } catch (caught) {
      setAnswer(null)
      setAnswerError(knowledgeErrorMessage(caught))
    } finally {
      setIsAnswering(false)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Technical references"
        title="Search technical documentation"
        description="Search active indexed manuals, bulletins, and technical documents, or ask for a grounded answer with citations."
      />

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">
          Document search
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          Results come from the indexed knowledge base and include source
          details for review.
        </p>
        <div className="mt-4">
          <KnowledgeSearchForm
            isSearching={isSearching}
            onSearch={runSearch}
          />
        </div>

        <div className="mt-5">
          <FormError message={searchError} />
          {searchResult === null ? (
            searchError === null ? (
              <p className="text-sm text-slate-500">
                Enter a query to search the technical knowledge base.
              </p>
            ) : null
          ) : searchResult.items.length === 0 ? (
            <EmptyState
              title="No matching documents"
              description="Try broadening the query or removing the manufacturer or model filter."
            />
          ) : (
            <>
              <p className="text-xs text-slate-500">
                {searchResult.items.length} result
                {searchResult.items.length === 1 ? '' : 's'} returned
              </p>
              <ul className="mt-3 grid gap-3">
                {searchResult.items.map((item) => (
                  <CitationCard
                    key={item.chunk_id}
                    eyebrow={`Passage ${item.chunk_index + 1}`}
                    title={item.document_name}
                    details={[
                      `${item.manufacturer} ${item.model}`,
                      item.version ? `Version ${item.version}` : null,
                      item.page_number ? `Page ${item.page_number}` : null,
                      `Similarity ${item.similarity.toFixed(3)}`,
                    ]
                      .filter((value) => value !== null)
                      .join(' - ')}
                    content={item.content}
                  />
                ))}
              </ul>
            </>
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">Grounded answer</h2>
        <p className="mt-1 text-sm text-slate-400">
          Answers are generated only from retrieved technical documents. Treat
          them as reference material, not an automatic diagnosis.
        </p>
        <div className="mt-4">
          <KnowledgeAnswerForm
            isAnswering={isAnswering}
            onAnswer={runAnswer}
          />
        </div>

        <div className="mt-5">
          <FormError message={answerError} />
          {answer === null ? (
            answerError === null ? (
              <p className="text-sm text-slate-500">
                Ask a question to generate a cited answer.
              </p>
            ) : null
          ) : (
            <div className="grid gap-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={answerStatusTone(answer.status)}>
                  {answerStatusLabel(answer.status)}
                </Badge>
                {answer.insufficient_evidence ? (
                  <span className="text-xs text-amber-300">
                    Evidence may be insufficient for this question.
                  </span>
                ) : null}
              </div>

              <p className="whitespace-pre-wrap text-sm leading-7 text-slate-100">
                {answer.answer}
              </p>

              {answer.evidence_summary ? (
                <p className="text-sm leading-6 text-slate-400">
                  {answer.evidence_summary}
                </p>
              ) : null}

              {answer.missing_information.length > 0 ? (
                <InlineWarning>
                  <p className="font-medium">Missing information</p>
                  <ul className="mt-1 list-disc space-y-1 pl-5">
                    {answer.missing_information.map((item, index) => (
                      <li key={`${index}-${item}`}>{formatSymptom(item)}</li>
                    ))}
                  </ul>
                </InlineWarning>
              ) : null}

              {answer.warnings.length > 0 ? (
                <InlineWarning>
                  <p className="font-medium">Warnings</p>
                  <ul className="mt-1 list-disc space-y-1 pl-5">
                    {answer.warnings.map((item, index) => (
                      <li key={`${index}-${item}`}>{formatSymptom(item)}</li>
                    ))}
                  </ul>
                </InlineWarning>
              ) : null}

              <div>
                <h3 className="text-sm font-semibold text-slate-200">
                  Citations
                </h3>
                {answer.citations.length === 0 ? (
                  <p className="mt-2 text-sm text-slate-400">
                    No citations were returned for this answer.
                  </p>
                ) : (
                  <ul className="mt-2 grid gap-3">
                    {answer.citations.map((citation) => (
                      <CitationCard
                        key={citation.source_id}
                        eyebrow={`Source ${citation.source_id}`}
                        title={citation.document_name}
                        details={[
                          `${citation.manufacturer} ${citation.model}`,
                          citation.version
                            ? `Version ${citation.version}`
                            : null,
                          citation.page_number
                            ? `Page ${citation.page_number}`
                            : null,
                        ]
                          .filter((value) => value !== null)
                          .join(' - ')}
                        content={citation.excerpt}
                      />
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>
      </section>

      <p className="text-xs leading-5 text-slate-500">
        Knowledge search and answers are operational reference tools. They do
        not create service records, change work-order status, or replace the
        service team&apos;s verification process.
      </p>
    </div>
  )
}
