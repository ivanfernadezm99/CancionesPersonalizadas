## Testing Capabilities — CancionesPersonalizadas

**Strict TDD Mode**: enabled
**Detected**: 2026-07-27

### Test Runner

- Command: `pytest`
- Framework: pytest 9.0.3

### Test Layers

| Layer       | Available | Tool             |
| ----------- | --------- | ---------------- |
| Unit        | ✅        | pytest           |
| Integration | ✅        | pytest + httpx   |
| E2E         | ❌        | Playwright avail (TBD) |

### Coverage

- Available: ✅
- Command: `pytest --cov`

### Quality Tools

| Tool         | Available | Command                |
| ------------ | --------- | ---------------------- |
| Linter       | ✅        | `ruff check .`         |
| Type checker | ✅        | `mypy .`               |
| Formatter    | ✅        | `black .`              |
