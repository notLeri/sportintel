import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { isAppError } from "@/shared/api";
import { newIdempotencyKey } from "@/shared/lib/idempotency";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Input,
  Label,
  toast,
} from "@/shared/ui";

import { normalizeUrlInput, useAddUrl } from "./useAddUrl";

export function AddUrlDialog() {
  const { t } = useTranslation("articles");
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Ключ создаётся при открытии и живёт до успешной отправки (BE-T1.10, повтор без дубля).
  const [key, setKey] = useState(newIdempotencyKey);
  const add = useAddUrl();

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      setKey(newIdempotencyKey());
      setError(null);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const url = normalizeUrlInput(value);
    if (!url) {
      setError(t("url_invalid"));
      return;
    }
    try {
      const res = await add.mutateAsync({ url, key });
      toast.success(res.created ? t("added") : t("already_exists"));
      setValue("");
      setOpen(false);
    } catch (err) {
      if (isAppError(err) && err.code === "article.invalid_url") setError(t("url_invalid"));
      else if (isAppError(err) && err.code === "network.offline") setError(t("offline"));
      else setError(t("add_failed"));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm">{t("add_url")}</Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={onSubmit} noValidate>
          <DialogHeader>
            <DialogTitle>{t("add_url")}</DialogTitle>
            <DialogDescription>{t("add_url_hint")}</DialogDescription>
          </DialogHeader>
          <div className="my-4 space-y-1">
            <Label htmlFor="manual-url">URL</Label>
            <Input
              id="manual-url"
              value={value}
              onChange={(e) => {
                setValue(e.target.value);
                setError(null);
              }}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "manual-url-error" : undefined}
              placeholder="https://ge.globo.com/…"
            />
            {error ? (
              <p id="manual-url-error" role="alert" className="text-destructive text-sm">
                {error}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!value.trim() || add.isPending}>
              {t("submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
