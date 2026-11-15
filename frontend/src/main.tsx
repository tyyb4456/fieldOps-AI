import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { AppAuthProvider } from './auth/AuthProvider.tsx'
import { ClerkRouterProvider } from './auth/ClerkRouterProvider.tsx'
import { ApiClientProvider } from './lib/api/ApiClientProvider.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ClerkRouterProvider>
        <ApiClientProvider>
          <AppAuthProvider>
            <App />
          </AppAuthProvider>
        </ApiClientProvider>
      </ClerkRouterProvider>
    </BrowserRouter>
  </StrictMode>,
)
