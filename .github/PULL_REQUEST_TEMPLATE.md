## Summary

<!-- What does this change and why? Link the issue if there is one. -->

## Checklist

- [ ] Backend tests pass: `cd backend && python -m pytest -q`
- [ ] Backend lint passes: `ruff check --config ../ruff.toml .`
- [ ] Frontend tests pass: `cd frontend && bun run test`
- [ ] Frontend lint passes: `bun run lint`
- [ ] Frontend types check: `bunx tsc --noEmit -p .`
- [ ] New parsers/scrapers/classifiers have tests with sample data (no live requests)
- [ ] Tests use the neutral fixtures (`backend/tests/fixtures/config_test.yaml`), not a personal config
- [ ] No personal data: no real names, emails, phone numbers, home city, companies applied to, CV file names, `/home/...` paths, tokens or credentials
- [ ] Docs updated if behaviour or configuration keys changed (`README.md`, `docs/`, `backend/defaults/jobhunter.yaml`)
