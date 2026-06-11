import { FormEvent, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, clearAuth, getRole, setAuth } from "./api";
import AdminPage from "./pages/AdminPage";
import DashboardPage from "./pages/DashboardPage";
import DataPage from "./pages/DataPage";
import ExecutionLegacyPage from "./pages/ExecutionLegacyPage";
import ExecutionPage from "./pages/ExecutionPage";
import HoldingsPage from "./pages/HoldingsPage";
import SettingsPage from "./pages/SettingsPage";

function LoginPage() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("112233");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    const res = await api<{ access_token: string; username: string; role: string }>(
      "/api/v1/auth/login",
      { method: "POST", body: JSON.stringify({ username, password }) },
    );
    if (!res.data) {
      setError(res.error || "登录失败");
      return;
    }
    setAuth(res.data.access_token, res.data.username, res.data.role);
    navigate("/dashboard");
  }

  return (
    <div className="login-page">
      <form className="login-box" onSubmit={onSubmit}>
        <h2>TimeRich</h2>
        <p>纳指100 + 红利低波 · 定投组合管理</p>
        <div className="form-row">
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="用户名" />
        </div>
        <div className="form-row">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="密码"
          />
        </div>
        {error && <div className="error">{error}</div>}
        <button type="submit">登录</button>
      </form>
    </div>
  );
}

function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const role = getRole();
  const nav = [
    { to: "/dashboard", label: "仪表盘" },
    { to: "/holdings", label: "持仓" },
    { to: "/execution", label: "定投" },
    { to: "/execution/legacy", label: "定投（旧）" },
    { to: "/data", label: "数据管理" },
    { to: "/settings", label: "设置" },
  ];
  if (role === "admin") nav.push({ to: "/admin", label: "用户管理" });

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>TimeRich</h1>
        <nav>
          {nav.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={location.pathname === item.to ? "active" : ""}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <strong>{nav.find((n) => n.to === location.pathname)?.label || "TimeRich"}</strong>
          <div className="topbar-actions">
            <button
              className="secondary"
              onClick={async () => {
                await api("/api/v1/dashboard/refresh", { method: "POST" });
                window.location.reload();
              }}
            >
              刷新数据
            </button>
            <button
              className="secondary"
              onClick={() => {
                clearAuth();
                navigate("/login");
              }}
            >
              退出
            </button>
          </div>
        </header>
        <div className="content">{children}</div>
      </div>
    </div>
  );
}

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem("token");
  if (!token) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route
        path="/dashboard"
        element={
          <PrivateRoute>
            <DashboardPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/holdings"
        element={
          <PrivateRoute>
            <HoldingsPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/execution/legacy"
        element={
          <PrivateRoute>
            <ExecutionLegacyPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/execution"
        element={
          <PrivateRoute>
            <ExecutionPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/data"
        element={
          <PrivateRoute>
            <DataPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <PrivateRoute>
            <SettingsPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/admin"
        element={
          <PrivateRoute>
            <AdminPage />
          </PrivateRoute>
        }
      />
    </Routes>
  );
}
