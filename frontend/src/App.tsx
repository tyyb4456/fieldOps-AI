import { Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { HomePage } from './pages/HomePage'
import { SignInPage } from './pages/SignInPage'
import { SignUpPage } from './pages/SignUpPage'
import { DashboardPage } from './pages/DashboardPage'
import { CustomerPage } from './pages/CustomerPage'
import { TechnicianPage } from './pages/TechnicianPage'
import { AdminPage } from './pages/AdminPage'
import { UnauthorizedPage } from './pages/UnauthorizedPage'
import { NotFoundPage } from './pages/NotFoundPage'

export default function App() {
  return (
    <Routes>
      <Route path="/sign-in/*" element={<SignInPage />} />
      <Route path="/sign-up/*" element={<SignUpPage />} />

      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route
          path="dashboard"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="customer"
          element={
            <ProtectedRoute allowedRoles={['customer']}>
              <CustomerPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="technician"
          element={
            <ProtectedRoute allowedRoles={['technician']}>
              <TechnicianPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="admin"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminPage />
            </ProtectedRoute>
          }
        />
        <Route path="unauthorized" element={<UnauthorizedPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
