import { i18n } from "@/shared/i18n";

import { AUDIT_ACTIONS, type AuditEntry, describeAction } from "./describeAction";

const t = i18n.getFixedT("pt-BR", ["event", "enums"]);
const entry = (action: string, extra: Partial<AuditEntry> = {}): AuditEntry => ({
  id: 1,
  at: "2026-10-09T10:00:00Z",
  actor: { id: "0192f6a1-0000-7000-8000-000000000001", name: "Ana" },
  action,
  target_type: "event",
  target_id: "x",
  before: null,
  after: null,
  reason: null,
  ...extra,
});

test.each(AUDIT_ACTIONS)("every audit action has a translation: %s", (action) => {
  for (const lng of ["pt-BR", "en", "ru"])
    expect(i18n.exists(`history.actions.${action}`, { lng, ns: "event" })).toBe(true);
  expect(describeAction(entry(action), t)).not.toContain("history.actions");
});

test("transition, rejection, edit and system actor", () => {
  expect(
    describeAction(
      entry("event.transitioned", { before: { status: "NEW" }, after: { status: "SELECTED" } }),
      t,
    ),
  ).toBe("Ana mudou o status de Novo para Selecionado");
  expect(
    describeAction(
      entry("event.transitioned", {
        before: { status: "NEW" },
        after: {
          status: "REJECTED",
          rejection_reason: "DUPLICATE",
          rejection_comment: "já existe",
        },
      }),
      t,
    ),
  ).toBe("Ana rejeitou: Duplicado — já existe");
  expect(describeAction(entry("event.edited", { after: { title: "x", summary: "y" } }), t)).toBe(
    "Ana editou: Título, Resumo",
  );
  expect(describeAction(entry("draft.saved", { actor: null, after: { n: 2 } }), t)).toBe(
    "Sistema salvou a versão 2 do rascunho",
  );
});
