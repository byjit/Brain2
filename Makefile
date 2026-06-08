# Makefile to manage Brain2 development services

.PHONY: help setup dev dev-backend dev-platform dev-extension dev-all test test-backend test-platform test-extension build build-platform build-extension clean clean-backend clean-platform clean-extension

# Default target: show help
help:
	@echo "========================================================================"
	@echo "                         Brain2 Developer Toolkit"
	@echo "========================================================================"
	@echo "Available commands:"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make setup           - Initialize all dependencies and environment files"
	@echo "  make setup-backend   - Set up backend dependencies (uv)"
	@echo "  make setup-platform  - Set up platform dependencies (pnpm)"
	@echo "  make setup-extension - Set up extension dependencies (pnpm)"
	@echo ""
	@echo "Development Servers:"
	@echo "  make dev             - Run backend + platform concurrently (Recommended)"
	@echo "  make dev-all         - Run backend + platform + extension concurrently"
	@echo "  make dev-backend     - Run backend development server"
	@echo "  make dev-platform    - Run platform development server"
	@echo "  make dev-extension   - Run extension development server"
	@echo ""
	@echo "Testing:"
	@echo "  make test            - Run all test suites (backend, platform, extension)"
	@echo "  make test-backend    - Run backend tests (pytest)"
	@echo "  make test-platform   - Run platform tests (vitest)"
	@echo "  make test-extension  - Run extension tests (vitest)"
	@echo ""
	@echo "Build:"
	@echo "  make build           - Build platform and extension production bundles"
	@echo "  make build-platform  - Build platform production bundle"
	@echo "  make build-extension - Build extension production bundle"
	@echo ""
	@echo "Clean:"
	@echo "  make clean           - Clean all build artifacts, caches, and node_modules"
	@echo "========================================================================"

# Env setup
.env:
	@if [ ! -f .env ]; then \
		echo "Creating root .env from .env.example..."; \
		cp .env.example .env; \
	fi

extension/.env:
	@if [ ! -f extension/.env ]; then \
		echo "Creating extension/.env from extension/.env.example..."; \
		cp extension/.env.example extension/.env; \
	fi

# Setup dependencies
setup: .env extension/.env setup-backend setup-platform setup-extension
	@echo "Setup complete! Please configure the credentials in your root '.env' file."

setup-backend:
	@echo "Setting up backend dependencies..."
	cd backend && uv sync

setup-platform:
	@echo "Setting up platform dependencies..."
	cd platform && pnpm install

setup-extension:
	@echo "Setting up extension dependencies..."
	cd extension && pnpm install

# Run development servers concurrently
dev: .env
	@echo "Starting backend and platform concurrently..."
	@(trap 'exit 0' INT; \
		cd backend && PYTHONUNBUFFERED=1 uv run uvicorn brain2.main:app --reload 2>&1 | awk '{print "[backend] " $$0; fflush()}' & \
		cd platform && FORCE_COLOR=1 pnpm dev 2>&1 | awk '{print "[platform] " $$0; fflush()}' & \
		wait)

dev-all: .env extension/.env
	@echo "Starting backend, platform, and extension concurrently..."
	@(trap 'exit 0' INT; \
		cd backend && PYTHONUNBUFFERED=1 uv run uvicorn brain2.main:app --reload 2>&1 | awk '{print "[backend] " $$0; fflush()}' & \
		cd platform && FORCE_COLOR=1 pnpm dev 2>&1 | awk '{print "[platform] " $$0; fflush()}' & \
		cd extension && FORCE_COLOR=1 pnpm dev 2>&1 | awk '{print "[extension] " $$0; fflush()}' & \
		wait)

dev-backend: .env
	@echo "Starting backend server (http://localhost:8000)..."
	cd backend && PYTHONUNBUFFERED=1 uv run uvicorn brain2.main:app --reload 2>&1 | awk '{print "[backend] " $$0; fflush()}'

dev-platform:
	@echo "Starting platform dashboard (http://localhost:3000)..."
	cd platform && FORCE_COLOR=1 pnpm dev 2>&1 | awk '{print "[platform] " $$0; fflush()}'

dev-extension: extension/.env
	@echo "Starting extension development server (WXT)..."
	cd extension && FORCE_COLOR=1 pnpm dev 2>&1 | awk '{print "[extension] " $$0; fflush()}'

# Run tests
test: test-backend test-platform test-extension

test-backend:
	@echo "Running backend tests..."
	cd backend && uv run pytest -q

test-platform:
	@echo "Running platform tests..."
	cd platform && pnpm test

test-extension:
	@echo "Running extension tests..."
	cd extension && pnpm test

# Build production bundles
build: build-platform build-extension

build-platform:
	@echo "Building platform production bundle..."
	cd platform && pnpm build

build-extension:
	@echo "Building extension production bundle..."
	cd extension && pnpm build

# Clean up build artifacts and dependency folders
clean: clean-backend clean-platform clean-extension

clean-backend:
	@echo "Cleaning backend..."
	rm -rf backend/.venv backend/.pytest_cache backend/__pycache__ backend/src/brain2/__pycache__

clean-platform:
	@echo "Cleaning platform..."
	rm -rf platform/node_modules platform/dist platform/.content-collections

clean-extension:
	@echo "Cleaning extension..."
	rm -rf extension/node_modules extension/.output extension/.wxt
