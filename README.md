# CPASS – foundation scaffold

Layout (copy into D:\CPASS, merge with your existing folders):

    CPASS/
      .gitignore            (you already have it)
      backend/              FastAPI + Supabase (service role, server-side only)
      frontend/             React + Vite (anon key only)
      supabase/migrations/  SQL to run in the Supabase SQL Editor

## 1. Database (Supabase)
1. Supabase dashboard -> SQL Editor -> paste `supabase/migrations/0001_foundation.sql` -> Run.
2. Authentication -> Users -> Add user (email + password, tick "Auto confirm").
3. Make that user an admin (replace the id and email):

       insert into profiles (id, full_name, email, role)
       values ('<auth user uuid>', 'Your Name', 'you@example.com', 'ADMIN');

4. Settings -> API: copy Project URL, `anon` key and `service_role` key.

## 2. Backend
    cd D:\CPASS\backend
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    copy .env.example .env        (then fill the values)
    uvicorn app.main:app --reload --port 8000
Open http://localhost:8000/docs and http://localhost:8000/health.

Import the master Excel (put the file anywhere, pass its path):

    python -m scripts.import_master "D:\path\DDUGKY_ALL_STATES_MASTER_DATA.xlsx" --dry-run
    python -m scripts.import_master "D:\path\DDUGKY_ALL_STATES_MASTER_DATA.xlsx"

## 3. Frontend
    cd D:\CPASS\frontend
    npm create vite@latest . -- --template react      (answer: ignore files / keep)
    npm install @supabase/supabase-js react-router-dom
    (now copy the `frontend/src/*` and `.env.example` from this scaffold over the generated ones)
    copy .env.example .env.local   (fill the values)
    npm run dev                    -> http://localhost:5173

## Key rules
- `service_role` key lives ONLY in backend/.env. Never in frontend, never in git.
- Browser talks to the backend with the user's Supabase access token; the backend checks the role and centre scope.
- All master tables have Row-Level Security ON with no public policies, so the anon key cannot read them directly.
