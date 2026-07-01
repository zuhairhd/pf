# Personal Finance SaaS

A personal finance SaaS application for managing accounts, budgets, bills, goals, investments, loans, tax profiles, documents, insights, and tenant-based financial records.

## Project Purpose

This project is designed as a multi-tenant personal finance system. It can be used to manage personal accounts and can later be extended as a SaaS platform where each tenant has isolated financial data.

## Main Features

- User and tenant-based finance management
- Accounts and balances
- Budgets and budget alerts
- Bills and recurring transactions
- Loans and loan tracking
- Investments
- Goals and contributions
- Documents
- Tax profiles and tax payments
- AI reports, insights, token usage, and chat sessions
- Audit logs and activity tracking
- PostgreSQL Row-Level Security support

## Technology Stack

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Redis
- Celery
- Docker support
- Pytest

## Project Structure

```text
pf/
|-- alembic/          Alembic migration files
|-- app/              Main application source code
|-- docker/           Docker-related files
|-- docs/             Documentation
|-- migrations/       Migration-related files
|-- scripts/          Utility scripts
|-- .env.example      Example environment variables
|-- alembic.ini       Alembic configuration
|-- requirements.txt  Python dependencies
|-- run.py            Application entry point
`-- README.md         Project documentation
```

## Local Setup

### 1. Activate virtual environment

```powershell
.\venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Create local environment file

```powershell
copy .env.example .env
```

Then edit `.env` and add your local database credentials and secret values.

Do not commit `.env`.

## Database Setup

Run Alembic migrations:

```powershell
alembic upgrade head
```

Create a new migration:

```powershell
alembic revision --autogenerate -m "Describe migration"
```

## Run the Application

```powershell
python run.py
```

## Run Tests

```powershell
pytest
```

## Security Notes

- Never commit `.env`
- Never commit real database passwords
- Never commit production secret keys
- Never commit API keys
- Keep `.env.example` with placeholder values only
- Use PostgreSQL Row-Level Security for tenant-scoped tables

## Git Workflow

Add the safe project files:

```powershell
git add .gitignore README.md .env.example requirements.txt run.py alembic.ini app alembic docker docs migrations scripts
```

Check what will be committed:

```powershell
git status
```

Commit:

```powershell
git commit -m "Initial personal finance SaaS project"
```

Set the main branch:

```powershell
git branch -M main
```

Add GitHub remote:

```powershell
git remote add origin https://github.com/zuhairhd/pf.git
```

Push to GitHub:

```powershell
git push -u origin main
```

If the remote already exists, use:

```powershell
git remote set-url origin https://github.com/zuhairhd/pf.git
git push -u origin main
```

## Important Files Not To Commit

The following files should stay local only:

```text
.env
venv/
.pytest_cache/
*.db
*.sqlite
*.sqlite3
logs/
uploads/
AI Personal Finance SaaS — World-Cl.txt
Database_sitting.txt
Find_Server.txt
prompt_*.txt
```

## License

Private project unless a license file is added.
