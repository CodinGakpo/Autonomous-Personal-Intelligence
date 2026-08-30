# Rule

1. tools/fathom must not import clickup.
2. tools must not import skills.
3. All ClickUp access must go through clickup/client.py.

## Why

Clear module boundaries reduce coupling, improve maintainability, and make testing easier. Restricting imports ensures that each module has a single responsibility and prevents architectural drift as the project grows.

## Scope

This rule applies to all existing and future code within the repository. Any code that interacts with ClickUp must use clickup/client.py as the single access layer.

## Enforcement

Code reviews must verify that prohibited imports are not introduced. Automated architecture checks and CI validation should be used to detect and prevent boundary violations.
