import React from 'react'
import { useLocation } from 'react-router-dom'

export function LocationProbe() {
  const location = useLocation()

  return (
    <div data-testid="location">
      {location.pathname}
      {location.search}
    </div>
  )
}
