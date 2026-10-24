import { useTranslation } from "react-i18next";

import {
  Button,
  DataTable,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui";

import type { DiffRow } from "./diffFields";

const show = (v: unknown) => (Array.isArray(v) ? `${v.length}` : String(v ?? "") || "—");

export function ConflictDiffDialog({
  rows,
  onReload,
  onOverwrite,
}: {
  rows: DiffRow[] | null;
  onReload: () => void;
  onOverwrite: () => void;
}) {
  const { t } = useTranslation("event");
  return (
    <Dialog open={rows !== null} onOpenChange={(o) => !o && onReload()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("edit.conflict_title")}</DialogTitle>
        </DialogHeader>
        <DataTable>
          <thead>
            <tr>
              <th>{t("edit.field")}</th>
              <th>{t("edit.theirs")}</th>
              <th>{t("edit.mine")}</th>
            </tr>
          </thead>
          <tbody>
            {(rows ?? []).map((r) => (
              <tr key={r.field}>
                <td>{t(`edit.fields.${r.field}`)}</td>
                <td>{show(r.theirs)}</td>
                <td>{show(r.mine)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
        <DialogFooter>
          <Button variant="outline" onClick={onReload}>
            {t("edit.reload")}
          </Button>
          <Button onClick={onOverwrite}>{t("edit.overwrite")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
