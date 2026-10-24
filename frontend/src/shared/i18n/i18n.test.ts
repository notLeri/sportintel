import { createI18n } from ".";

test("default locale is ru", () => {
  expect(createI18n().language).toBe("ru");
});

test("pt-BR key", () => {
  expect(createI18n("pt-BR").t("nav.events")).toBe("Eventos");
});

test("missing key in ru falls back to en", () => {
  const i18n = createI18n("ru");
  i18n.addResource("en", "common", "only.en", "English only");
  expect(i18n.t("only.en")).toBe("English only");
});

test("ICU plural", () => {
  const pt = createI18n("pt-BR");
  expect(pt.t("sources", { count: 1 })).toBe("1 fonte");
  expect(pt.t("sources", { count: 3 })).toBe("3 fontes");
  const ru = createI18n("ru");
  expect(ru.t("sources", { count: 5 })).toBe("5 источников");
});
