import { FormEvent, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api, getRole } from "../api";

export default function AdminPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const isAdmin = getRole() === "admin";

  async function load() {
    const res = await api<any[]>("/api/v1/users");
    setUsers(res.data || []);
  }

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin]);

  if (!isAdmin) return <Navigate to="/dashboard" replace />;

  async function createUser() {
    await api("/api/v1/users", {
      method: "POST",
      body: JSON.stringify({ username, password, role: "user" }),
    });
    setUsername("");
    setPassword("");
    load();
  }

  async function toggle(id: number) {
    await api(`/api/v1/users/${id}/toggle`, { method: "POST" });
    load();
  }

  return (
    <>
      <div className="card">
        <h3>新建用户</h3>
        <input placeholder="用户名" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input
          placeholder="初始密码"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ marginTop: 8 }}
        />
        <button style={{ marginTop: 8 }} onClick={createUser}>
          创建
        </button>
      </div>
      <table>
        <thead>
          <tr>
            <th>用户名</th>
            <th>角色</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.username}</td>
              <td>{u.role}</td>
              <td>{u.is_active ? "启用" : "禁用"}</td>
              <td>
                {u.username !== "admin" && (
                  <button className="secondary" onClick={() => toggle(u.id)}>
                    {u.is_active ? "禁用" : "启用"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
