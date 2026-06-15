import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Save, Shield, UserRoundPlus, Users } from "lucide-react";

import { api } from "../api/client";
import type { AuthUser, UserRole } from "../types/api";
import { Badge, Button, Card, Input } from "./ui";

export function UserManagement({ currentUser }: { currentUser: AuthUser }) {
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: api.users });
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("standard");
  const [drafts, setDrafts] = useState<Record<string, { display_name: string; password: string }>>(
    {}
  );

  const refreshUsers = () => queryClient.invalidateQueries({ queryKey: ["users"] });

  const createUser = useMutation({
    mutationFn: api.createUser,
    onSuccess: () => {
      setUsername("");
      setDisplayName("");
      setPassword("");
      setRole("standard");
      refreshUsers();
    }
  });

  const updateUser = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof api.updateUser>[1] }) =>
      api.updateUser(id, payload),
    onSuccess: refreshUsers
  });

  const updatePassword = useMutation({
    mutationFn: ({ id, nextPassword }: { id: string; nextPassword: string }) =>
      api.updateUserPassword(id, nextPassword),
    onSuccess: (_user, variables) => {
      setDrafts((current) => ({
        ...current,
        [variables.id]: { ...(current[variables.id] ?? {}), password: "" }
      }));
      refreshUsers();
    }
  });

  const deactivateUser = useMutation({
    mutationFn: api.deactivateUser,
    onSuccess: refreshUsers
  });

  function submitNewUser(event: FormEvent) {
    event.preventDefault();
    createUser.mutate({
      username: username.trim(),
      display_name: displayName.trim() || null,
      password,
      role,
      is_active: true
    });
  }

  function draftFor(user: AuthUser) {
    return drafts[user.id] ?? { display_name: user.display_name, password: "" };
  }

  function setDraft(user: AuthUser, patch: Partial<{ display_name: string; password: string }>) {
    setDrafts((current) => ({
      ...current,
      [user.id]: { ...draftFor(user), ...patch }
    }));
  }

  return (
    <Card className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.24em] text-ink-500 dark:text-ink-100">
          Administration
        </p>
        <h2 className="mt-1 flex items-center gap-2 font-display text-2xl font-bold">
          <Users className="h-5 w-5 text-harbor-500" />
          User management
        </h2>
        <p className="mt-2 text-sm text-ink-500 dark:text-ink-100">
          Add local users, assign administrator or standard access, and reset passwords.
        </p>
      </div>

      <form
        className="grid gap-3 rounded-3xl border border-ink-100 bg-white/55 p-4 dark:border-white/10 dark:bg-white/5 lg:grid-cols-[1fr_1fr_1fr_160px_auto]"
        onSubmit={submitNewUser}
      >
        <Input
          aria-label="New username"
          autoComplete="off"
          placeholder="Username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
        />
        <Input
          aria-label="Display name"
          autoComplete="off"
          placeholder="Display name"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
        />
        <Input
          aria-label="Initial password"
          autoComplete="new-password"
          placeholder="Initial password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <select
          aria-label="Role"
          className="rounded-2xl border border-ink-100 bg-white/80 px-4 py-2 text-sm outline-none ring-harbor-400 transition focus:ring-2 dark:border-white/10 dark:bg-white/5 dark:text-ink-50"
          value={role}
          onChange={(event) => setRole(event.target.value as UserRole)}
        >
          <option value="standard">Standard</option>
          <option value="admin">Administrator</option>
        </select>
        <Button disabled={createUser.isPending || !username.trim() || password.length < 8}>
          <UserRoundPlus className="mr-2 h-4 w-4" />
          Add
        </Button>
      </form>

      {createUser.error ? <ErrorMessage message={createUser.error.message} /> : null}
      {updateUser.error ? <ErrorMessage message={updateUser.error.message} /> : null}
      {updatePassword.error ? <ErrorMessage message={updatePassword.error.message} /> : null}
      {deactivateUser.error ? <ErrorMessage message={deactivateUser.error.message} /> : null}

      <div className="grid gap-3">
        {users.data?.map((user) => {
          const draft = draftFor(user);
          const isSelf = user.id === currentUser.id;
          return (
            <div
              className="grid gap-3 rounded-3xl border border-ink-100 bg-white/55 p-4 dark:border-white/10 dark:bg-white/5"
              key={user.id}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{user.username}</span>
                    <Badge tone={user.role === "admin" ? "warn" : "neutral"}>
                      {user.role === "admin" ? "Administrator" : "Standard"}
                    </Badge>
                    <Badge tone={user.is_active ? "good" : "bad"}>
                      {user.is_active ? "Active" : "Disabled"}
                    </Badge>
                    {isSelf ? <Badge tone="good">You</Badge> : null}
                  </div>
                  <p className="mt-1 text-xs text-ink-500 dark:text-ink-100">
                    Last login: {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "Never"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    disabled={updateUser.isPending || user.role === "admin"}
                    onClick={() => updateUser.mutate({ id: user.id, payload: { role: "admin" } })}
                    type="button"
                    variant="ghost"
                  >
                    <Shield className="mr-2 h-4 w-4" />
                    Make admin
                  </Button>
                  <Button
                    disabled={updateUser.isPending || user.role === "standard" || isSelf}
                    onClick={() =>
                      updateUser.mutate({ id: user.id, payload: { role: "standard" } })
                    }
                    type="button"
                    variant="ghost"
                  >
                    Make standard
                  </Button>
                  <Button
                    disabled={deactivateUser.isPending || isSelf || !user.is_active}
                    onClick={() => deactivateUser.mutate(user.id)}
                    type="button"
                    variant="danger"
                  >
                    Disable
                  </Button>
                </div>
              </div>

              <div className="grid gap-3 lg:grid-cols-[1fr_auto_1fr_auto]">
                <Input
                  aria-label={`Display name for ${user.username}`}
                  value={draft.display_name}
                  onChange={(event) => setDraft(user, { display_name: event.target.value })}
                />
                <Button
                  disabled={updateUser.isPending || draft.display_name.trim() === user.display_name}
                  onClick={() =>
                    updateUser.mutate({
                      id: user.id,
                      payload: { display_name: draft.display_name.trim() || user.username }
                    })
                  }
                  type="button"
                  variant="ghost"
                >
                  <Save className="mr-2 h-4 w-4" />
                  Save name
                </Button>
                <Input
                  aria-label={`New password for ${user.username}`}
                  autoComplete="new-password"
                  placeholder="New password"
                  type="password"
                  value={draft.password}
                  onChange={(event) => setDraft(user, { password: event.target.value })}
                />
                <Button
                  disabled={updatePassword.isPending || draft.password.length < 8}
                  onClick={() =>
                    updatePassword.mutate({ id: user.id, nextPassword: draft.password })
                  }
                  type="button"
                  variant="ghost"
                >
                  <KeyRound className="mr-2 h-4 w-4" />
                  Reset
                </Button>
              </div>
            </div>
          );
        })}
        {users.isLoading ? (
          <p className="rounded-3xl border border-dashed border-ink-100 p-5 text-sm text-ink-500 dark:border-white/10 dark:text-ink-100">
            Loading users…
          </p>
        ) : null}
      </div>
    </Card>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <p className="rounded-2xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-200">
      {message}
    </p>
  );
}
