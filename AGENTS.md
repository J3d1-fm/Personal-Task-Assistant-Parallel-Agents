# Project Instructions

## GitHub Actions Minute Budget

- Treat GitHub Actions minutes as a scarce shared budget. Prefer local validation first: targeted tests, lint, typecheck, build, or simulator checks that match the change.
- Do not push tiny fixup commits just to see CI results. Batch small related edits into one meaningful push when practical.
- Do not run full GitHub Actions CI for docs-only, changelog-only, instruction-only, or similarly low-risk changes unless the user explicitly asks or a release/merge gate requires it.
- For narrow code changes, run the smallest useful local or targeted check first. Use full CI for PR readiness, release, merge, dependency, security, cross-platform, or high-risk changes.
- When editing GitHub workflows, keep CI economical: add `paths-ignore` or path filters for safe non-code files, use `concurrency.cancel-in-progress`, and put expensive jobs behind `workflow_dispatch`, labels, or release-gate conditions where appropriate.
- Never weaken required quality gates just to save minutes. If CI is required by branch protection, release policy, or explicit user instruction, treat that as the source of truth.
- When intentionally skipping remote CI to save minutes, say so in the final report and include the local validation evidence that was used instead.
