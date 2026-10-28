# Hosting: website online, backend on my laptop

## The short version
- **Website (front end)** is on Cloudflare Pages: https://resume-projects-1.pages.dev  — always online, free.
- **Sign-in** uses Supabase — always online, free. It does NOT need the backend.
- **Backend (the Python API + the big database)** runs on **my laptop**. It is only available while my laptop is on and the backend is started.

## What is the 2.1 GB file?
`storage/quant.duckdb` is **data, not code.** It is a DuckDB database holding:
- daily stock prices and features (~714,000 rows)
- news articles (~924,000) and their sentiment scores
- SEC filing facts (~670,000)
- macro data, market regimes, and the saved results of the alpha experiments

The code that reads it is in `app/`. The code is small; the data is what makes it 2.1 GB.
Because GitHub refuses files over 2 GiB, the repo stores it as a compressed zip: `storage/quant.duckdb.zip` (via Git LFS). Unzip it to get `storage/quant.duckdb`.

## What stays where
| Part | Where it runs | Online when laptop is off? |
|---|---|---|
| Website pages, design, login screen | Cloudflare | Yes |
| Sign-up / sign-in / Google login | Supabase | Yes |
| Data pages, dashboards, alpha results, chatbot-style API calls | Laptop backend | **No** |
| `quant.duckdb` (the data) | Laptop (and a zip backup on GitHub) | n/a |

## What happens with a backend-only laptop
- Backend OFF: the website loads and people can sign in, but data pages show errors or stay empty.
- Backend ON: the pages work **only for me, on this laptop**. The site calls `http://127.0.0.1:8000`, which means "this same computer". Another person's browser looks for a backend on *their* computer, finds nothing, and the data pages fail.
- To let other people see live data, the backend needs a public address. Options: a free tunnel (Cloudflare Tunnel) while the laptop stays on, or a paid host (Hugging Face PRO Docker Space, Render, Fly.io).

## How to run the backend on the laptop
1. Unzip the database (if starting from GitHub): extract `storage/quant.duckdb.zip` so you get `storage/quant.duckdb`.
2. In the project folder: `pip install -r requirements.txt`
3. Start it: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
4. Open https://resume-projects-1.pages.dev on this laptop — the data pages now talk to your backend.

Never put API keys (GROQ, GEMINI, FINNHUB) in GitHub. Keep them in a local `.env` file.
