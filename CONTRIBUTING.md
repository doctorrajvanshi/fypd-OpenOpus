# Contributing to fypd

We are thrilled that you are interested in contributing to **fypd**! Whether you want to fix a bug, add a visual style template, or implement a publishing publisher target, your contributions are highly welcome.

Here is a quick guide to help you set up your developer environment and submit pull requests cleanly.

---

## 🛠️ Developer Environment Setup

### 1. Unified Architecture Overview
fypd runs as a unified application:
*   **Backend (FastAPI):** `app_server.py` manages a sequential background task queue, handles static file serving, and orchestrates LiteLLM calls.
*   **Frontend (React + Vite + Tailwind):** Sourced in the `/frontend` directory and builds static assets into `/dist_frontend` for the FastAPI server to serve directly.
*   **Video Engine (Python):** `viral_clipper.py` manages the localized frame rendering, computer vision, and Whisper transcription.

### 2. Running in Development Mode
To work on the frontend with hot-reloading (HMR):
1.  Launch the FastAPI backend server:
    ```bash
    python app_server.py
    ```
    The backend runs on `http://127.0.0.1:8000`.
2.  Start the Vite frontend development server:
    ```bash
    cd frontend
    npm run dev
    ```
    The frontend runs on `http://localhost:5173`.
3.  Vite is configured to automatically proxy backend requests (`/jobs`, `/repurpose/*`, etc.) to the FastAPI server running on port 8000. Any frontend code changes you save will instantly hot-reload in the browser.

### 3. Rebuilding the Frontend Bundle
Before committing frontend edits or submitting pull requests, you must rebuild the static assets so the FastAPI server compiles the correct deployment bundle:
```bash
cd frontend
npm run build
```
Verify that the React code compiles successfully with TypeScript (`tsc -b && vite build`) and bundles cleanly into the `/dist_frontend` directory.

---

## 📝 Code Style & Standards

*   **Python:** Adhere to standard PEP 8 naming conventions. Keep rendering templates focused and clean. Preserve comments, docstrings, and Windows compatibility overrides inside `viral_clipper.py` and `app_server.py`.
*   **React / TypeScript:** Write clean functional components using modern hooks. Ensure that all CSS utility tokens align with standard Tailwind v4 definitions.
*   **No Hardcoded Secrets:** Never commit API keys, personal directories, or credentials. Always utilize local `.env` setups or `localStorage` bindings.

---

## 🚀 Pull Request Guidelines

1.  Fork the repository and create your branch from `main`:
    ```bash
    git checkout -b feature/your-awesome-feature
    ```
2.  Implement your changes, keep your commits focused and write descriptive commit messages.
3.  Verify that all builds pass cleanly (`npm run build` and `python -m py_compile app_server.py`).
4.  Open a Pull Request describing:
    *   What the PR accomplishes.
    *   Any UI/functional screenshots or walkthrough details.
    *   How you tested the changes manually.

Thank you for helping us build the ultimate Autonomous Content Factory! 🚀
