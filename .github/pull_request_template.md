## What changed

<!-- What and why; link the issue if there is one. -->

## Checklist

- [ ] ruff, mypy, import-linter, eslint, tsc are green; CI is green
- [ ] New logic is covered by tests
- [ ] Migrations: `alembic upgrade head` from scratch and `downgrade -1 → upgrade` pass; `alembic heads` = 1
- [ ] `openapi.json` and `frontend/src/shared/api/generated/` are regenerated (`make api-client`) if the API changed
- [ ] New UI strings exist in `en`, `ru` and `pt-BR`
- [ ] New env variables/settings are described in the README
- [ ] Deliberate simplifications are marked with `ponytail:`

## Did a prompt or enrichment rule change?

<!-- If so, attach an evals report (`make eval-rules`, evals/reports/…) comparing before and after. -->

- [ ] No
- [ ] Yes, report: …
