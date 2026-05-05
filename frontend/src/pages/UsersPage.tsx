import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Shield,
  UserPlus,
  Users,
} from "lucide-react";
import type { AuthUser, Role } from "../context/AuthContext";
import {
  createUser,
  deactivateUser,
  listUsers,
  updateUser,
} from "../services/users";

const ROLES: Array<{ value: Role; label: string }> = [
  { value: "admin", label: "System Administrator" },
  { value: "supervisor", label: "Supervisor" },
  { value: "officer", label: "Traffic Officer" },
];

export function UsersPage() {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [badgeNumber, setBadgeNumber] = useState("");
  const [role, setRole] = useState<Role>("officer");
  const [password, setPassword] = useState("");

  async function loadUsers() {
    try {
      setLoading(true);
      setError(null);
      const data = await listUsers();
      setUsers(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers();
  }, []);

  const filteredUsers = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();

    if (!q) return users;

    return users.filter((user) => {
      return (
        user.full_name.toLowerCase().includes(q) ||
        user.email.toLowerCase().includes(q) ||
        user.role_label.toLowerCase().includes(q) ||
        (user.badge_number ?? "").toLowerCase().includes(q)
      );
    });
  }, [searchTerm, users]);

  async function handleCreateUser(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setSaving(true);

    try {
      const created = await createUser({
        full_name: fullName.trim(),
        email: email.trim(),
        badge_number: badgeNumber.trim() || null,
        role,
        password,
      });

      setUsers((prev) => [created, ...prev]);
      setSuccess(`User ${created.full_name} created successfully.`);
      setFullName("");
      setEmail("");
      setBadgeNumber("");
      setRole("officer");
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user.");
    } finally {
      setSaving(false);
    }
  }

  async function handleRoleChange(user: AuthUser, nextRole: Role) {
    setError(null);
    setSuccess(null);

    try {
      const updated = await updateUser(user.user_id, { role: nextRole });
      setUsers((prev) =>
        prev.map((item) => (item.user_id === user.user_id ? updated : item))
      );
      setSuccess(`Updated role for ${updated.full_name}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update role.");
    }
  }

  async function handleToggleActive(user: AuthUser) {
    setError(null);
    setSuccess(null);

    try {
      const updated = await updateUser(user.user_id, {
        is_active: !user.is_active,
      });
      setUsers((prev) =>
        prev.map((item) => (item.user_id === user.user_id ? updated : item))
      );
      setSuccess(
        `${updated.full_name} is now ${updated.is_active ? "active" : "inactive"}.`
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update user status."
      );
    }
  }

  async function handleDeactivate(user: AuthUser) {
    const confirmed = window.confirm(
      `Deactivate ${user.full_name}? This user will no longer be able to log in.`
    );

    if (!confirmed) return;

    setError(null);
    setSuccess(null);

    try {
      await deactivateUser(user.user_id);
      setUsers((prev) =>
        prev.map((item) =>
          item.user_id === user.user_id ? { ...item, is_active: false } : item
        )
      );
      setSuccess(`${user.full_name} deactivated.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to deactivate user.");
    }
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Administration</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-gray-900">
            User Management
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-gray-600">
            Create and manage system users. Access is controlled by role-based
            permissions.
          </p>
        </div>

        <button
          onClick={loadUsers}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </section>

      {error && (
        <section className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4">
          <AlertCircle className="mt-0.5 h-5 w-5 text-red-600" />
          <div>
            <p className="text-sm font-semibold text-red-900">Action failed</p>
            <p className="mt-1 text-sm text-red-800">{error}</p>
          </div>
        </section>
      )}

      {success && (
        <section className="flex items-start gap-3 rounded-xl border border-green-200 bg-green-50 p-4">
          <CheckCircle2 className="mt-0.5 h-5 w-5 text-green-600" />
          <div>
            <p className="text-sm font-semibold text-green-900">Success</p>
            <p className="mt-1 text-sm text-green-800">{success}</p>
          </div>
        </section>
      )}

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <UserPlus className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                Add New User
              </h2>
              <p className="mt-1 text-sm text-gray-600">
                Create login credentials for authorised users.
              </p>
            </div>
          </div>

          <form onSubmit={handleCreateUser} className="mt-6 space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                Full name
              </label>
              <input
                required
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                Email
              </label>
              <input
                required
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                Badge / Staff ID
              </label>
              <input
                value={badgeNumber}
                onChange={(event) => setBadgeNumber(event.target.value)}
                placeholder="Optional"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                Role
              </label>
              <select
                value={role}
                onChange={(event) => setRole(event.target.value as Role)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500"
              >
                {ROLES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                Temporary password
              </label>
              <input
                required
                type="password"
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500"
              />
            </div>

            <button
              type="submit"
              disabled={saving}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <UserPlus className="h-4 w-4" />
                  Create User
                </>
              )}
            </button>
          </form>
        </div>

        <div className="xl:col-span-2 rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 px-6 py-5">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="flex items-start gap-3">
                <div className="rounded-lg bg-gray-100 p-2">
                  <Users className="h-5 w-5 text-gray-700" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">
                    System Users
                  </h2>
                  <p className="mt-1 text-sm text-gray-600">
                    {users.length} account{users.length === 1 ? "" : "s"} found.
                  </p>
                </div>
              </div>

              <input
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Search users"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 md:w-72"
              />
            </div>
          </div>

          {loading ? (
            <div className="flex items-center gap-2 px-6 py-12 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading users...
            </div>
          ) : filteredUsers.length === 0 ? (
            <div className="px-6 py-12 text-sm text-gray-500">
              No users match the current search.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead className="border-b border-gray-200 bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      User
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Role
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Last Login
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Actions
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-200 bg-white">
                  {filteredUsers.map((user) => (
                    <tr key={user.user_id}>
                      <td className="px-6 py-4">
                        <p className="text-sm font-medium text-gray-900">
                          {user.full_name}
                        </p>
                        <p className="mt-1 text-xs text-gray-500">
                          {user.email}
                        </p>
                        {user.badge_number && (
                          <p className="mt-1 text-xs text-gray-400">
                            Badge: {user.badge_number}
                          </p>
                        )}
                      </td>

                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <Shield className="h-4 w-4 text-gray-400" />
                          <select
                            value={user.role}
                            onChange={(event) =>
                              handleRoleChange(user, event.target.value as Role)
                            }
                            className="rounded-lg border border-gray-300 px-2 py-1 text-xs text-gray-700 outline-none focus:border-gray-500"
                          >
                            {ROLES.map((item) => (
                              <option key={item.value} value={item.value}>
                                {item.label}
                              </option>
                            ))}
                          </select>
                        </div>
                      </td>

                      <td className="px-6 py-4">
                        <button
                          onClick={() => handleToggleActive(user)}
                          className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                            user.is_active
                              ? "bg-green-100 text-green-800"
                              : "bg-red-100 text-red-800"
                          }`}
                        >
                          {user.is_active ? "Active" : "Inactive"}
                        </button>
                      </td>

                      <td className="px-6 py-4 text-sm text-gray-600">
                        {user.last_login ?? "Never"}
                      </td>

                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => handleDeactivate(user)}
                          disabled={!user.is_active}
                          className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          Deactivate
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
