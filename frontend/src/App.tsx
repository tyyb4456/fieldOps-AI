import { Outlet, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { HomePage } from './pages/HomePage'
import { SignInPage } from './pages/SignInPage'
import { SignUpPage } from './pages/SignUpPage'
import { DashboardPage } from './pages/DashboardPage'
import { AdminPage } from './pages/AdminPage'
import { UnauthorizedPage } from './pages/UnauthorizedPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { CustomerDashboardPage } from './features/customers/pages/CustomerDashboardPage'
import { CustomerProfilePage } from './features/customers/pages/CustomerProfilePage'
import { EquipmentListPage } from './features/equipment/pages/EquipmentListPage'
import { EquipmentNewPage } from './features/equipment/pages/EquipmentNewPage'
import { EquipmentDetailPage } from './features/equipment/pages/EquipmentDetailPage'
import { EquipmentEditPage } from './features/equipment/pages/EquipmentEditPage'
import { ComplaintListPage } from './features/complaints/pages/ComplaintListPage'
import { ComplaintNewPage } from './features/complaints/pages/ComplaintNewPage'
import { ComplaintDetailPage } from './features/complaints/pages/ComplaintDetailPage'
import { TechnicianDashboardPage } from './features/technicians/pages/TechnicianDashboardPage'
import { TechnicianAssignmentsPage } from './features/technicians/pages/TechnicianAssignmentsPage'
import { TechnicianWorkOrdersPage } from './features/technicians/pages/TechnicianWorkOrdersPage'
import { TechnicianWorkOrderDetailPage } from './features/technicians/pages/TechnicianWorkOrderDetailPage'
import { TechnicianServiceRecordsPage } from './features/technicians/pages/TechnicianServiceRecordsPage'
import { TechnicianServiceRecordDetailPage } from './features/technicians/pages/TechnicianServiceRecordDetailPage'
import { TechnicianTechnicalReferencesPage } from './features/technicians/pages/TechnicianTechnicalReferencesPage'

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
              <Outlet />
            </ProtectedRoute>
          }
        >
          <Route index element={<CustomerDashboardPage />} />
          <Route path="equipment" element={<EquipmentListPage />} />
          <Route path="equipment/new" element={<EquipmentNewPage />} />
          <Route path="equipment/:equipmentId" element={<EquipmentDetailPage />} />
          <Route
            path="equipment/:equipmentId/edit"
            element={<EquipmentEditPage />}
          />
          <Route path="complaints" element={<ComplaintListPage />} />
          <Route path="complaints/new" element={<ComplaintNewPage />} />
          <Route
            path="complaints/:complaintId"
            element={<ComplaintDetailPage />}
          />
          <Route path="profile" element={<CustomerProfilePage />} />
        </Route>
        <Route
          path="technician"
          element={
            <ProtectedRoute allowedRoles={['technician']}>
              <Outlet />
            </ProtectedRoute>
          }
        >
          <Route index element={<TechnicianDashboardPage />} />
          <Route path="assignments" element={<TechnicianAssignmentsPage />} />
          <Route path="work-orders" element={<TechnicianWorkOrdersPage />} />
          <Route
            path="work-orders/:workOrderId"
            element={<TechnicianWorkOrderDetailPage />}
          />
          <Route
            path="service-records"
            element={<TechnicianServiceRecordsPage />}
          />
          <Route
            path="service-records/:serviceRecordId"
            element={<TechnicianServiceRecordDetailPage />}
          />
          <Route
            path="technical-references"
            element={<TechnicianTechnicalReferencesPage />}
          />
        </Route>
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
