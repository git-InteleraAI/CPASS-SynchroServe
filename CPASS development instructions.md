# CPASS – Software Engineering and Regression Prevention Standards

## Objective
Build a secure, scalable, maintainable, modular and reliable application where modifications to one feature do not unintentionally affect other features or existing business functionality.

## Mandatory Principles

1. **Modular Development:** Keep features and modules logically separated with clear responsibilities and interfaces.
2. **Minimal Changes:** Modify only the components necessary to implement the requested improvement.
3. **Dependency Analysis:** Before modifying code, identify all dependent components, services, APIs, database tables and integrations.
4. **Backward Compatibility:** Preserve existing functionality, API contracts and database behavior unless a change is explicitly required.
5. **Regression Prevention:** Every code modification must include appropriate regression tests for affected and dependent functionality.
6. **Error Isolation:** Prevent failures in one module from unnecessarily affecting unrelated modules.
7. **Database Safety:** Use backward-compatible migrations and preserve existing data.
8. **Centralized Logic:** Avoid duplicated business logic and inconsistent validation across modules.
9. **Observability:** Implement meaningful logging, error handling and monitoring.
10. **Documentation:** Document important architectural changes, API changes, migrations and implementation decisions.

## Mandatory Development Workflow

1. Inspect the existing implementation.
2. Understand the existing business logic.
3. Perform dependency and impact analysis.
4. Define expected behavior and acceptance criteria.
5. Implement one logical change at a time.
6. Add or update unit and integration tests.
7. Run relevant automated tests.
8. Run regression tests for dependent modules.
9. Run end-to-end tests for affected user journeys.
10. Review the final code for security, performance and maintainability.
11. Commit changes with meaningful messages.

## Regression Prevention Requirements

A feature is not considered complete simply because its new functionality works.

It must also be demonstrated that:
- Existing functionality continues working.
- Dependent modules continue working.
- API consumers are not unexpectedly broken.
- Existing records and database relationships remain valid.
- User roles and permissions remain correct.
- External integrations continue working.
- No unrelated functionality has regressed.

## CPASS-Specific Requirements

Preserve the existing L1, L2, L3, L4 and L5 workflow, candidate lifecycle, document management, Google Drive integration, authentication, role-based access, audit logs and existing business rules.

## Release and Merge Policy

Never merge into the main branch while:
- Critical or high-priority defects remain unresolved.
- Required automated tests fail.
- Regression tests fail.
- Database migrations are unsafe.
- Existing workflows are broken.
- Security validation is incomplete.

**Definition of Done:** A modification is complete only when the requested improvement works, existing dependent functionality remains intact, and the relevant automated and regression tests pass.