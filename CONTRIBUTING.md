# Contributing to Brain2 🧠

Thank you for your interest in contributing to Brain2! We are excited to build a unified memory store for AI agents together.

This document outlines the guidelines and steps to help you get started with contributing.

---

## 📜 Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please be respectful and constructive in all your interactions.

---

## 🚀 How Can I Contribute?

### 1. Reporting Bugs
* Search the existing issues to see if the bug has already been reported.
* If not, open a new issue using our **Bug Report** template.
* Include a clear description of the bug, steps to reproduce, expected behavior, and screenshots if applicable.

### 2. Suggesting Features
* Open an issue using the **Feature Request** template.
* Explain the problem your feature solves and the proposed implementation.
* Discuss suggestions with the maintainers before starting implementation to ensure alignment with the product vision.

### 3. Submitting Pull Requests
* Fork the repository and create your branch from `main`.
* Write elegant, clean, and maintainable code.
* Ensure tests pass and add new tests for your changes.
* Link the pull request to the issue it resolves.

---

## 🛠️ Development Setup

Brain2 consists of two primary components: a Chrome Extension (frontend) and an MCP Backend (python service).

### Chrome Extension (`/extension`)
* Built with WXT, React 19, TypeScript, and Tailwind CSS.
* Uses `pnpm` for package management.

To get started:
1. Navigate to `/extension` and run `pnpm install` to install dependencies.
2. Run `pnpm dev` to launch the extension in a development Chrome instance with hot-reloading.
3. Run `pnpm compile` to check for TypeScript compilation errors.
4. Run `pnpm test` to run Vitest unit tests.

### MCP Backend (`/mcp`)
* Built with FastAPI, SQLite, FTS5, and `sqlite-vec`.
* Uses Python 3.11+.

To get started:
1. Navigate to `/mcp`.
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Run the development server (instructions will be updated as the server is implemented).

---

## 💡 Code Standards & Guidelines

We hold our codebase to high software engineering standards. Please apply these principles in all code you write:

### Architectural Principles
* **DRY (Don't Repeat Yourself):** Abstract repeated logic into reusable utility functions or hooks.
* **YAGNI (You Aren't Gonna Need It):** Focus strictly on the required feature scope. Do not add speculative code or dependencies.
* **SOLID Principles:**
  * **Single Responsibility:** Each module, function, or component should have exactly one reason to change.
  * **Open/Closed:** Write code that is open for extension but closed for modification (e.g. plugin architectures, strategy patterns).
  * **Liskov Substitution:** Derivatives must be completely substitutable for their base types.
  * **Interface Segregation:** Keep interfaces clean, narrow, and focused.
  * **Dependency Inversion:** Depend on abstractions (interfaces) rather than concrete implementations.

### General Guidelines
* **No File Deletions:** Do not delete files or refactor large chunks of code without prior approval or issue alignment.
* **Preserve Documentation:** Retain existing comments, docstrings, and notes unless they are directly invalidated by your changes.
* **Type Safety:** Always write fully typed TypeScript; avoid using the `any` type.
* **User Isolation:** On the backend, ensure that all database queries are isolated to the specific user's file: `/data/users/{user_id}.db`. Under no circumstances should cross-user data access occur.

### ⚠️ Critical Rule: Updating Agent Rules
Any changes in the repository structure, tech stack, or build/dev scripts must be documented in the [AGENTS.md](AGENTS.md) file. The [AGENTS.md](AGENTS.md) file and [docs/spec.md](docs/spec.md) are the primary sources of truth for both developers and AI Coding Agents.

---

## 📬 Pull Request Checklist

Before submitting a Pull Request, please ensure you have completed the following:
1. [ ] Followed the coding guidelines and architectural standards.
2. [ ] Kept branch names clear and descriptive (e.g., `feat/oauth-flow` or `fix/normalizer-bug`).
3. [ ] Created unit tests for new logic and verified all tests pass (`pnpm test`).
4. [ ] Run TypeScript compile checks (`pnpm compile`).
5. [ ] Documented any changes in [AGENTS.md](AGENTS.md) (if repo structure, tech stack, or scripts changed).
6. [ ] Opened the PR with a clear summary of the changes and referenced the issue number.
