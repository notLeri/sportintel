import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useMe } from "@/entities/user";
import { api, isAppError, unwrap } from "@/shared/api";
import { formatDateTime } from "@/shared/lib/datetime";
import { cn } from "@/shared/lib/utils";
import {
  Badge,
  Button,
  Checkbox,
  DataTable,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  toast,
} from "@/shared/ui";

type User = import("@/shared/api").components["schemas"]["UserAdminItem"];
type Role = User["role"];
const ROLES: Role[] = ["researcher", "editor", "admin"];
const usersKey = ["users"] as const;
const MIN_PASSWORD = 10; // как на backend (identity.domain.password)

function usePatch() {
  const qc = useQueryClient();
  const { t } = useTranslation("admin");
  return useMutation({
    mutationFn: ({ u, patch }: { u: User; patch: Record<string, unknown> }) =>
      unwrap(
        api.PATCH("/api/v1/users/{user_id}", {
          params: { path: { user_id: u.id } },
          body: patch,
          headers: { "If-Match": `"${u.version}"` },
        }),
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: usersKey }),
    onError: (e) =>
      toast.error(
        isAppError(e) && e.code === "user.last_admin"
          ? t("users.last_admin")
          : isAppError(e)
            ? e.title
            : "",
      ),
  });
}

function InviteUserDialog() {
  const { t } = useTranslation(["admin", "enums"]);
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("researcher");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const invite = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/users", {
          body: {
            email: email.trim(),
            role,
            display_name: name.trim() || null,
            password: password || null,
          },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: usersKey });
      setOpen(false);
      setEmail("");
      setName("");
      setPassword("");
      setError(null);
      toast.success(t("users.invited"));
    },
    onError: (e) =>
      setError(
        isAppError(e) && e.code === "user.email_exists"
          ? t("users.exists")
          : isAppError(e)
            ? e.title
            : "",
      ),
  });
  const valid =
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) &&
    (password === "" || password.length >= MIN_PASSWORD);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button size="sm" onClick={() => setOpen(true)}>
        {t("users.invite")}
      </Button>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("users.invite")}</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid) invite.mutate();
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="u-email">E-mail</Label>
            <Input
              id="u-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="u-name">{t("users.name")}</Label>
            <Input id="u-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="u-role">{t("users.role")}</Label>
            <select
              id="u-role"
              className="border-input h-8 w-full rounded-md border bg-transparent px-2"
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`enums:Role.${r}`)}
                </option>
              ))}
            </select>
          </div>
          <PasswordField id="u-password" value={password} onChange={setPassword} />
          {error ? (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="submit" disabled={!valid || invite.isPending}>
              {t("users.send")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PasswordField({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const { t } = useTranslation("admin");
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{t("users.password")}</Label>
      <Input
        id={id}
        type="password"
        autoComplete="new-password"
        minLength={MIN_PASSWORD}
        aria-describedby={`${id}-hint`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <p id={`${id}-hint`} className="text-muted-foreground text-xs">
        {t("users.password_hint", { min: MIN_PASSWORD })}
      </p>
    </div>
  );
}

/** Задать или сбросить пароль: все сессии пользователя закрываются. */
function SetPasswordDialog({ u }: { u: User }) {
  const { t } = useTranslation("admin");
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const patch = usePatch();
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setPassword("");
      }}
    >
      <Button
        size="sm"
        variant="outline"
        title={t("users.set_password_tip")}
        aria-label={t("users.set_password_for", { name: u.display_name })}
        onClick={() => setOpen(true)}
      >
        {u.has_password ? t("users.reset_password") : t("users.set_password")}
      </Button>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("users.set_password_for", { name: u.display_name })}</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            patch.mutate(
              { u, patch: { password } },
              {
                onSuccess: () => {
                  setOpen(false);
                  setPassword("");
                  toast.success(t("users.password_set"));
                },
              },
            );
          }}
        >
          <PasswordField id={`pw-${u.id}`} value={password} onChange={setPassword} />
          <DialogFooter>
            <Button type="submit" disabled={password.length < MIN_PASSWORD || patch.isPending}>
              {t("users.save_password")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function UsersPage() {
  const { t } = useTranslation(["admin", "enums"]);
  const me = useMe();
  const allowed = me.permissions.includes("users.manage");
  const list = useQuery({
    queryKey: usersKey,
    enabled: allowed,
    queryFn: () => unwrap(api.GET("/api/v1/users")),
  });
  const patch = usePatch();
  if (!allowed) return <p role="alert">{t("forbidden")}</p>;
  return (
    <section aria-labelledby="users-h" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="users-h" className="text-lg font-semibold">
          {t("section.users")}
        </h2>
        <InviteUserDialog />
      </div>
      <DataTable aria-label={t("section.users")}>
        <thead>
          <tr>
            <th scope="col">{t("users.name")}</th>
            <th scope="col">E-mail</th>
            <th scope="col" className="shrink">
              {t("users.role")}
            </th>
            <th scope="col" className="shrink text-center!">
              {t("users.active")}
            </th>
            <th scope="col" className="shrink">
              {t("users.last_login")}
            </th>
            <th scope="col" className="shrink">
              {t("users.password")}
            </th>
          </tr>
        </thead>
        <tbody>
          {(list.data?.items ?? []).map((u) => (
            <tr key={u.id} className={cn(!u.active && "text-muted-foreground")}>
              <td className="font-medium">
                {u.display_name}{" "}
                {u.invited && !u.last_login_at ? (
                  <Badge variant="secondary">{t("users.invited_badge")}</Badge>
                ) : null}
              </td>
              <td className="text-muted-foreground">{u.email}</td>
              <td className="shrink">
                <select
                  aria-label={t("users.role_for", { name: u.display_name })}
                  className="border-input h-8 rounded-md border bg-transparent px-2"
                  value={u.role}
                  onChange={(e) => {
                    const role = e.target.value as Role;
                    if (
                      window.confirm(
                        t("users.confirm_role", {
                          name: u.display_name,
                          role: t(`enums:Role.${role}`),
                        }),
                      )
                    )
                      patch.mutate({ u, patch: { role } });
                  }}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {t(`enums:Role.${r}`)}
                    </option>
                  ))}
                </select>
              </td>
              <td className="shrink text-center">
                <Checkbox
                  aria-label={t("users.active_for", { name: u.display_name })}
                  checked={u.active}
                  onCheckedChange={(c) => {
                    if (c === true || window.confirm(t("users.confirm_off")))
                      patch.mutate({ u, patch: { active: c === true } });
                  }}
                />
              </td>
              <td className="shrink text-muted-foreground">
                {u.last_login_at ? formatDateTime(u.last_login_at, me.timezone) : "—"}
              </td>
              <td className="shrink">
                <SetPasswordDialog u={u} />
              </td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </section>
  );
}
