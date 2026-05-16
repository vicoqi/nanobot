import { Routes, Route, Navigate } from "react-router-dom";
import { isLoggedIn } from "@/lib/auth";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import DashboardPage from "@/pages/DashboardPage";
import AgentDetailPage from "@/pages/AgentDetailPage";
import AdminPage from "@/pages/AdminPage";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  return isLoggedIn() ? <>{children}</> : <Navigate to="/login" />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/dashboard" element={<PrivateRoute><DashboardPage /></PrivateRoute>} />
      <Route path="/agent/:id" element={<PrivateRoute><AgentDetailPage /></PrivateRoute>} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="*" element={<Navigate to="/login" />} />
    </Routes>
  );
}
