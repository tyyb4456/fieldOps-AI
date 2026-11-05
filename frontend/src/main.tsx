import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { AppAuthProvider } from './auth/AuthProvider.tsx'
import { ClerkRouterProvider } from './auth/ClerkRouterProvider.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ClerkRouterProvider>
        <AppAuthProvider>
          <App />
        </AppAuthProvider>
      </ClerkRouterProvider>
    </BrowserRouter>
  </StrictMode>,
)
