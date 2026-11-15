import React from 'react'
import { useLocation } from 'react-router-dom'

export function LocationProbe() {
  const location = useLocation()
  const notice = (location.state as { notice?: unknown } | null)?.notice

  return (
    <div
      data-testid="location"
      data-notice={typeof notice === 'string' ? notice : undefined}
    >
      {location.pathname}
      {location.search}
    </div>
  )
}
