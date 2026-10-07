import React from "react";
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import AuthPage, { ForgotPasswordPage, ResetPasswordPage } from "./AuthPage.jsx";
import UserDashboard from "./UserDashboard.jsx";
import LandingPage from "./screens/LandingPage.jsx";
import { RequireRole, StudentLayout, TeacherLayout, CoordinatorLayout } from "./routing/RoleLayouts.jsx";
import AdminRoutes from "./routing/RolePages.jsx";
import * as AdminScreens from "./screens/AdminScreens.jsx";
import { getRoleHome } from "./routing/roles.js";
import { supabase } from "./services/supabaseClient.js";

function App() {
  const [session, setSession] = useState(null);
  const [authReady, setAuthReady] = useState(!supabase);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!supabase) return undefined;
    let active = true;
    const loadProfile = async (authSession) => {
      if (!authSession?.user) { if (active) setSession(null); return { success: false }; }
      const { data, error } = await supabase.from("profiles").select("email, full_name, role, status").eq("id", authSession.user.id).single();
      if (error || data?.status !== "active" || !getRoleHome(data?.role)) {
        if (active) setSession(null);
        return { success: false, message: data?.status === "pending" ? "Your account is awaiting administrator activation." : "Your account is not authorized to access QueMe." };
      }
      const nextSession = { email: data.email, name: data.full_name || authSession.user.email, role: data.role };
      if (active) setSession(nextSession);
      return { success: true };
    };
    supabase.auth.getSession().then(({ data }) => loadProfile(data.session)).finally(() => active && setAuthReady(true));
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, authSession) => {
      if (event === "SIGNED_OUT" || event === "TOKEN_REFRESH_FAILED") setSession(null);
      else if (event === "SIGNED_IN" || event === "TOKEN_REFRESHED" || event === "USER_UPDATED") loadProfile(authSession);
    });
    return () => { active = false; subscription.unsubscribe(); };
  }, []);

  const handleLogin = async (authSession) => {
    if (!supabase) return { success: false, message: "Authentication is not configured." };
    const { data, error } = await supabase.from("profiles").select("email, full_name, role, status").eq("id", authSession.user.id).single();
    if (error || data?.status !== "active" || !getRoleHome(data?.role)) return { success: false, message: data?.status === "pending" ? "Your account is awaiting administrator activation." : "Your account is not authorized." };
    setSession({ email: data.email, name: data.full_name || authSession.user.email, role: data.role });
    navigate(getRoleHome(data.role), { replace: true });
    return { success: true };
  };

  const handleLogout = () => {
    supabase?.auth.signOut();
    setSession(null);
    navigate("/login", { replace: true });
  };

  const isAuthenticated = Boolean(session);

  const isPublicPath = (path) =>
    path === "/"
    || ["/login", "/signup", "/forgot-password"].includes(path)
    || (import.meta.env.DEV && (path === "/design" || path.startsWith("/design/")));

  useEffect(() => {
    if (!isAuthenticated) {
      if (!isPublicPath(location.pathname)) {
        navigate("/login", { replace: true });
      }
      return;
    }

    if (["/", "/login", "/signup", "/forgot-password"].includes(location.pathname)) {
      navigate(getRoleHome(session.role) || "/login", { replace: true });
      return;
    }

  }, [isAuthenticated, session, location.pathname, navigate]);

  if (!authReady) return null;
  return (
    <Routes>
      <Route path="/" element={isAuthenticated ? <Navigate to={getRoleHome(session.role) || "/login"} replace /> : <LandingPage onLogin={() => navigate("/login")} onSignup={() => navigate("/signup")} />} />
      <Route path="/login" element={isAuthenticated ? <Navigate to={getRoleHome(session.role) || "/login"} replace /> : <AuthPage onLogin={handleLogin} />} />
      <Route path="/signup" element={isAuthenticated ? <Navigate to={getRoleHome(session.role) || "/login"} replace /> : <AuthPage mode="signup" onLogin={handleLogin} />} />
      <Route path="/forgot-password" element={isAuthenticated ? <Navigate to={getRoleHome(session.role) || "/login"} replace /> : <ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/auth/callback" element={<Navigate to="/login" replace />} />

      <Route element={<RequireRole session={session} allowedRole="student" />}>
        <Route element={<StudentLayout />}>
          <Route path="/student" element={<UserDashboard onLogout={handleLogout} />} />
        </Route>
      </Route>
      <Route element={<RequireRole session={session} allowedRole="teacher" />}>
        <Route element={<TeacherLayout />}>
          <Route path="/teacher" element={<AdminScreens.TeacherScreen onLogout={handleLogout} />} />
        </Route>
      </Route>
      <Route element={<RequireRole session={session} allowedRole="coordinator" />}>
        <Route element={<CoordinatorLayout />}>
          <Route path="/coordinator" element={<AdminScreens.CoordinatorScreen onLogout={handleLogout} />} />
        </Route>
      </Route>
      <Route element={<RequireRole session={session} allowedRole="admin" />}>
        <Route element={<AdminRoutes />}>
          <Route path="/admin" element={<AdminScreens.AdminDashboard onLogout={handleLogout} />} />
          <Route path="/admin/accounts" element={<AdminScreens.AdminAccounts onLogout={handleLogout} />} />
          <Route path="/admin/invitations" element={<AdminScreens.AdminInvitations onLogout={handleLogout} />} />
          <Route path="/admin/academic" element={<AdminScreens.AdminAcademic onLogout={handleLogout} />} />
          <Route path="/admin/academic/departments" element={<AdminScreens.AdminDepartments onLogout={handleLogout} />} />
          <Route path="/admin/academic/courses" element={<AdminScreens.AdminCourses onLogout={handleLogout} />} />
          <Route path="/admin/academic/semesters" element={<AdminScreens.AdminSemesters onLogout={handleLogout} />} />
          <Route path="/admin/academic/batches" element={<AdminScreens.AdminBatches onLogout={handleLogout} />} />
          <Route path="/admin/academic/classes" element={<AdminScreens.AdminClasses onLogout={handleLogout} />} />
          <Route path="/admin/people" element={<AdminScreens.AdminPeople onLogout={handleLogout} />} />
          <Route path="/admin/people/enrollments" element={<AdminScreens.AdminEnrollments onLogout={handleLogout} />} />
          <Route path="/admin/people/teacher-assignments" element={<AdminScreens.AdminTeacherAssignments onLogout={handleLogout} />} />
          <Route path="/admin/people/coordinator-assignments" element={<AdminScreens.AdminCoordinatorAssignments onLogout={handleLogout} />} />
          <Route path="/admin/interviews" element={<AdminScreens.AdminInterviews onLogout={handleLogout} />} />
          <Route path="/admin/interviews/assignments" element={<AdminScreens.AdminInterviewAssignments onLogout={handleLogout} />} />
          <Route path="/admin/audit" element={<AdminScreens.AdminAuditLog onLogout={handleLogout} />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to={isAuthenticated ? (getRoleHome(session.role) || "/login") : "/login"} replace />} />
    </Routes>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
