# Brain2 🧠

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![WXT Framework](https://img.shields.io/badge/Extension-WXT-brightgreen)](https://wxt.dev/)
[![React 19](https://img.shields.io/badge/Frontend-React%2019-cyan)](https://react.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Styling-Tailwind%20CSS-blueviolet)](https://tailwindcss.com/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57)](https://sqlite.org/)

> **Save your context in one place, and bring it to all AI agents you use.**

Brain2 is an open-source personal memory store designed to bridge the gap between where you save information (GitHub stars, articles, clips, and conversations) and where you use it (Cursor, Claude Code, ChatGPT, or the Claude Web Interface). 

It consists of:
1. **A Chrome Extension** to capture full pages, selected clips, and conversations with one click.
2. **A Remote MCP Server** that serves your knowledge base to any Model Context Protocol (MCP) compliant client using hybrid search (BM25 + sqlite-vec vector search).

---

## 🏗️ Technical Architecture

```mermaid
graph TD
    subgraph "Capture Clients"
        Ext[Chrome Extension]
        AgentWrite[AI Agent / write-back]
    end

    subgraph "Brain2 Backend (hosted / local)"
        API[FastAPI Gateway]
        OAuth[OAuth 2.1 Server + PKCE]
        Pipeline[Background Jobs Pipeline]
    end

    subgraph "Per-User Isolated Storage"
        DBs[(/data/users/{user_id}.db)]
        FTS[FTS5 Index]
        Vec[sqlite-vec / vec0]
    end

    Ext -->|POST /entries| API
    AgentWrite -->|save tool| API
    OAuth -.->|JWT Bearer Token Validation| API
    
    API -->|Normalize & Save| Pipeline
    Pipeline -->|FTS indexing| FTS
    Pipeline -->|Gemini Flash summary| DBs
    Pipeline -->|Gemini Embeddings| Vec

    classDef client fill:#dcf8c6,stroke:#333,stroke-width:2px;
    classDef server fill:#ececff,stroke:#333,stroke-width:2px;
    classDef storage fill:#fff2cc,stroke:#333,stroke-width:2px;
    class Ext,AgentWrite client;
    class API,OAuth,Pipeline server;
    class DBs,FTS,Vec storage;
```

---

## ✨ Features

- **Save Once** — Capture bookmarks, selection text snippets, full web pages, or entire chat transcripts with a single click.
- **Recall Anywhere** — Point any AI agent (Claude Code, Cursor, ChatGPT) to your MCP URL, sign in, and let it query your memory store.
- **Hybrid Search (BM25 + Vector)** — Finds relevant documents using keyword matching on titles/tags combined with semantic vector search on summarized content (merged via Reciprocal Rank Fusion).
- **Agent Write-Back** — Let your AI agents add entries, update notes, and categorize bookmarks directly via the `save` tool during conversations.
- **Isolated SQLite Storage** — Zero cross-user database leakage. Every user gets a private `{user_id}.db` SQLite database with integrated vector capabilities.
- **Modern Authentication** — Built-in OAuth 2.1 flow with PKCE, integrating seamlessly with client environments and supporting "Sign in with Google."

---

## 🛠️ Tech Stack

### Chrome Extension (`/extension`)
* **Framework:** [WXT](https://wxt.dev/) (Web Extension Framework)
* **Frontend:** React 19, TypeScript
* **Styling:** Tailwind CSS, Radix UI, Base UI
* **Package Manager:** `pnpm`
* **Test Suite:** Vitest

### MCP Backend & Auth Server (`/mcp`)
* **Core:** Python 3.11+, FastAPI
* **MCP Integration:** MCP Python SDK (over HTTP + Server-Sent Events)
* **Database:** SQLite (with FTS5 & `sqlite-vec` extension)
* **LLM Integrations:** Gemini Flash (Summarization) & Gemini Embeddings 2 (Semantic vectors)
* **Authentication:** OAuth 2.1 + PKCE with JWT Bearer validation

---

## 📁 Repository Structure

```text
├── .agents/             # Symlinked AI agent configurations & tools
├── .claude/             # Symlinked Claude-specific skills (shareable)
├── docs/                # Product specifications and designs
│   └── spec.md          # Core architecture & database schema spec
├── extension/           # Chrome Extension (WXT, React 19, TS)
└── mcp/                 # Remote MCP Server & Backend (FastAPI, SQLite)
```

---

## 🚀 Getting Started

### Prerequisites
* [Node.js](https://nodejs.org/) (v18+)
* [pnpm](https://pnpm.io/) (v8+)
* [Python](https://www.python.org/) (v3.11+)

---

### 1. Setting up the Chrome Extension

Navigate to the `extension/` directory:
```bash
cd extension
```

Install dependencies:
```bash
pnpm install
```

Start the development server (automatically launches a Chrome instance with the extension loaded):
```bash
pnpm dev
```

Build the extension for production:
```bash
# Chrome / Edge
pnpm build

# Firefox
pnpm build:firefox
```

Run test suite:
```bash
pnpm test
```

---

### 2. Setting up the MCP Backend

Navigate to the `mcp/` directory:
```bash
cd mcp
```

Create a virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt  # Note: API implementation is in progress
```

Detailed implementation configurations and database setup are detailed in the product specification: [docs/spec.md](docs/spec.md).

---

## 💡 Developer Guidelines & Coding Standards

Contributors should adhere to the following:
* **DRY & YAGNI:** Avoid code duplication and focus on required functionality rather than speculative enhancements.
* **SOLID Principles:** Write clean, modular, and single-responsibility components.
* **Database Security:** Maintain total user-isolation by strictly routing requests to `{user_id}.db`.
* **Consistent Conventions:** Keep to TypeScript naming rules on the frontend and PEP-8 on the backend.

For more details, see the [CONTRIBUTING.md](CONTRIBUTING.md) guide.

---

## 🤝 Contributing

We welcome contributions from the community! Feel free to report bugs, suggest features, or submit pull requests. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on code style, workflows, and submission processes.

---

## 📜 License

This project is licensed under the terms of the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for the full text.
