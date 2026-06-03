## Project Overview

Save content from anywhere, and bring it as context to every AI agents you use.

> [!IMPORTANT]
> Any changes in the repository structure, tech stack, or scripts must be updated in the [AGENTS.md](/AGENTS.md) file.
> The project's source of truth is the [AGENTS.md](/AGENTS.md) and `docs/spec.md` file.

## Repository Structure

- [extension/](/extension): Chrome Extension built using WXT, React, TypeScript, and Tailwind CSS.
- [mcp/](/mcp): Directory for Model Context Protocol (MCP) servers.
- [docs/](/docs): Product documentation and specifications (e.g., [spec.md](/docs/spec.md)).
- [.agents/](/.agents) / [.claude/](/.claude): AI agent configurations and shared skills (symlinked).

# Coding standards you must follow

- Write elegant, clean, and maintainable code.
- Ensure a good directory structure and modularity.
- Add explanatory comments to the code where necessary.
- Use meaningful variable and function names relevant to the language.
- Use consistent naming conventions.
- When working on the frontend, ensure responsiveness and a beautiful, consistent UI.
- When working on the backend, ensure efficient code that follows best practices for security and performance.
- When working on the database, ensure the schema is well defined and follows best practices for data integrity and performance.
- Do not delete any files or code to fix errors; ask the user for clarification if unsure.
- Apply the following principles in all code you generate:
- **DRY (Don't Repeat Yourself):** Abstract repeated logic into functions or modules to avoid duplication.
- **YAGNI (You Aren't Gonna Need It):** Only implement features and code that are currently required; avoid speculative additions.
- **SOLID Principles:**
- _Single Responsibility:_ Each module/class/function should have one clear responsibility.
- _Open/Closed:_ Code should be open for extension but closed for modification.
- _Liskov Substitution:_ Subtypes must be substitutable for their base types without altering correctness.
- _Interface Segregation:_ Prefer small, specific interfaces over large, general ones.
- _Dependency Inversion:_ Depend on abstractions, not concrete implementations.
- Write clean, maintainable, and modular code that adheres to these principles.
- Add comments where necessary for clarity, but avoid excessive commenting.
- Structure code into smaller, modular files and follow best practices.
- Do not repeat yourself; keep solutions simple.

## Tech Stack

- **Framework**: [WXT](https://wxt.dev/) (Web Extension Framework) for building the Chrome extension
- **Frontend & UI**: React 19, TypeScript, Tailwind CSS, Base UI, Radix UI (configured in [extension/package.json](/extension/package.json))
- **Build Tool**: Vite (under the hood via WXT and [vitest.config.ts](/extension/vitest.config.ts))
- **Testing**: Vitest
- **Package Manager**: pnpm (uses [pnpm-lock.yaml](/extension/pnpm-lock.yaml))

## Available Scripts

All scripts are executed from the [extension/](/extension) directory:

- `pnpm dev`: Start WXT development server (launches Chrome extension with hot reload)
- `pnpm dev:firefox`: Start WXT development server targeting Firefox
- `pnpm build`: Build production extension bundle
- `pnpm build:firefox`: Build production extension bundle for Firefox
- `pnpm zip`: Build and zip Chrome extension for distribution
- `pnpm zip:firefox`: Build and zip Firefox extension for distribution
- `pnpm compile`: Run TypeScript compilation check (`tsc --noEmit`)
- `pnpm test`: Run tests with Vitest once
- `pnpm test:watch`: Run tests with Vitest in watch mode
