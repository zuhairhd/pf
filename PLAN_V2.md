# AI Personal CFO / Financial Digital Twin SaaS Platform

## PLAN_V2.md

**Version:** 2.0  
**Date:** 2026-07-01  
**Project Root:** `C:\dev\PF`  
**Supersedes:** All previous Flask personal accounting SaaS plans  
**Status:** Ready for Development

---

> **Important Notice:**  
> This plan supersedes the previous Flask personal accounting SaaS plan. The double-entry accounting engine remains as the foundational data layer, but the product is now organized around **AI financial intelligence**, **financial life**, and the **Financial Digital Twin**. The user experience is centered on understanding, improving, and predicting one's financial health — not on bookkeeping.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Updated Product Vision](#2-updated-product-vision)
3. [Updated Architecture Decisions](#3-updated-architecture-decisions)
4. [Why FastAPI is Now Selected](#4-why-fastapi-is-now-selected)
5. [Why Modular Monolith First](#5-why-modular-monolith-first)
6. [Product Navigation: Financial Life First](#6-product-navigation-financial-life-first)
7. [Normal User View vs Accountant View](#7-normal-user-view-vs-accountant-view)
8. [Updated Project Structure](#8-updated-project-structure)
9. [Updated Data Model Overview](#9-updated-data-model-overview)
10. [Financial Digital Twin Architecture](#10-financial-digital-twin-architecture)
11. [AI CFO Architecture](#11-ai-cfo-architecture)
12. [Tenant Security with PostgreSQL RLS](#12-tenant-security-with-postgresql-rls)
13. [Family Finance Architecture](#13-family-finance-architecture)
14. [Import Strategy: Oman/Middle East Context](#14-import-strategy-omanmiddle-east-context)
15. [Updated Kanban Board](#15-updated-kanban-board)
16. [Updated Phases](#16-updated-phases)
17. [Detailed Kanban Cards](#17-detailed-kanban-cards)
18. [Migration from Old Plan to New Plan](#18-migration-from-old-plan-to-new-plan)
19. [Risks and Mitigations](#19-risks-and-mitigations)
20. [Final Build Order: First 30 Cards](#20-final-build-order-first-30-cards)

---

## 1. Executive Summary

We are building an **AI Personal CFO / Financial Digital Twin SaaS Platform** that transforms how individuals and families manage their financial lives. Unlike traditional accounting software that forces users to understand debits, credits, and ledgers, our platform hides the accounting engine and presents users with an intelligent, conversational, and predictive financial companion.

The platform learns from the user's financial data, builds a living "Financial Digital Twin," and proactively offers insights, warnings, recommendations, and simulations — all within a secure, multi-tenant SaaS architecture.

### Key Differentiators

- **AI as Core, Not Add-on:** The AI CFO is not a chatbot sidebar. It is the central intelligence that powers the dashboard, alerts, recommendations, and simulations.
- **Financial Digital Twin:** A living model of the user's financial life that continuously updates, forecasts, and simulates scenarios.
- **Hidden Accounting Engine:** Double-entry bookkeeping ensures data integrity, but users never see journal entries or ledgers unless they choose "Accountant View."
- **Family Finance:** Full support for shared accounts, private accounts, roles, permissions, and family goals.
- **Oman/Middle East Ready:** Built with OMR as default currency, Islamic finance considerations, and SMS/Excel import as primary data entry methods.

### Technology Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| Web Framework | FastAPI |
| ORM | SQLAlchemy 2.x |
| Migrations | Alembic |
| Database | PostgreSQL 15+ with Row-Level Security |
| Cache | Redis |
| Background Tasks | Celery + Redis |
| Frontend Templates | Jinja2 |
| Interactivity | HTMX |
| Styling | Bootstrap 5 |
| AI/LLM | OpenAI API (GPT-4o / GPT-4o-mini) or compatible |
| Containerization | Docker (Phase 2+) |
| CI/CD | GitHub Actions (Phase 2+) |

---

## 2. Updated Product Vision

### Product Name Candidates (To Be Finalized in Phase 0)

1. **AI Personal CFO** — Emphasizes the advisory, intelligent nature.
2. **Financial Digital Twin** — Emphasizes the living model and simulation capability.
3. **FinTwin** — Short, memorable brand name.
4. **CFO.ai** — Direct and clear.

> **Decision Required:** Final product name will be selected in Phase 0 card PF-000.

### Vision Statement

> "Every person and family deserves a personal CFO — an intelligent, always-available financial advisor that understands their complete financial picture, anticipates their needs, and guides them toward financial security and independence."

### Target Users

| User Type | Description |
|-----------|-------------|
| Individual | Single user managing personal finances |
| Family | Multiple members with shared and private accounts |
| Young Professional | Early career, building savings, managing debt |
| Family Head | Managing household budget, goals, children's accounts |
| Small Business Owner | Simple business accounting with personal overlap |
| Accountant/Advisor | External professional with read-only or managed access |

### Core Value Propositions

1. **Know Your Financial Self:** Complete, real-time understanding of your financial position.
2. **Never Miss a Beat:** Proactive alerts for bills, overspending, anomalies, and opportunities.
3. **Plan with Confidence:** Simulate future scenarios and get data-backed recommendations.
4. **Improve Continuously:** AI-powered insights that learn and adapt to your behavior.
5. **Family-First:** Manage household finances together while respecting privacy.

---

## 3. Updated Architecture Decisions

### Decision Log

| # | Decision | Status | Rationale |
|---|----------|--------|-----------|
| 1 | AI is the core, not a small module | **ACCEPTED** | This is the most important product change. The entire UX revolves around AI intelligence. |
| 2 | Financial Digital Twin is the flagship | **ACCEPTED** | Stronger positioning than "AI Chat" or "Health Score." Creates a living, evolving model. |
| 3 | Hide accounting from normal users | **ACCEPTED** | Keep double-entry engine for integrity, but show users simple financial life screens. |
| 4 | Add bank feeds / imports early | **ACCEPTED, PHASED** | Start with Excel, CSV, SMS import. Bank feeds come later due to Oman market realities. |
| 5 | Replace Flask with FastAPI | **ACCEPTED** | Starting fresh in `C:\dev\PF`. FastAPI is better for async, validation, OpenAPI, and scalability. |
| 6 | Build microservices | **REJECTED FOR V1** | Build modular monolith first. Extract services later only when clear boundaries and scale demand it. |
| 7 | Add PostgreSQL Row-Level Security | **ACCEPTED** | Stronger tenant isolation than application-level filtering alone. Defense in depth. |
| 8 | Build family finance as a full product | **ACCEPTED** | Not just "invite user." Needs shared accounts, private accounts, roles, permissions, family goals. |
| 9 | Add tax, estate, credit score, insurance | **DEFERRED** | Good future vision, but too much for v1. Focus on core financial life first. |
| 10 | Modular monolith with clear boundaries | **ACCEPTED** | Each module (ai_cfo, accounting, family, etc.) has clean internal structure. Future extraction possible. |
| 11 | AI never modifies data without approval | **ACCEPTED** | Safety rule. AI suggests, user approves. Audit trail for all AI-suggested actions. |
| 12 | OMR default, multi-currency planned | **ACCEPTED** | Oman market is primary. USD, AED, SAR, QAR, KWD, BHD support in v1. |
| 13 | SMS import for bank alerts | **ACCEPTED** | Critical for Oman where bank APIs are limited. Parse SMS alerts for automatic transaction creation. |
| 14 | Server-rendered UI first, SPA later | **ACCEPTED** | Jinja2 + HTMX + Bootstrap 5 for rapid development. API-first design enables future mobile/SPA. |

### Architecture Principles

1. **Security First:** Tenant isolation at database level (RLS) + application level.
2. **API-First:** Every feature is built as an API endpoint first. UI consumes the same API.
3. **Event-Driven Internally:** Use Celery tasks for background processing, AI generation, imports.
4. **Audit Everything:** Every financial change is logged with who, what, when, and why.
5. **Test at Every Level:** Unit tests for services, integration tests for APIs, end-to-end for critical paths.
6. **Document as We Build:** OpenAPI auto-generated from FastAPI. Architecture Decision Records (ADRs) for major decisions.

---

## 4. Why FastAPI is Now Selected

### Context

The previous plan used Flask. Since we are starting fresh in `C:\dev\PF`, we have the opportunity to select the best framework for the product's future.

### Why FastAPI Over Flask

| Factor | FastAPI | Flask |
|--------|---------|-------|
| **Async Support** | Native `async/await` for I/O-bound operations (AI calls, external APIs) | Requires extensions (e.g., Quart) |
| **Automatic Validation** | Pydantic models validate request/response automatically | Manual validation with Flask-WTF or marshmallow |
| **OpenAPI Documentation** | Auto-generated `/docs` and `/redoc` endpoints | Manual setup with Flask-RESTX or flasgger |
| **Type Safety** | Full Python type hints throughout | Optional, not enforced |
| **Performance** | ~3x faster than Flask for API workloads | Synchronous by default |
| **Modern Python** | Built for Python 3.8+ features | Older design, more boilerplate |
| **Dependency Injection** | Built-in `Depends()` system | Manual or with extensions |
| **Background Tasks** | Built-in `BackgroundTasks` + Celery integration | Celery only |
| **Learning Curve** | Moderate (familiar for Flask developers) | Gentle |
| **Ecosystem Maturity** | Rapidly growing, production-ready | Very mature, extensive plugins |

### Specific Benefits for This Project

1. **AI Integration:** Async endpoints can call OpenAI API without blocking the server.
2. **API-First Design:** Auto-generated OpenAPI docs mean mobile and third-party integrations are ready from day one.
3. **Validation:** Pydantic schemas for transactions, budgets, goals ensure data integrity at the API boundary.
4. **Future Mobile App:** A React Native or Flutter app can consume the same FastAPI endpoints the web UI uses.
5. **WebSocket Support:** Built-in WebSocket support for real-time AI chat and notifications.

### Trade-offs Accepted

- **Learning Curve:** Team must learn Pydantic and FastAPI patterns. Mitigation: FastAPI is intuitive for Flask developers.
- **Ecosystem:** Some Flask extensions don't have FastAPI equivalents. Mitigation: Most needs (auth, ORM, migrations) are framework-agnostic.
- **Opinionated:** FastAPI is more opinionated than Flask. Mitigation: Opinions align with our goals (validation, async, types).

---

## 5. Why Modular Monolith First

### The Microservices Temptation

It is tempting to design microservices early: `auth-service`, `accounting-service`, `ai-service`, `notification-service`. This feels clean and "enterprise-grade."

### Why We Reject Microservices for V1

| Concern | Microservices | Modular Monolith |
|--------|---------------|------------------|
| **Team Size** | Needs multiple teams to justify overhead | Single developer/small team can manage |
| **Operational Complexity** | Kubernetes, service mesh, distributed tracing, circuit breakers | Single deploy, single logs, single monitor |
| **Database per Service** | Complex transactions, eventual consistency challenges | Single PostgreSQL database, ACID transactions |
| **Development Speed** | Slower: API contracts, versioning, cross-service testing | Faster: refactor within codebase, direct function calls |
| **Debugging** | Distributed tracing required | Stack traces show full call chain |
| **Deployment** | Multiple pipelines, blue-green per service | One pipeline, one artifact |
| **Cost** | Multiple running instances, inter-service networking | Single instance, efficient resource use |
| **Refactoring** | Hard to change service boundaries | Easy to move code between modules |

### Our Strategy: Modular Monolith with Extraction Path

```
Current (V1):                    Future (V2+):
┌─────────────────────┐          ┌─────────┐ ┌─────────┐ ┌─────────┐
│   Modular Monolith  │    →     │  Auth   │ │Accounting│ │  AI     │
│                     │          │ Service │ │ Service │ │ Service │
│  ┌─────────────┐    │          └─────────┘ └─────────┘ └─────────┘
│  │  identity   │    │
│  ├─────────────┤    │          ┌─────────┐ ┌─────────┐
│  │  tenants    │    │          │ Family  │ │ Notify  │
│  ├─────────────┤    │          │ Service │ │ Service │
│  │  accounting │    │          └─────────┘ └─────────┘
│  ├─────────────┤    │
│  │  ai_cfo     │    │
│  ├─────────────┤    │
│  │  family     │    │
│  └─────────────┘    │
└─────────────────────┘
```

### Module Boundaries

Each module is a self-contained unit with:
- Its own `models.py`, `schemas.py`, `services.py`, `routes.py`
- Its own `permissions.py` for access control
- Its own `tasks.py` for background jobs
- Its own `tests/` directory
- Clear imports: modules can import from `core` and `core.db`, but cross-module imports go through service layers, not direct model access.

### When to Extract a Service

1. **Independent Scaling:** One module needs 10x the resources of others.
2. **Independent Deployment:** One module changes 10x more frequently.
3. **Team Growth:** A dedicated team can own a module end-to-end.
4. **Technology Mismatch:** A module needs a different language or database.
5. **Failure Isolation:** A module's crashes must not affect others.

> **Rule:** Do not extract until at least two of the above conditions are met.

---

## 6. Product Navigation: Financial Life First

### Normal User Navigation (Primary)

These are the main screens a typical user sees. The accounting engine is completely hidden.

```
┌─────────────────────────────────────────────────────────────┐
│  🏠 Today                    ← Daily snapshot, AI brief      │
│  📅 This Month               ← Monthly overview, cash flow   │
│  💸 Cash Flow                ← Income vs expenses, trends    │
│  🧾 Bills                    ← Upcoming, paid, overdue       │
│  📺 Subscriptions            ← Recurring, tracking, alerts   │
│  🎯 Goals                    ← Savings goals, progress       │
│  💳 Debt                     ← Loans, credit cards, optimizer │
│  🏦 Savings                  ← Accounts, rates, projections  │
│  📊 Net Worth                ← Assets - liabilities, history │
│  🤖 AI CFO                   ← Chat, insights, simulations   │
│  👨‍👩‍👧 Family Finance          ← Shared accounts, members      │
│  📁 Documents                ← Receipts, statements, OCR    │
│  ⚙️  Settings                 ← Profile, currency, alerts    │
└─────────────────────────────────────────────────────────────┘
```

### Advanced / Accountant View (Secondary)

Hidden behind "Advanced" or "Accountant Mode" toggle. Only for power users, accountants, or debugging.

```
┌─────────────────────────────────────────────────────────────┐
│  📒 Chart of Accounts        ← Full COA, account types       │
│  📝 Journal Entries          ← Manual double-entry posts    │
│  📋 General Ledger           ← Transaction history by account│
│  ⚖️  Trial Balance            ← Debits = Credits verification  │
│  🏛️  Admin / Reports         ← System admin, audit logs     │
└─────────────────────────────────────────────────────────────┘
```

### Navigation Philosophy

- **Today First:** The default landing page is "Today" — a daily briefing of what matters now.
- **Time-Based Views:** "This Month" is the primary time window. Users can drill into "This Week" or "Custom Range."
- **Action-Oriented:** Each screen suggests actions: "Pay this bill," "Review this subscription," "Increase this savings."
- **AI-Enhanced:** Every screen has an "Ask AI" button that provides context-aware help.

---

## 7. Normal User View vs Accountant View

### Design Principle

> "The accounting engine is the foundation, not the facade."

### Normal User View

| Feature | How It Appears |
|---------|---------------|
| Transactions | Simple list: date, description, amount, category, account. No debit/credit terminology. |
| Accounts | "My Accounts" — bank accounts, wallets, credit cards. Balances shown clearly. |
| Transfers | "Move money from Account A to Account B" — simple form. |
| Categories | "Spending categories" — Dining, Transport, Bills, etc. |
| Income | "Money In" — salary, freelance, gifts, etc. |
| Expenses | "Money Out" — spending, bills, transfers out. |
| Reconciliation | "Match with bank statement" — simple checkbox or import matching. |
| Reports | "How am I doing?" — charts, summaries, plain language. |

### Accountant View

| Feature | How It Appears |
|---------|---------------|
| Chart of Accounts | Full hierarchical COA with account codes, types, parent-child relationships. |
| Journal Entries | Manual JE form with debit/credit lines, narration, reference numbers. |
| General Ledger | Account-wise transaction history with running balances. |
| Trial Balance | Debits and credits summarized by account, with imbalance warnings. |
| Audit Trail | Complete history of who changed what, when, and from what to what. |
| Account Reconciliation | Full reconciliation workflow with statement balances, differences, adjustments. |

### Switching Between Views

- Normal users never see accountant view unless they explicitly enable it in Settings > Advanced.
- Accountants invited to a family/tenant can default to accountant view.
- All data created in normal view flows through the double-entry engine automatically. The user doesn't need to know.

### Example: A Simple Transaction

**Normal User Sees:**
```
You spent RO 12.500 at Starbucks on July 1
Category: Dining Out
Account: Bank Muscat Debit
```

**Behind the Scenes (Accounting Engine):**
```
Debit:  Expenses:Dining Out      RO 12.500
Credit: Assets:Bank Muscat       RO 12.500
```

**Accountant Sees:**
```
JE-2026-0001 | July 1, 2026
Dr. 5300 Dining Out              RO 12.500
Cr. 1100 Bank Muscat             RO 12.500
Narration: Starbucks purchase
```

---

## 8. Updated Project Structure

```
C:/dev/PF/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app factory, lifespan events
│   ├── config.py                  # Settings, env vars, Pydantic Settings
│   ├── dependencies.py            # FastAPI Depends() reusables
│   ├── core/                      # Shared infrastructure
│   │   ├── __init__.py
│   │   ├── db.py                  # SQLAlchemy engine, session, base
│   │   ├── rls.py                 # PostgreSQL RLS setup and helpers
│   │   ├── security.py            # Password hashing, JWT, encryption
│   │   ├── logging.py             # Structured logging setup
│   │   ├── exceptions.py          # Custom exceptions, exception handlers
│   │   ├── middleware.py          # Tenant, auth, logging middleware
│   │   ├── pagination.py          # Common pagination schemas
│   │   └── enums.py               # Shared enums (AccountType, etc.)
│   ├── identity/                  # Authentication & user management
│   │   ├── __init__.py
│   │   ├── models.py              # User, UserProfile, PasswordReset
│   │   ├── schemas.py             # Pydantic request/response models
│   │   ├── services.py            # Registration, login, password reset
│   │   ├── routes.py              # /auth/*, /users/* endpoints
│   │   ├── permissions.py         # Role definitions, access checks
│   │   └── tests/
│   ├── tenants/                   # Multi-tenant SaaS foundation
│   │   ├── __init__.py
│   │   ├── models.py              # Tenant, TenantMember, Subscription, Plan
│   │   ├── schemas.py
│   │   ├── services.py            # Tenant creation, member management
│   │   ├── routes.py              # /tenants/*, /subscriptions/*
│   │   ├── permissions.py         # Tenant-level access control
│   │   └── tests/
│   ├── accounting/                # Double-entry engine (hidden from normal users)
│   │   ├── __init__.py
│   │   ├── models.py              # Account, JournalEntry, JournalEntryLine
│   │   ├── schemas.py
│   │   ├── services.py            # Posting engine, balance calculations
│   │   ├── routes.py              # /accounting/* (advanced endpoints)
│   │   ├── permissions.py
│   │   └── tests/
│   ├── transactions/              # User-facing transaction management
│   │   ├── __init__.py
│   │   ├── models.py              # Transaction, TransactionSplit, Attachment
│   │   ├── schemas.py
│   │   ├── services.py            # Create, update, delete, search
│   │   ├── routes.py              # /transactions/*, /transfers/*
│   │   ├── permissions.py
│   │   └── tests/
│   ├── budgets/                   # Budgeting module
│   │   ├── __init__.py
│   │   ├── models.py              # Budget, BudgetCategory, BudgetPeriod
│   │   ├── schemas.py
│   │   ├── services.py            # Budget creation, vs-actual, alerts
│   │   ├── routes.py              # /budgets/*
│   │   ├── permissions.py
│   │   └── tests/
│   ├── goals/                     # Financial goals
│   │   ├── __init__.py
│   │   ├── models.py              # Goal, GoalContribution, GoalMilestone
│   │   ├── schemas.py
│   │   ├── services.py            # Goal tracking, projections
│   │   ├── routes.py              # /goals/*
│   │   ├── permissions.py
│   │   └── tests/
│   ├── loans/                     # Debt and loan management
│   │   ├── __init__.py
│   │   ├── models.py              # LoanAccount, LoanPayment, RepaymentSchedule
│   │   ├── schemas.py
│   │   ├── services.py            # Interest calc, snowball/avalanche
│   │   ├── routes.py              # /loans/*
│   │   ├── permissions.py
│   │   └── tests/
│   ├── bills/                     # Bill tracking and reminders
│   │   ├── __init__.py
│   │   ├── models.py              # Bill, BillInstance, BillReminder
│   │   ├── schemas.py
│   │   ├── services.py            # Bill creation, due date tracking
│   │   ├── routes.py              # /bills/*
│   │   ├── permissions.py
│   │   └── tests/
│   ├── subscriptions/             # Subscription tracking
│   │   ├── __init__.py
│   │   ├── models.py              # Subscription, SubscriptionPayment
│   │   ├── schemas.py
│   │   ├── services.py            # Detect duplicates, upcoming renewals
│   │   ├── routes.py              # /subscriptions/*
│   │   ├── permissions.py
│   │   └── tests/
│   ├── imports/                   # Data import (CSV, Excel, SMS, bank feeds)
│   │   ├── __init__.py
│   │   ├── models.py              # ImportJob, ImportMapping, ImportedRow
│   │   ├── schemas.py
│   │   ├── services.py            # Parsers, mappers, validators
│   │   ├── routes.py              # /imports/*
│   │   ├── parsers/               # CSV, Excel, SMS, OFX, QIF parsers
│   │   │   ├── __init__.py
│   │   │   ├── csv_parser.py
│   │   │   ├── excel_parser.py
│   │   │   ├── sms_parser.py
│   │   │   └── bank_feed_parser.py
│   │   ├── permissions.py
│   │   └── tests/
│   ├── documents/                 # Receipt and document management
│   │   ├── __init__.py
│   │   ├── models.py              # Document, DocumentCategory
│   │   ├── schemas.py
│   │   ├── services.py            # Upload, OCR, AI receipt reading
│   │   ├── routes.py              # /documents/*
│   │   ├── permissions.py
│   │   └── tests/
│   ├── ai_cfo/                    # AI Financial Coach / Digital Twin
│   │   ├── __init__.py
│   │   ├── models.py              # AIInsight, AIConversation, AIDigitalTwin
│   │   ├── schemas.py
│   │   ├── services.py            # Orchestrator, individual AI services
│   │   ├── routes.py              # /ai/*, /ai/chat/*
│   │   ├── engines/               # Individual AI engines
│   │   │   ├── __init__.py
│   │   │   ├── health_engine.py
│   │   │   ├── cashflow_engine.py
│   │   │   ├── spending_engine.py
│   │   │   ├── debt_optimizer.py
│   │   │   ├── savings_optimizer.py
│   │   │   ├── goal_planner.py
│   │   │   ├── whatif_simulator.py
│   │   │   ├── recommendation_engine.py
│   │   │   ├── daily_brief.py
│   │   │   ├── weekly_review.py
│   │   │   ├── monthly_review.py
│   │   │   └── proactive_alerts.py
│   │   ├── llm/                   # LLM integration layer
│   │   │   ├── __init__.py
│   │   │   ├── client.py          # OpenAI client wrapper
│   │   │   ├── prompts.py         # Prompt templates
│   │   │   ├── cost_control.py    # Token tracking, budget limits
│   │   │   └── safety.py          # Safety filters, disclaimer injection
│   │   ├── permissions.py
│   │   └── tests/
│   ├── family/                    # Family finance module
│   │   ├── __init__.py
│   │   ├── models.py              # Family, FamilyMember, FamilyAccountAccess
│   │   ├── schemas.py
│   │   ├── services.py            # Member management, access control
│   │   ├── routes.py              # /family/*
│   │   ├── permissions.py         # Role-based access (parent, child, viewer)
│   │   └── tests/
│   ├── notifications/             # Notifications (email, push, SMS)
│   │   ├── __init__.py
│   │   ├── models.py              # Notification, NotificationPreference
│   │   ├── schemas.py
│   │   ├── services.py            # Send notifications, queue management
│   │   ├── routes.py              # /notifications/*
│   │   ├── channels/              # Email, push, SMS, WhatsApp
│   │   │   ├── __init__.py
│   │   │   ├── email.py
│   │   │   ├── push.py
│   │   │   └── sms.py
│   │   ├── permissions.py
│   │   └── tests/
│   ├── reports/                   # Financial reports
│   │   ├── __init__.py
│   │   ├── models.py              # Report, ReportSchedule
│   │   ├── schemas.py
│   │   ├── services.py            # Report generation, scheduling
│   │   ├── routes.py              # /reports/*
│   │   ├── generators/            # Income statement, balance sheet, etc.
│   │   │   ├── __init__.py
│   │   │   ├── income_statement.py
│   │   │   ├── balance_sheet.py
│   │   │   ├── cash_flow.py
│   │   │   ├── net_worth.py
│   │   │   └── expense_analysis.py
│   │   ├── permissions.py
│   │   └── tests/
│   ├── admin/                     # Super admin and tenant admin
│   │   ├── __init__.py
│   │   ├── models.py              # AdminAction, SystemSetting
│   │   ├── schemas.py
│   │   ├── services.py            # User management, subscription oversight
│   │   ├── routes.py              # /admin/*
│   │   ├── permissions.py         # Super admin checks
│   │   └── tests/
│   ├── api/                       # Public API (for future integrations)
│   │   ├── __init__.py
│   │   ├── schemas.py             # API key, webhook models
│   │   ├── services.py            # API key management, webhook delivery
│   │   ├── routes.py              # /api/v1/*
│   │   ├── permissions.py         # API key auth
│   │   └── tests/
│   ├── static/                    # CSS, JS, images
│   │   ├── css/
│   │   ├── js/
│   │   └── images/
│   ├── templates/                 # Jinja2 templates
│   │   ├── base.html
│   │   ├── partials/
│   │   ├── pages/
│   │   └── emails/
│   └── tasks/                     # Celery task definitions
│       ├── __init__.py
│       ├── celery_app.py          # Celery app configuration
│       ├── ai_tasks.py            # AI generation tasks
│       ├── import_tasks.py        # Background import processing
│       ├── notification_tasks.py  # Scheduled notifications
│       └── report_tasks.py        # Scheduled report generation
├── alembic/                       # Database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── tests/                         # Integration and E2E tests
│   ├── conftest.py
│   ├── integration/
│   └── e2e/
├── scripts/                       # Utility scripts
│   ├── setup_dev.py
│   ├── seed_data.py
│   └── generate_keys.py
├── docs/                          # Architecture docs, ADRs
│   ├── adr/
│   └── api/
├── docker/                        # Docker files (Phase 2+)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── nginx.conf
├── requirements.txt               # Python dependencies
├── requirements-dev.txt           # Dev dependencies
├── pytest.ini                     # Test configuration
├── .env.example                   # Environment variable template
├── .gitignore
├── README.md
└── run.py                         # Development entry point
```

---

## 9. Updated Data Model Overview

### Core Entities

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TENANT ISOLATION                            │
│  Every table below has tenant_id. RLS policies enforce access.      │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Tenant     │────<│ TenantMember │────>│    User      │
│  (SAAS)      │     │  (SAAS)      │     │  (IDENTITY)  │
└──────────────┘     └──────────────┘     └──────────────┘
       │
       │ has many
       ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Account     │────<│ Transaction  │────>│  Category    │
│(ACCOUNTING)  │     │(TRANSACTIONS)│     │(TRANSACTIONS)│
└──────────────┘     └──────────────┘     └──────────────┘
       │
       │ has many
       ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│JournalEntry  │────<│JournalEntry  │     │   Budget     │
│  (ACCOUNTING)│     │   Line       │     │  (BUDGETS)   │
└──────────────┘     └──────────────┘     └──────────────┘
                                              │
       ┌──────────────┐     ┌──────────────┐   │
       │    Goal      │     │    Loan      │   │
       │  (GOALS)     │     │  (LOANS)     │   │
       └──────────────┘     └──────────────┘   │
                                                │
       ┌──────────────┐     ┌──────────────┐   │
       │    Bill      │     │ Subscription │   │
       │  (BILLS)     │     │(SUBSCRIPTIONS)│  │
       └──────────────┘     └──────────────┘   │
                                                │
       ┌──────────────┐     ┌──────────────┐   │
       │   Family     │────<│FamilyMember  │   │
       │  (FAMILY)    │     │  (FAMILY)    │   │
       └──────────────┘     └──────────────┘   │
                                                │
       ┌──────────────┐     ┌──────────────┐   │
       │  AIInsight   │     │AIDigitalTwin │   │
       │  (AI_CFO)    │     │  (AI_CFO)    │   │
       └──────────────┘     └──────────────┘   │
                                                │
       ┌──────────────┐     ┌──────────────┐   │
       │  Document    │     │  ImportJob   │   │
       │ (DOCUMENTS)  │     │  (IMPORTS)   │   │
       └──────────────┘     └──────────────┘   │
                                                │
       ┌──────────────┐     ┌──────────────┐   │
       │ Notification │     │    Report    │   │
       │(NOTIFICATIONS)│    │  (REPORTS)   │   │
       └──────────────┘     └──────────────┘   │
```

### Key Model Design Principles

1. **Tenant Isolation:** Every table has `tenant_id`. PostgreSQL RLS policies ensure users only see their tenant's data.
2. **Audit Trail:** All financial tables have `created_at`, `updated_at`, `created_by`, `updated_by`.
3. **Soft Deletes:** Financial records use soft deletes (`deleted_at`) to preserve historical integrity.
4. **Currency:** All monetary amounts stored as `Decimal(19, 4)` in base currency. Exchange rates stored separately.
5. **Double Entry:** Every user-facing transaction automatically generates a balanced journal entry.

### Simplified Entity Definitions

#### Tenant (tenants.models)
```python
class Tenant(Base):
    id: UUID
    name: str
    slug: str
    plan_id: UUID → Plan
    status: active/suspended/cancelled
    settings: JSONB
    created_at: datetime
    updated_at: datetime
```

#### User (identity.models)
```python
class User(Base):
    id: UUID
    email: str
    password_hash: str
    is_active: bool
    is_verified: bool
    last_login: datetime
    created_at: datetime
```

#### TenantMember (tenants.models)
```python
class TenantMember(Base):
    id: UUID
    tenant_id: UUID → Tenant
    user_id: UUID → User
    role: owner/admin/member/accountant/viewer
    is_primary: bool
    joined_at: datetime
```

#### Account (accounting.models)
```python
class Account(Base):
    id: UUID
    tenant_id: UUID → Tenant
    name: str
    code: str
    type: asset/liability/income/expense/equity
    parent_id: UUID → Account (optional)
    currency: str  # OMR, USD, etc.
    opening_balance: Decimal
    current_balance: Decimal
    is_system: bool
    is_active: bool
```

#### Transaction (transactions.models)
```python
class Transaction(Base):
    id: UUID
    tenant_id: UUID → Tenant
    account_id: UUID → Account
    category_id: UUID → Category
    date: date
    description: str
    amount: Decimal
    type: income/expense/transfer
    transfer_to_account_id: UUID → Account (optional)
    journal_entry_id: UUID → JournalEntry
    attachments: list[Attachment]
    is_reconciled: bool
    source: manual/import/bank_feed/ai_suggested
    status: pending/approved/rejected
```

#### JournalEntry (accounting.models)
```python
class JournalEntry(Base):
    id: UUID
    tenant_id: UUID → Tenant
    date: date
    reference: str
    narration: str
    total_debit: Decimal
    total_credit: Decimal
    is_balanced: bool
    source: manual/transaction/adjustment
    status: draft/posted/reversed
```

#### JournalEntryLine (accounting.models)
```python
class JournalEntryLine(Base):
    id: UUID
    journal_entry_id: UUID → JournalEntry
    account_id: UUID → Account
    debit: Decimal
    credit: Decimal
    description: str
```

#### AIDigitalTwin (ai_cfo.models)
```python
class AIDigitalTwin(Base):
    id: UUID
    tenant_id: UUID → Tenant
    user_id: UUID → User
    financial_health_score: int  # 0-100
    health_components: JSONB     # cash_flow, debt, savings, etc.
    cash_flow_forecast: JSONB    # 3, 6, 12 month projections
    risk_indicators: JSONB       # flagged risks
    last_updated: datetime
    last_analyzed: datetime
```

#### AIInsight (ai_cfo.models)
```python
class AIInsight(Base):
    id: UUID
    tenant_id: UUID → Tenant
    user_id: UUID → User
    type: health/cashflow/spending/debt/budget/savings/goal/alert
    severity: info/warning/critical/suggestion
    title: str
    description: str
    reasoning: str  # Human-readable explanation
    confidence_score: float  # 0.0 - 1.0
    suggested_action: str
    action_type: none/approve_reject/link
    is_read: bool
    is_actioned: bool
    created_at: datetime
```

---

## 10. Financial Digital Twin Architecture

### What is a Financial Digital Twin?

A Financial Digital Twin is a living, computational model of a user's financial life. It:
- **Mirrors** the user's actual financial state (accounts, transactions, debts, goals).
- **Updates** continuously as new data arrives.
- **Predicts** future states based on patterns and assumptions.
- **Simulates** "what-if" scenarios.
- **Recommends** actions to improve outcomes.

### Digital Twin Data Model

```
┌─────────────────────────────────────────────────────────────┐
│              FINANCIAL DIGITAL TWIN MODEL                    │
├─────────────────────────────────────────────────────────────┤
│  CURRENT STATE                                              │
│  ├── Income Profile (salary, freelance, passive)           │
│  ├── Expense Profile (fixed, variable, discretionary)        │
│  ├── Asset Profile (cash, investments, property)              │
│  ├── Liability Profile (loans, credit cards, mortgages)     │
│  ├── Cash Flow Pattern (monthly in/out, seasonality)          │
│  ├── Behavioral Patterns (spending triggers, habits)        │
│  └── Risk Exposure (no emergency fund, high debt, etc.)      │
├─────────────────────────────────────────────────────────────┤
│  PREDICTIVE STATE (3, 6, 12 months)                         │
│  ├── Projected Balances                                      │
│  ├── Projected Cash Flow                                     │
│  ├── Goal Achievement Timeline                             │
│  ├── Debt Payoff Timeline                                    │
│  └── Risk Forecasts                                          │
├─────────────────────────────────────────────────────────────┤
│  SIMULATION STATE (what-if scenarios)                       │
│  ├── Scenario: Save RO 50 more/month                        │
│  ├── Scenario: Buy a car (loan impact)                      │
│  ├── Scenario: Salary increase 10%                            │
│  ├── Scenario: Pay off credit card early                      │
│  └── Scenario: Emergency expense of RO 500                  │
├─────────────────────────────────────────────────────────────┤
│  RECOMMENDATION STATE                                       │
│  ├── Prioritized action list                                │
│  ├── Expected impact of each action                         │
│  ├── Confidence score for each recommendation               │
│  └── Human-readable reasoning                               │
└─────────────────────────────────────────────────────────────┘
```

### Digital Twin Update Cycle

```
New Data Arrives ──> Validate & Store ──> Update Twin State ──> Trigger AI Analysis
     │                                                              │
     │                                                              ▼
     │                                                    ┌─────────────────┐
     │                                                    │  AI Engines Run  │
     │                                                    │  • Health Score  │
     │                                                    │  • Cash Flow     │
     │                                                    │  • Spending      │
     │                                                    │  • Debt          │
     │                                                    │  • Savings       │
     │                                                    │  • Goals         │
     │                                                    └─────────────────┘
     │                                                              │
     │                                                              ▼
     │                                                    ┌─────────────────┐
     │                                                    │  Generate       │
     │                                                    │  Insights &     │
     │                                                    │  Recommendations│
     │                                                    └─────────────────┘
     │                                                              │
     ▼                                                              ▼
┌─────────────┐                                            ┌─────────────────┐
│  Store in   │                                            │  Notify User    │
│  Database   │                                            │  (if proactive) │
└─────────────┘                                            └─────────────────┘
```

### Digital Twin Components

| Component | Description | Data Sources |
|-----------|-------------|--------------|
| Income Profile | Regular, irregular, and passive income patterns | Transactions, user input |
| Expense Profile | Fixed, variable, and discretionary spending | Transactions, categories, budgets |
| Asset Profile | Current value and growth of all assets | Accounts, external valuations |
| Liability Profile | Outstanding debts, interest rates, payment schedules | Loans, credit cards |
| Cash Flow Pattern | Monthly net flow, seasonality, trends | Historical transactions |
| Behavioral Profile | Spending triggers, habits, anomalies | Transaction patterns, AI analysis |
| Risk Exposure | Emergency fund gap, debt-to-income, concentration risk | All of the above |

---

## 11. AI CFO Architecture

### AI is the Core, Not a Bolt-On

The AI CFO is not a chat interface added to an accounting app. It is the central intelligence that:
- Powers the dashboard's "Today" view
- Generates the Financial Health Score
- Creates proactive alerts
- Simulates future scenarios
- Recommends specific actions
- Answers user questions with full financial context

### AI Architecture Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                               │
│  Dashboard │ Chat │ Notifications │ Reports │ Settings              │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      AI ORCHESTRATOR SERVICE                         │
│  • Routes requests to correct engine                                  │
│  • Manages conversation context                                       │
│  • Enforces safety rules                                                │
│  • Tracks cost and token usage                                          │
│  • Injects disclaimers                                                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  REACTIVE MODE  │ │  PROACTIVE MODE │ │  PREDICTIVE MODE│
│  User asks      │ │  AI detects     │ │  AI forecasts   │
│  AI answers     │ │  and alerts     │ │  future issues  │
└─────────────────┘ └─────────────────┘ └─────────────────┘
              │               │               │
              ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      AI ENGINE POOL                                    │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐     │
│  │   Health    │ │   Cash Flow │ │   Spending  │ │    Debt     │     │
│  │   Engine    │ │   Engine    │ │   Engine    │ │  Optimizer  │     │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐     │
│  │   Savings   │ │    Goal     │ │   What-If   │ │     Bill    │     │
│  │  Optimizer  │ │   Planner   │ │  Simulator  │ │  Predictor  │     │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐     │
│  │Subscription │ │   Daily     │ │   Weekly    │ │   Monthly   │     │
│  │  Analyzer   │ │   Brief     │ │   Review    │ │   Review    │     │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                   │
│  │Recommendation│ │  Proactive  │ │    AI       │                   │
│  │   Engine    │ │   Alerts    │ │   Memory    │                   │
│  └─────────────┘ └─────────────┘ └─────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      LLM INTEGRATION LAYER                             │
│  • OpenAI GPT-4o / GPT-4o-mini client                                 │
│  • Prompt templates with financial context injection                    │
│  • Response parsing and validation                                    │
│  • Token usage tracking and cost control                              │
│  • Safety filtering and disclaimer injection                          │
│  • Confidence scoring                                                 │
│  • Fallback to rule-based when LLM unavailable                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DATA CONTEXT LAYER                                │
│  • Financial Digital Twin state (current, predicted, simulated)       │
│  • Historical transactions (aggregated, anonymized)                   │
│  • Budget vs actual data                                              │
│  • Goal progress and timelines                                        │
│  • Debt schedules and interest calculations                           │
│  • User preferences and risk tolerance                                │
└─────────────────────────────────────────────────────────────────────┘
```

### AI Operating Modes

| Mode | Trigger | Example | User Action |
|------|---------|---------|-------------|
| **Reactive** | User asks a question | "Can I afford a new car?" | AI answers with analysis |
| **Proactive** | AI detects an anomaly | "You spent 40% more on dining this month" | User reads and may act |
| **Predictive** | Scheduled forecast | "Your account balance may drop below RO 50 in 10 days" | User can prevent |
| **Prescriptive** | AI recommends action | "Pay your credit card first — it has 18% interest" | User approves or rejects |
| **Approval-Based** | AI suggests automation | "Shall I move RO 100 to your emergency fund?" | User must approve |

### AI Safety Rules

1. **Never Modify Data Without Approval:** AI can suggest, but never execute financial transactions, account changes, or data modifications without explicit user approval.
2. **Always Include Disclaimer:** Every AI response includes: "This is educational guidance, not professional financial advice."
3. **Confidence Scoring:** Every insight has a confidence score (0.0-1.0). Low confidence insights are flagged as "speculative."
4. **Human-Readable Reasoning:** AI must explain *why* it made a recommendation, not just state it.
5. **Cost Control:** Token usage is tracked per tenant. Alerts when approaching limits.
6. **Privacy:** Financial data is never sent to LLM providers in raw form. Use aggregated, anonymized summaries.
7. **Audit Trail:** Every AI suggestion and user response is logged.
8. **No Investment Advice:** AI never recommends specific stocks, funds, or investment products. It can suggest *categories* (e.g., "consider diversification").
9. **No Tax Advice:** AI never provides tax calculations or advice.
10. **Fallback:** If LLM is unavailable, rule-based engines provide basic insights.

### AI Memory

The AI maintains memory across sessions:
- **Short-term:** Current conversation context (last 10 messages).
- **Medium-term:** Recent insights and user reactions (last 30 days).
- **Long-term:** User preferences, risk tolerance, recurring patterns, dismissed recommendations.

Memory is stored in the `AIConversation` and `AIDigitalTwin` tables, not sent to the LLM provider.

---

## 12. Tenant Security with PostgreSQL RLS

### Why RLS?

Application-level tenant filtering (`WHERE tenant_id = ?`) is error-prone. A missed clause in one query can expose data. **PostgreSQL Row-Level Security (RLS)** enforces tenant isolation at the database level — the final line of defense.

### RLS Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│  • FastAPI routes validate JWT                              │
│  • Middleware extracts tenant_id from token                   │
│  • All queries include tenant_id filter (defense in depth)   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    DATABASE LAYER (RLS)                      │
│  • PostgreSQL RLS policies enforce tenant_id filtering       │
│  • Even if app forgets WHERE clause, RLS blocks access       │
│  • Policies use SET LOCAL to set current tenant context      │
└─────────────────────────────────────────────────────────────┘
```

### RLS Implementation

#### Step 1: Enable RLS on All Tenant Tables

```sql
-- Example for transactions table
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

-- Create policy
CREATE POLICY tenant_isolation_policy ON transactions
    USING (tenant_id = current_setting('app.current_tenant_id', true)::UUID);
```

#### Step 2: Set Tenant Context on Each Connection

```python
# In SQLAlchemy session setup
def set_tenant_context(session, tenant_id: UUID):
    session.execute(
        text("SET LOCAL app.current_tenant_id = :tenant_id"),
        {"tenant_id": str(tenant_id)}
    )
```

#### Step 3: Middleware Integration

```python
# FastAPI middleware extracts tenant from JWT and sets context
@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    tenant_id = extract_tenant_from_jwt(request)
    with db_session() as session:
        set_tenant_context(session, tenant_id)
        response = await call_next(request)
    return response
```

### RLS Policy Examples

| Table | Policy | Effect |
|-------|--------|--------|
| transactions | `tenant_id = current_setting('app.current_tenant_id')` | Users only see their tenant's transactions |
| accounts | Same | Users only see their tenant's accounts |
| users | Special: user sees self + tenant members | Users see themselves and other members of their tenant |
| ai_insights | Same | Users only see insights for their tenant |

### Super Admin Bypass

```sql
-- Super admin role bypasses RLS
CREATE POLICY admin_bypass ON transactions
    USING (current_user = 'admin');
```

### Performance Considerations

- RLS policies add a small overhead (~1-2ms per query).
- Ensure `tenant_id` is indexed on all tables.
- Use `SET LOCAL` (not `SET`) so context is session-scoped and reset on connection return to pool.

---

## 13. Family Finance Architecture

### Family Finance is a Full Product Module

Not just "invite user." Family finance includes:
- Shared accounts (visible to all family members)
- Private accounts (visible only to owner)
- Role-based permissions (parent, adult member, teen, child, viewer)
- Family goals (shared savings targets)
- Family budgets (shared spending limits)
- Allowances and chore tracking (for children)
- Spending visibility controls (parents see all, teens see own, children see limited)

### Family Data Model

```python
class Family(Base):
    id: UUID
    tenant_id: UUID → Tenant
    name: str
    head_id: UUID → User  # Primary family head
    settings: JSONB       # Allowance rules, visibility settings

class FamilyMember(Base):
    id: UUID
    family_id: UUID → Family
    user_id: UUID → User
    role: head/parent/adult/teen/child/viewer
    allowance_amount: Decimal  # For children/teens
    allowance_frequency: weekly/monthly
    can_see_all_accounts: bool
    can_see_all_transactions: bool
    can_create_transactions: bool
    can_create_budgets: bool
    can_manage_goals: bool
    can_invite_members: bool

class FamilyAccountAccess(Base):
    id: UUID
    family_id: UUID → Family
    account_id: UUID → Account
    member_id: UUID → FamilyMember
    access_level: full/view_only/none
```

### Family Roles and Permissions

| Role | Can See All Accounts | Can Create Transactions | Can Manage Budgets | Can Invite | Can See Others' Private |
|------|---------------------|------------------------|-------------------|------------|------------------------|
| Head | Yes | Yes | Yes | Yes | Yes |
| Parent | Yes | Yes | Yes | Yes | Yes |
| Adult | Configurable | Yes | Yes | No | No |
| Teen | Shared + Own | Yes (limited) | No | No | No |
| Child | Shared only | No | No | No | No |
| Viewer | Configurable | No | No | No | No |

### Family Features

1. **Shared Dashboard:** Family financial health score, combined net worth, shared goals.
2. **Individual Dashboard:** Personal spending, personal goals, private accounts.
3. **Allowances:** Automated allowance transfers to children's accounts.
4. **Chore Tracking:** Link chores to allowance payments (optional).
5. **Spending Alerts:** Parents get alerts when teen spending exceeds limits.
6. **Family Goals:** "Save for family vacation" — contributions from multiple members.
7. **Family Budgets:** "Monthly groceries budget" — tracked across all members.

---

## 14. Import Strategy: Oman/Middle East Context

### Context

In Oman and the broader Middle East:
- **Bank APIs are limited:** Open banking is not yet widespread.
- **SMS alerts are universal:** Every bank sends SMS alerts for transactions.
- **Excel/CSV exports are common:** Banks provide monthly statements in Excel.
- **Manual entry is tedious:** Users need frictionless import.

### Import Priority Order

```
Phase 1 (V1):          Phase 2 (V2):          Phase 3 (V3):
┌─────────────┐        ┌─────────────┐        ┌─────────────┐
│   Manual    │        │   OFX/QIF   │        │  Bank APIs  │
│   Entry     │   →    │   Import    │   →    │  (Open Bank)│
├─────────────┤        ├─────────────┤        ├─────────────┤
│  CSV Import │        │  PDF Parse  │        │  Plaid/Yodlee│
├─────────────┤        ├─────────────┤        ├─────────────┤
│ Excel Import│        │  Document   │        │  Real-time  │
├─────────────┤        │  OCR + AI   │        │  Sync       │
│  SMS Import │        └─────────────┘        └─────────────┘
└─────────────┘
```

### Import Methods

#### 1. Manual Entry
- Simple form: date, description, amount, category, account.
- Smart defaults: auto-suggest category based on description.
- Split transactions: one payment, multiple categories.
- Recurring flag: mark as repeating.

#### 2. CSV Import
- Upload CSV file.
- Column mapping UI: map CSV columns to app fields.
- Preview before import.
- Duplicate detection: match existing transactions.
- Template download: provide sample CSV for users.

#### 3. Excel Import
- Upload .xlsx file.
- Sheet selection (if multiple sheets).
- Header row detection.
- Same mapping, preview, and duplicate detection as CSV.
- Support for multiple currencies in one file.

#### 4. SMS Import
- **Critical for Oman market.**
- User forwards bank SMS to a dedicated number or copies/pastes into app.
- AI parses SMS content: bank name, amount, date, description, balance.
- Auto-creates transaction with suggested category.
- Supports major Omani banks: Bank Muscat, OAB, Alizz, Sohar International, etc.
- SMS patterns stored and learned from user corrections.

**Example SMS Parsing:**
```
SMS: "Bank Muscat: Your account ****1234 has been debited OMR 45.000 
      on 01-JUL-2026. Available balance: OMR 1,234.567. 
      Ref: CARREFOUR MALL OF OMAN"

Parsed:
  Bank: Bank Muscat
  Account: ****1234
  Type: Debit
  Amount: 45.000 OMR
  Date: 2026-07-01
  Description: CARREFOUR MALL OF OMAN
  Balance: 1234.567 OMR
  Suggested Category: Groceries
```

#### 5. Bank Feeds (Later)
- Direct API integration with banks (when available).
- Third-party providers: Plaid, Yodlee, Salt Edge (if they support Oman).
- Real-time or daily sync.
- Automatic reconciliation.

### Import Job Architecture

```python
class ImportJob(Base):
    id: UUID
    tenant_id: UUID → Tenant
    user_id: UUID → User
    type: csv/excel/sms/bank_feed
    status: pending/processing/preview/review/completed/failed
    file_path: str  # Stored temporarily
    mapping: JSONB  # Column mappings
    total_rows: int
    processed_rows: int
    imported_rows: int
    duplicate_rows: int
    error_rows: int
    errors: JSONB
    created_at: datetime
    completed_at: datetime
```

### Import Flow

```
User Uploads File ──> Validate Format ──> Parse Rows ──> Map Columns
                                                              │
                                                              ▼
User Reviews Mapping <── Preview Sample <── Detect Duplicates <── Suggest Categories
       │
       ▼
User Confirms ──> Import Transactions ──> Generate Journal Entries ──> Done
       │
       ▼
Errors Logged ──> User Can Fix and Retry
```

---

## 15. Updated Kanban Board

### Board Columns

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  BACKLOG │ → │  READY   │ → │  ANALYSIS│ → │DEVELOPMENT│ → │CODE REVIEW│
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
       │                                                              │
       ▼                                                              ▼
┌──────────┐                                                ┌──────────┐
│  ICEBOX  │                                                │  TESTING  │
│(Future)  │                                                └──────────┘
└──────────┘                                                       │
                                                                   ▼
                                                            ┌──────────┐
                                                            │    UAT   │
                                                            └──────────┘
                                                                   │
                                                                   ▼
                                                            ┌──────────┐
                                                            │READY FOR │
                                                            │ RELEASE  │
                                                            └──────────┘
                                                                   │
                                                                   ▼
                                                            ┌──────────┐
                                                            │ RELEASED │
                                                            └──────────┘
```

### Board Rules

1. **Backlog:** All known cards. Prioritized by epic and priority.
2. **Ready:** Cards with clear acceptance criteria, no blockers.
3. **Analysis:** Technical design, data model, API contract defined.
4. **Development:** Active coding. Branch naming: `feature/{card-id}`.
5. **Code Review:** PR created, reviewer assigned. Max 2 days in review.
6. **Testing:** QA, integration tests, security checks.
7. **UAT:** User acceptance testing (stakeholder demo).
8. **Ready for Release:** Merged to `main`, tagged.
9. **Released:** Deployed to production.

### WIP Limits

| Column | WIP Limit |
|--------|-----------|
| Ready | 5 |
| Analysis | 3 |
| Development | 5 |
| Code Review | 4 |
| Testing | 3 |

---

## 16. Updated Phases

### Phase 0: Product & Architecture Reframe (Week 1)

Before writing production code, establish the foundation decisions.

| Card ID | Title |
|---------|-------|
| PF-000 | Decide Final Product Name and Vision |
| PF-001 | Choose FastAPI Architecture and Document |
| PF-002 | Define Modular Monolith Boundaries |
| PF-003 | Define PostgreSQL RLS Tenant Strategy |
| PF-004 | Define Financial Digital Twin Model |
| PF-005 | Define AI CFO Safety Rules |
| PF-006 | Define User Navigation Around Financial Life |
| PF-007 | Define Normal User View vs Accountant View |
| PF-008 | Define Import Strategy (Manual, CSV, Excel, SMS) |
| PF-009 | Define MVP User Journey |
| PF-010 | Define Family Finance Model |
| PF-011 | Write PLAN_V2.md (This Document) |
| PF-012 | Setup Development Environment |
| PF-013 | Create Project Skeleton and Folder Structure |
| PF-014 | Setup PostgreSQL and Redis |
| PF-015 | Setup Git Repository and Branching Strategy |

### Phase 1: SaaS Foundation (Weeks 2-5)

Build the core platform that everything else depends on.

| Card ID | Title |
|---------|-------|
| PF-100 | Project Architecture & Configuration System |
| PF-101 | Database Layer: SQLAlchemy, Alembic, Base Models |
| PF-102 | Logging, Exception Handling, and Middleware |
| PF-103 | PostgreSQL RLS Implementation |
| SAAS-200 | Tenant Model and CRUD |
| SAAS-201 | Tenant Isolation Middleware |
| SAAS-202 | Subscription Plans (Free, Premium, Family) |
| SAAS-203 | Usage Limits and Quotas |
| AUTH-300 | User Registration |
| AUTH-301 | User Login and JWT |
| AUTH-302 | Forgot Password |
| AUTH-303 | Email Verification |
| AUTH-304 | Role-Based Access Control (RBAC) |
| AUTH-305 | Tenant Member Invitation |
| USR-400 | User Profile and Settings |
| USR-401 | Currency and Language Preferences |
| USR-402 | Theme and Notification Settings |
| ACC-500 | Chart of Accounts (Hidden Foundation) |
| ACC-501 | Account Types and Hierarchy |
| ACC-502 | Opening Balances |

### Phase 2: Financial Life MVP (Weeks 6-9)

Build the user-facing features that make the product useful.

| Card ID | Title |
|---------|-------|
| TRX-600 | Simple Transaction Entry |
| TRX-601 | Transaction List, Search, and Filter |
| TRX-602 | Split Transactions |
| TRX-603 | Transfer Between Accounts |
| TRX-604 | Transaction Categories |
| TRX-605 | Transaction Attachments |
| IMP-700 | CSV Import |
| IMP-701 | Excel Import |
| IMP-702 | SMS Import Parser |
| IMP-703 | Import Job Management UI |
| BILL-800 | Bill Creation and Tracking |
| BILL-801 | Bill Reminders and Alerts |
| SUB-900 | Subscription Tracking |
| SUB-901 | Subscription Renewal Alerts |
| BDG-1000 | Budget Creation |
| BDG-1001 | Budget Categories and Periods |
| BDG-1002 | Budget vs Actual |
| BDG-1003 | Overspending Alerts |
| DB-1100 | Dashboard Skeleton |
| DB-1101 | Today Screen (Daily Brief) |
| DB-1102 | Cash Flow Widget |
| DB-1103 | Net Worth Widget |
| DB-1104 | Bills and Subscriptions Widget |
| DB-1105 | Goals Widget |

### Phase 3: AI CFO / Digital Twin (Weeks 10-14)

Build the AI intelligence layer — the core differentiator.

| Card ID | Title |
|---------|-------|
| AI-1200 | AI Orchestrator Architecture |
| AI-1201 | LLM Client and Prompt Management |
| AI-1202 | Cost Control and Token Tracking |
| AI-1203 | AI Safety and Disclaimer System |
| AI-1204 | Financial Digital Twin Data Model |
| AI-1205 | Financial Health Engine |
| AI-1206 | Financial Health Score |
| AI-1207 | Cash Flow Intelligence Engine |
| AI-1208 | Spending Analyzer Engine |
| AI-1209 | Subscription Analyzer |
| AI-1210 | Bill Predictor |
| AI-1211 | Debt Optimizer |
| AI-1212 | Savings Optimizer |
| AI-1213 | Goal Planner |
| AI-1214 | What-If Simulator |
| AI-1215 | Recommendation Engine |
| AI-1216 | Daily Brief Generation |
| AI-1217 | Weekly Review Generation |
| AI-1218 | Monthly Review Generation |
| AI-1219 | Proactive Alerts Engine |
| AI-1220 | AI Chat Interface |
| AI-1221 | AI Memory System |
| AI-1222 | AI Confidence Scoring |
| AI-1223 | Dashboard v2 (AI-Centric) |

### Phase 4: Family, Automation, Admin, Billing (Weeks 15-18)

Expand to family use, administration, and monetization.

| Card ID | Title |
|---------|-------|
| FAM-1300 | Family Model and Roles |
| FAM-1301 | Shared and Private Accounts |
| FAM-1302 | Family Goals |
| FAM-1303 | Family Budgets |
| FAM-1304 | Allowance and Chore Tracking |
| FAM-1305 | Family Dashboard |
| GOAL-1400 | Goal Creation and Tracking |
| GOAL-1401 | Goal Contributions |
| GOAL-1402 | Goal Projections |
| LOAN-1500 | Loan Accounts |
| LOAN-1501 | Interest Calculation |
| LOAN-1502 | Repayment Schedule |
| LOAN-1503 | Snowball Strategy |
| LOAN-1504 | Avalanche Strategy |
| LOAN-1505 | Loan Simulator |
| NOTIF-1600 | Email Notifications |
| NOTIF-1601 | Push Notifications |
| NOTIF-1602 | Notification Preferences |
| NOTIF-1603 | Daily Summary Email |
| NOTIF-1604 | Monthly Summary Email |
| ADMIN-1700 | Super Admin Dashboard |
| ADMIN-1701 | Tenant Management |
| ADMIN-1702 | Subscription Management |
| ADMIN-1703 | Audit Logs |
| ADMIN-1704 | System Monitoring |
| BILLING-1800 | Stripe Integration |
| BILLING-1801 | Invoice Generation |
| BILLING-1802 | Payment Processing |
| BILLING-1803 | Billing History |

### Phase 5: Scale, API, Bank Feeds, Mobile (Weeks 19-24)

Scale the platform, add APIs, mobile, and advanced features.

| Card ID | Title |
|---------|-------|
| API-1900 | REST API v1 |
| API-1901 | OpenAPI Documentation |
| API-1902 | API Key Management |
| API-1903 | Webhooks |
| REP-2000 | Income Statement Report |
| REP-2001 | Balance Sheet Report |
| REP-2002 | Cash Flow Report |
| REP-2003 | Net Worth Report |
| REP-2004 | Expense Analysis Report |
| REP-2005 | Category Trends Report |
| DOC-2100 | Document Upload |
| DOC-2101 | OCR for Receipts |
| DOC-2102 | AI Receipt Reading |
| DOC-2103 | Document Categories |
| MOB-2200 | Responsive UI Improvements |
| MOB-2201 | PWA Support |
| MOB-2202 | Offline Support |
| FEED-2300 | Bank Feed Architecture |
| FEED-2301 | OFX/QIF Import |
| FEED-2302 | PDF Statement Parsing |
| FEED-2303 | Bank API Integration (When Available) |
| SCALE-2400 | Performance Optimization |
| SCALE-2401 | Caching Layer |
| SCALE-2402 | Database Indexing Strategy |
| SCALE-2403 | Background Job Optimization |
| SCALE-2404 | Docker Containerization |
| SCALE-2405 | CI/CD Pipeline |
| SCALE-2406 | Monitoring and Alerting |

---

## 17. Detailed Kanban Cards

### Phase 0: Product & Architecture Reframe

---

#### PF-000: Decide Final Product Name and Vision

**Card ID:** PF-000  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Select the final product name and write the product vision statement.

**Scope:**
- Evaluate name candidates: AI Personal CFO, Financial Digital Twin, FinTwin, CFO.ai
- Check domain name availability (optional)
- Write final vision statement
- Create product tagline
- Document target user personas

**Files / Modules Affected:**
- `docs/product/vision.md`
- `README.md` (update)

**Acceptance Criteria:**
- [ ] Product name is selected and documented
- [ ] Vision statement is written and approved
- [ ] Tagline is defined
- [ ] At least 3 user personas are documented
- [ ] Name is used consistently in all subsequent documentation

**Test Requirements:**
- N/A (decision document)

**Dependencies:**
- None

**Estimated Effort:** 2 hours

---

#### PF-001: Choose FastAPI Architecture and Document

**Card ID:** PF-001  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Document the FastAPI architecture decisions and create the architecture overview.

**Scope:**
- Document why FastAPI was chosen over Flask
- Define project structure conventions
- Define API design conventions (RESTful, versioning)
- Define dependency injection patterns
- Document async usage guidelines

**Files / Modules Affected:**
- `docs/adr/001-fastapi-over-flask.md`
- `docs/architecture/overview.md`

**Acceptance Criteria:**
- [ ] ADR-001 is written and committed
- [ ] Architecture overview document is complete
- [ ] API conventions are documented
- [ ] Dependency injection patterns are documented
- [ ] Async usage guidelines are documented

**Test Requirements:**
- N/A (documentation)

**Dependencies:**
- PF-000

**Estimated Effort:** 4 hours

---

#### PF-002: Define Modular Monolith Boundaries

**Card ID:** PF-002  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Define the module boundaries for the modular monolith and document the rules for cross-module communication.

**Scope:**
- List all modules and their responsibilities
- Define what each module owns (models, services, routes)
- Define cross-module communication rules (service layer only, no direct model access)
- Define shared core module contents
- Document extraction criteria for future microservices

**Files / Modules Affected:**
- `docs/architecture/modules.md`
- `docs/adr/002-modular-monolith.md`

**Acceptance Criteria:**
- [ ] All modules are defined with clear responsibilities
- [ ] Module ownership rules are documented
- [ ] Cross-module communication rules are documented
- [ ] Core module contents are defined
- [ ] Extraction criteria are documented

**Test Requirements:**
- N/A (documentation)

**Dependencies:**
- PF-001

**Estimated Effort:** 4 hours

---

#### PF-003: Define PostgreSQL RLS Tenant Strategy

**Card ID:** PF-003  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Document the PostgreSQL Row-Level Security strategy for tenant isolation.

**Scope:**
- Define RLS policy patterns for all tenant tables
- Define tenant context setting mechanism
- Define super admin bypass strategy
- Document performance considerations
- Define migration strategy for adding RLS to existing tables

**Files / Modules Affected:**
- `docs/architecture/tenant-security.md`
- `docs/adr/003-postgresql-rls.md`

**Acceptance Criteria:**
- [ ] RLS policy template is defined
- [ ] Tenant context mechanism is documented
- [ ] Super admin bypass is documented
- [ ] Performance considerations are documented
- [ ] Migration strategy is documented

**Test Requirements:**
- N/A (documentation)

**Dependencies:**
- PF-002

**Estimated Effort:** 4 hours

---

#### PF-004: Define Financial Digital Twin Model

**Card ID:** PF-004  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Document the Financial Digital Twin data model and update cycle.

**Scope:**
- Define Digital Twin entity and attributes
- Define update triggers (transaction added, bill paid, etc.)
- Define prediction algorithms (simple linear first, ML later)
- Define simulation input/output format
- Define confidence scoring approach

**Files / Modules Affected:**
- `docs/architecture/digital-twin.md`
- `docs/adr/004-financial-digital-twin.md`

**Acceptance Criteria:**
- [ ] Digital Twin entity model is documented
- [ ] Update triggers are defined
- [ ] Prediction approach is documented
- [ ] Simulation format is defined
- [ ] Confidence scoring is defined

**Test Requirements:**
- N/A (documentation)

**Dependencies:**
- PF-002

**Estimated Effort:** 6 hours

---

#### PF-005: Define AI CFO Safety Rules

**Card ID:** PF-005  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Document the AI safety rules, disclaimers, and guardrails.

**Scope:**
- Define all 10 safety rules (see Section 11)
- Define disclaimer text and injection mechanism
- Define confidence scoring thresholds
- Define fallback behavior when LLM is unavailable
- Define audit trail requirements for AI interactions
- Define what constitutes "financial advice" vs "educational guidance"

**Files / Modules Affected:**
- `docs/architecture/ai-safety.md`
- `docs/adr/005-ai-safety-rules.md`
- `app/ai_cfo/llm/safety.py` (stub)

**Acceptance Criteria:**
- [ ] All safety rules are documented
- [ ] Disclaimer mechanism is defined
- [ ] Confidence thresholds are defined
- [ ] Fallback behavior is documented
- [ ] Audit trail requirements are documented
- [ ] Legal review checklist is created

**Test Requirements:**
- N/A (documentation)

**Dependencies:**
- PF-004

**Estimated Effort:** 4 hours

---

#### PF-006: Define User Navigation Around Financial Life

**Card ID:** PF-006  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Document the user navigation structure organized around financial life, not accounting.

**Scope:**
- Define primary navigation items and their order
- Define secondary navigation (sub-menus)
- Define mobile navigation structure
- Define default landing page ("Today")
- Define navigation based on user role (individual vs family member vs accountant)

**Files / Modules Affected:**
- `docs/product/navigation.md`
- `docs/product/wireframes/` (optional)

**Acceptance Criteria:**
- [ ] Primary navigation is defined with descriptions
- [ ] Secondary navigation is defined
- [ ] Mobile navigation is defined
- [ ] Default landing page is specified
- [ ] Role-based navigation differences are documented

**Test Requirements:**
- N/A (documentation)

**Dependencies:**
- PF-000

**Estimated Effort:** 3 hours

---

#### PF-007: Define Normal User View vs Accountant View

**Card ID:** PF-007  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Document the distinction between normal user view and accountant view, including which features are hidden/shown.

**Scope:**
- Define all screens in normal user view
- Define all screens in accountant view
- Define how users switch between views
- Define default view per role
- Define which accounting features are auto-generated vs manual

**Files / Modules Affected:**
- `docs/product/user-views.md`

**Acceptance Criteria:**
- [ ] Normal user screens are listed with descriptions
- [ ] Accountant screens are listed with descriptions
- [ ] View switching mechanism is defined
- [ ] Default views per role are documented
- [ ] Auto-generated vs manual accounting features are documented

**Test Requirements:**
- N/A (documentation)

**Dependencies:**
- PF-006

**Estimated Effort:** 3 hours

---

#### PF-008: Define Import Strategy (Manual, CSV, Excel, SMS)

**Card ID:** PF-008  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Document the data import strategy for the Oman/Middle East context.

**Scope:**
- Define manual entry form fields and validation
- Define CSV import format, mapping, and preview flow
- Define Excel import format and sheet handling
- Define SMS import for major Omani banks (patterns, parsing)
- Define bank feed strategy (deferred)
- Define duplicate detection algorithm
- Define error handling and retry mechanism

**Files / Modules Affected:**
- `docs/product/import-strategy.md`
- `docs/adr/006-import-strategy.md`

**Acceptance Criteria:**
- [ ] Manual entry spec is documented
- [ ] CSV import spec is documented
- [ ] Excel import spec is documented
- [ ] SMS import spec is documented with bank patterns
- [ ] Bank feed deferral is documented
- [ ] Duplicate detection is documented
- [ ] Error handling is documented

**Test Requirements:**
- N/A (documentation)

**Dependencies:**
- PF-006

**Estimated Effort:** 6 hours

---

#### PF-009: Define MVP User Journey

**Card ID:** PF-009  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Document the ideal user journey from signup to first AI insight.

**Scope:**
- Define signup flow (email, password, tenant creation)
- Define onboarding flow (add first account, add first transaction, set first budget)
- Define path to first AI insight (how much data needed)
- Define "aha moment" — when does the user see value?
- Define retention hooks (daily brief, weekly review)

**Files / Modules Affected:**
- `docs/product/mvp-journey.md`
- `docs/product/onboarding-flow.md`

**Acceptance Criteria:**
- [ ] Signup flow is documented step-by-step
- [ ] Onboarding flow is documented
- [ ] Path to first AI insight is defined
- [ ] "Aha moment" is identified
- [ ] Retention hooks are documented

**Test Requirements:**
- N/A (documentation)

**Dependencies:**
- PF-006, PF-008

**Estimated Effort:** 4 hours

---

#### PF-010: Define Family Finance Model

**Card ID:** PF-010  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** High  
**Status:** Ready

**Goal:**  
Document the family finance data model, roles, and permissions.

**Scope:**
- Define family entity and relationships
- Define family roles (head, parent, adult, teen, child, viewer)
- Define permission matrix per role
- Define shared vs private account model
- Define family goal and budget model
- Define allowance and chore tracking (optional for v1)

**Files / Modules Affected:**
- `docs/architecture/family-finance.md`
- `docs/adr/007-family-finance.md`

**Acceptance Criteria:**
- [ ] Family entity model is documented
- [ ] All roles are defined with descriptions
- [ ] Permission matrix is documented
- [ ] Shared vs private account model is defined
- [ ] Family goal and budget model is defined
- [ ] Allowance model is defined (if in v1)

**Test Requirements:**
- N/A (documentation)

**Dependencies:**
- PF-002

**Estimated Effort:** 4 hours

---

#### PF-011: Write PLAN_V2.md

**Card ID:** PF-011  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Write this comprehensive plan document.

**Scope:**
- Compile all Phase 0 decisions into a single document
- Include all 20 sections as specified
- Include detailed Kanban cards for first 30 cards
- Include migration from old plan to new plan
- Include risks and mitigations

**Files / Modules Affected:**
- `PLAN_V2.md`

**Acceptance Criteria:**
- [ ] All 20 sections are complete
- [ ] First 30 cards have detailed specifications
- [ ] Migration mapping is complete
- [ ] Risks and mitigations are documented
- [ ] Document is reviewed and approved

**Test Requirements:**
- N/A (documentation)

**Dependencies:**
- All PF-000 through PF-010

**Estimated Effort:** 8 hours

---

#### PF-012: Setup Development Environment

**Card ID:** PF-012  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Setup the local development environment with Python, PostgreSQL, and Redis.

**Scope:**
- Install Python 3.11+
- Create virtual environment
- Install PostgreSQL 15+
- Install Redis
- Verify all tools are working
- Document setup steps

**Files / Modules Affected:**
- `docs/dev/setup.md`
- `venv/` (created)

**Acceptance Criteria:**
- [ ] Python 3.11+ is installed and verified
- [ ] Virtual environment is created and activated
- [ ] PostgreSQL 15+ is installed and running
- [ ] Redis is installed and running
- [ ] All tools are verified working
- [ ] Setup steps are documented

**Test Requirements:**
- N/A (environment setup)

**Dependencies:**
- PF-011

**Estimated Effort:** 2 hours

---

#### PF-013: Create Project Skeleton and Folder Structure

**Card ID:** PF-013  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Create the complete project folder structure as defined in Section 8.

**Scope:**
- Create all directories in `app/`
- Create `__init__.py` files in all packages
- Create placeholder files (models.py, schemas.py, services.py, routes.py) in each module
- Create `requirements.txt` with initial dependencies
- Create `run.py` entry point
- Create `.env.example`
- Create `.gitignore`

**Files / Modules Affected:**
- All directories under `app/`
- `requirements.txt`
- `run.py`
- `.env.example`
- `.gitignore`
- `README.md`

**Acceptance Criteria:**
- [ ] All directories from Section 8 are created
- [ ] All `__init__.py` files are present
- [ ] Placeholder files exist in each module
- [ ] `requirements.txt` has FastAPI, SQLAlchemy, Alembic, PostgreSQL driver, Redis, Celery
- [ ] `run.py` exists and is runnable (even if just starts FastAPI)
- [ ] `.env.example` documents all required env vars
- [ ] `.gitignore` ignores venv, __pycache__, .env

**Test Requirements:**
- [ ] `python run.py` starts without import errors

**Dependencies:**
- PF-012

**Estimated Effort:** 2 hours

---

#### PF-014: Setup PostgreSQL and Redis

**Card ID:** PF-014  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Setup PostgreSQL database and Redis cache with initial configuration.

**Scope:**
- Create PostgreSQL database: `pf_dev`
- Create PostgreSQL user: `pf_user`
- Configure PostgreSQL for RLS (enable required extensions)
- Configure Redis
- Test connectivity from Python
- Document connection strings

**Files / Modules Affected:**
- `app/core/db.py` (initial version)
- `scripts/setup_db.py`

**Acceptance Criteria:**
- [ ] PostgreSQL database `pf_dev` exists
- [ ] PostgreSQL user `pf_user` exists with correct permissions
- [ ] RLS can be enabled (extensions available)
- [ ] Redis is running and accessible
- [ ] Python can connect to both
- [ ] Connection strings are documented

**Test Requirements:**
- [ ] Connection test script passes

**Dependencies:**
- PF-013

**Estimated Effort:** 2 hours

---

#### PF-015: Setup Git Repository and Branching Strategy

**Card ID:** PF-015  
**Epic:** Phase 0 — Product & Architecture Reframe  
**Priority:** Critical  
**Status:** Ready

**Goal:**  
Initialize Git repository and define branching strategy.

**Scope:**
- Initialize Git repository
- Create `main` branch
- Define branching strategy (GitFlow vs trunk-based)
- Create branch naming conventions
- Setup commit message conventions
- Create initial commit with project skeleton
- Document branching strategy

**Files / Modules Affected:**
- `.git/`
- `docs/dev/git-strategy.md`

**Acceptance Criteria:**
- [ ] Git repository is initialized
- [ ] `main` branch exists
- [ ] Branching strategy is documented
- [ ] Branch naming conventions are documented
- [ ] Commit message conventions are documented
- [ ] Initial commit is made with project skeleton
- [ ] `.gitignore` is committed

**Test Requirements:**
- N/A (Git setup)

**Dependencies:**
- PF-013

**Estimated Effort:** 1 hour

---

### Phase 1: SaaS Foundation

---

#### PF-100: Project Architecture & Configuration System

**Card ID:** PF-100  
**Epic:** PF-100 — Platform Foundation  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Build the configuration system that manages environment variables, settings, and application configuration.

**Scope:**
- Implement Pydantic Settings for configuration
- Support dev/test/prod environments
- Load from `.env` file
- Validate required settings on startup
- Implement settings for: database, Redis, email, AI, security
- Create `app/config.py` with `Settings` class

**Files / Modules Affected:**
- `app/config.py`
- `app/main.py` (uses settings)
- `.env.example` (update)

**Acceptance Criteria:**
- [ ] `Settings` class loads from environment variables
- [ ] Required settings are validated on startup (fail fast)
- [ ] Different environments (dev/test/prod) are supported
- [ ] `.env.example` documents all settings
- [ ] Sensitive settings (passwords, keys) are marked as secrets
- [ ] Settings are accessible via dependency injection

**Test Requirements:**
- [ ] Unit tests for settings validation
- [ ] Test that missing required settings raise error on startup

**Dependencies:**
- PF-013, PF-014

**Estimated Effort:** 4 hours

---

#### PF-101: Database Layer: SQLAlchemy, Alembic, Base Models

**Card ID:** PF-101  
**Epic:** PF-100 — Platform Foundation  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Setup the database layer with SQLAlchemy 2.x, connection pooling, session management, and Alembic migrations.

**Scope:**
- Configure SQLAlchemy engine with connection pooling
- Implement async session management (or sync for v1)
- Create base model with `id`, `tenant_id`, `created_at`, `updated_at`, `created_by`, `updated_by`
- Setup Alembic with async support
- Create initial migration
- Implement database dependency for FastAPI

**Files / Modules Affected:**
- `app/core/db.py`
- `app/core/enums.py`
- `alembic/env.py`
- `alembic.ini`

**Acceptance Criteria:**
- [ ] SQLAlchemy engine is configured with pooling
- [ ] Base model has all audit fields
- [ ] Alembic is configured and can run migrations
- [ ] Initial migration creates no tables (or basic tables if needed)
- [ ] Database dependency works with FastAPI `Depends()`
- [ ] Connection is properly closed after requests

**Test Requirements:**
- [ ] Test database connection
- [ ] Test session lifecycle
- [ ] Test base model creation

**Dependencies:**
- PF-100

**Estimated Effort:** 6 hours

---

#### PF-102: Logging, Exception Handling, and Middleware

**Card ID:** PF-102  
**Epic:** PF-100 — Platform Foundation  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement structured logging, global exception handling, and essential middleware.

**Scope:**
- Configure structured logging (JSON format for production)
- Implement global exception handlers for FastAPI
- Create custom exception hierarchy
- Implement request logging middleware
- Implement timing middleware (request duration)
- Implement correlation ID middleware

**Files / Modules Affected:**
- `app/core/logging.py`
- `app/core/exceptions.py`
- `app/core/middleware.py`
- `app/main.py`

**Acceptance Criteria:**
- [ ] Logs are structured (JSON in production, readable in dev)
- [ ] All unhandled exceptions return consistent error responses
- [ ] Custom exceptions have appropriate HTTP status codes
- [ ] Request logging includes method, path, duration, status
- [ ] Correlation ID is generated and propagated
- [ ] Error responses include correlation ID for debugging

**Test Requirements:**
- [ ] Test exception handlers return correct status codes
- [ ] Test logging output format
- [ ] Test correlation ID propagation

**Dependencies:**
- PF-100

**Estimated Effort:** 4 hours

---

#### PF-103: PostgreSQL RLS Implementation

**Card ID:** PF-103  
**Epic:** PF-100 — Platform Foundation  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement PostgreSQL Row-Level Security policies and tenant context management.

**Scope:**
- Create RLS helper functions in `app/core/rls.py`
- Implement tenant context setting on database connections
- Create RLS policy templates
- Implement middleware that sets tenant context from JWT
- Test RLS policies prevent cross-tenant access
- Document RLS usage for developers

**Files / Modules Affected:**
- `app/core/rls.py`
- `app/core/middleware.py`
- `app/core/db.py`
- `app/tenants/models.py` (for testing)

**Acceptance Criteria:**
- [ ] RLS helper functions are implemented
- [ ] Tenant context is set on every database connection
- [ ] RLS policies are created for all tenant tables
- [ ] Cross-tenant access is blocked at database level
- [ ] Super admin can bypass RLS
- [ ] RLS does not break existing queries
- [ ] Performance impact is acceptable (<5ms per query)

**Test Requirements:**
- [ ] Test that user A cannot see user B's data
- [ ] Test that RLS policies are applied correctly
- [ ] Test super admin bypass
- [ ] Performance test: query with RLS vs without

**Dependencies:**
- PF-101

**Estimated Effort:** 8 hours

---

#### SAAS-200: Tenant Model and CRUD

**Card ID:** SAAS-200  
**Epic:** SAAS-200 — Multi-Tenant SaaS  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement the Tenant model with full CRUD operations.

**Scope:**
- Create `Tenant` model (id, name, slug, plan_id, status, settings)
- Create `Plan` model (id, name, description, price, limits)
- Create tenant CRUD service
- Create tenant admin routes (create, read, update, delete)
- Implement tenant slug uniqueness validation
- Implement tenant soft delete

**Files / Modules Affected:**
- `app/tenants/models.py`
- `app/tenants/schemas.py`
- `app/tenants/services.py`
- `app/tenants/routes.py`

**Acceptance Criteria:**
- [ ] Tenant can be created with name and slug
- [ ] Tenant slug is unique
- [ ] Tenant can be updated
- [ ] Tenant can be soft deleted
- [ ] Tenant list supports pagination
- [ ] Tenant settings are stored as JSONB
- [ ] Plan model has name, price, and limits

**Test Requirements:**
- [ ] Unit tests for tenant CRUD
- [ ] Integration tests for tenant routes
- [ ] Test slug uniqueness validation
- [ ] Test soft delete

**Dependencies:**
- PF-101, PF-103

**Estimated Effort:** 6 hours

---

#### SAAS-201: Tenant Isolation Middleware

**Card ID:** SAAS-201  
**Epic:** SAAS-200 — Multi-Tenant SaaS  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement middleware that automatically isolates data by tenant.

**Scope:**
- Extract tenant_id from JWT token in requests
- Set tenant context on database session
- Reject requests without valid tenant context
- Handle tenant suspension (return 403)
- Log tenant context for debugging
- Ensure tenant_id is applied to all queries automatically

**Files / Modules Affected:**
- `app/core/middleware.py`
- `app/core/dependencies.py`
- `app/tenants/permissions.py`

**Acceptance Criteria:**
- [ ] Tenant is extracted from JWT on every request
- [ ] Database session has tenant context set
- [ ] Requests without tenant return 401/403
- [ ] Suspended tenants receive 403
- [ ] Tenant context is logged
- [ ] All queries are filtered by tenant_id (application level + RLS)

**Test Requirements:**
- [ ] Test tenant extraction from valid JWT
- [ ] Test rejection of requests without tenant
- [ ] Test suspended tenant handling
- [ ] Test that queries are tenant-scoped

**Dependencies:**
- SAAS-200, PF-103

**Estimated Effort:** 6 hours

---

#### SAAS-202: Subscription Plans (Free, Premium, Family)

**Card ID:** SAAS-202  
**Epic:** SAAS-200 — Multi-Tenant SaaS  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement subscription plans with feature limits.

**Scope:**
- Create Plan model with features and limits
- Create seed data for Free, Premium, Family plans
- Implement plan feature checking (can_use_feature)
- Implement plan limit checking (check_limit)
- Create plan management routes (admin only)
- Document plan features and limits

**Files / Modules Affected:**
- `app/tenants/models.py` (Plan)
- `app/tenants/services.py`
- `app/tenants/routes.py`
- `scripts/seed_data.py`

**Acceptance Criteria:**
- [ ] Free, Premium, Family plans are defined
- [ ] Each plan has feature flags and limits
- [ ] Feature checking works correctly
- [ ] Limit checking works correctly
- [ ] Plan can be changed (upgrade/downgrade)
- [ ] Plan changes are logged

**Test Requirements:**
- [ ] Test plan feature checking
- [ ] Test plan limit enforcement
- [ ] Test plan upgrade/downgrade

**Dependencies:**
- SAAS-200

**Estimated Effort:** 6 hours

---

#### SAAS-203: Usage Limits and Quotas

**Card ID:** SAAS-203  
**Epic:** SAAS-200 — Multi-Tenant SaaS  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement usage tracking and quota enforcement.

**Scope:**
- Create usage tracking model (transactions, AI requests, storage, users)
- Implement usage counting on relevant operations
- Implement quota enforcement (reject if exceeded)
- Implement usage reporting (current usage, remaining quota)
- Create usage dashboard for tenants
- Implement soft limits (warning) and hard limits (rejection)

**Files / Modules Affected:**
- `app/tenants/models.py` (UsageLog)
- `app/tenants/services.py`
- `app/tenants/routes.py`

**Acceptance Criteria:**
- [ ] Usage is tracked for: transactions, AI requests, storage, users
- [ ] Quotas are enforced at plan limits
- [ ] Soft limits trigger warnings
- [ ] Hard limits reject operations
- [ ] Usage dashboard shows current usage
- [ ] Usage resets monthly

**Test Requirements:**
- [ ] Test usage tracking accuracy
- [ ] Test quota enforcement
- [ ] Test soft limit warnings
- [ ] Test monthly reset

**Dependencies:**
- SAAS-202

**Estimated Effort:** 6 hours

---

#### AUTH-300: User Registration

**Card ID:** AUTH-300  
**Epic:** AUTH-300 — Authentication  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement user registration with email, password, and automatic tenant creation.

**Scope:**
- Create registration endpoint: POST /auth/register
- Validate email format and uniqueness
- Validate password strength (min 8 chars, complexity)
- Hash password with bcrypt
- Create user record
- Create tenant record (if first user)
- Create tenant membership (owner role)
- Send verification email
- Return JWT token

**Files / Modules Affected:**
- `app/identity/models.py` (User)
- `app/identity/schemas.py`
- `app/identity/services.py`
- `app/identity/routes.py`
- `app/tenants/services.py` (tenant creation)

**Acceptance Criteria:**
- [ ] User can register with email and password
- [ ] Email is validated for format and uniqueness
- [ ] Password meets strength requirements
- [ ] Password is hashed (not stored plain)
- [ ] Tenant is created automatically for first user
- [ ] User is assigned owner role in tenant
- [ ] Verification email is sent
- [ ] JWT token is returned on registration

**Test Requirements:**
- [ ] Test registration with valid data
- [ ] Test registration with duplicate email
- [ ] Test registration with weak password
- [ ] Test password hashing
- [ ] Test tenant creation on registration
- [ ] Test JWT token generation

**Dependencies:**
- SAAS-200

**Estimated Effort:** 6 hours

---

#### AUTH-301: User Login and JWT

**Card ID:** AUTH-301  
**Epic:** AUTH-300 — Authentication  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement user login with JWT token generation and validation.

**Scope:**
- Create login endpoint: POST /auth/login
- Verify email and password
- Generate JWT access token (15 min expiry)
- Generate JWT refresh token (7 day expiry)
- Implement token refresh endpoint
- Implement token validation dependency
- Include tenant_id and roles in token payload
- Implement logout (token blacklist in Redis)

**Files / Modules Affected:**
- `app/identity/services.py`
- `app/identity/routes.py`
- `app/core/security.py`
- `app/core/dependencies.py`

**Acceptance Criteria:**
- [ ] User can login with email and password
- [ ] Invalid credentials return 401
- [ ] Access token expires in 15 minutes
- [ ] Refresh token expires in 7 days
- [ ] Token refresh works with valid refresh token
- [ ] Token includes tenant_id and user roles
- [ ] Logout invalidates token
- [ ] Protected routes reject invalid tokens

**Test Requirements:**
- [ ] Test login with valid credentials
- [ ] Test login with invalid credentials
- [ ] Test token expiry
- [ ] Test token refresh
- [ ] Test logout invalidates token
- [ ] Test protected route access with/without token

**Dependencies:**
- AUTH-300

**Estimated Effort:** 6 hours

---

#### AUTH-302: Forgot Password

**Card ID:** AUTH-302  
**Epic:** AUTH-300 — Authentication  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement password reset flow via email.

**Scope:**
- Create forgot password endpoint: POST /auth/forgot-password
- Generate secure reset token
- Send reset email with token link
- Create reset password endpoint: POST /auth/reset-password
- Validate reset token
- Update password
- Invalidate reset token after use
- Expire reset tokens after 1 hour

**Files / Modules Affected:**
- `app/identity/models.py` (PasswordReset)
- `app/identity/services.py`
- `app/identity/routes.py`
- `app/templates/emails/reset_password.html`

**Acceptance Criteria:**
- [ ] User can request password reset with email
- [ ] Reset token is generated securely
- [ ] Reset email is sent
- [ ] Password can be reset with valid token
- [ ] Invalid token is rejected
- [ ] Expired token is rejected
- [ ] Token is invalidated after use
- [ ] New password is hashed

**Test Requirements:**
- [ ] Test forgot password flow end-to-end
- [ ] Test invalid token rejection
- [ ] Test expired token rejection
- [ ] Test token single-use

**Dependencies:**
- AUTH-301

**Estimated Effort:** 4 hours

---

#### AUTH-303: Email Verification

**Card ID:** AUTH-303  
**Epic:** AUTH-300 — Authentication  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement email verification flow.

**Scope:**
- Generate verification token on registration
- Send verification email
- Create verify endpoint: GET /auth/verify-email/{token}
- Mark user as verified
- Resend verification email endpoint
- Restrict certain features for unverified users

**Files / Modules Affected:**
- `app/identity/models.py`
- `app/identity/services.py`
- `app/identity/routes.py`
- `app/templates/emails/verify_email.html`

**Acceptance Criteria:**
- [ ] Verification token is generated on registration
- [ ] Verification email is sent
- [ ] Email is verified with valid token
- [ ] Invalid token is rejected
- [ ] Verification can be resent
- [ ] Unverified users have restricted access

**Test Requirements:**
- [ ] Test verification flow
- [ ] Test invalid token
- [ ] Test resend verification
- [ ] Test restricted access for unverified users

**Dependencies:**
- AUTH-300

**Estimated Effort:** 4 hours

---

#### AUTH-304: Role-Based Access Control (RBAC)

**Card ID:** AUTH-304  
**Epic:** AUTH-300 — Authentication  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement role-based access control for tenant members.

**Scope:**
- Define roles: owner, admin, member, accountant, viewer
- Define permissions per role (read, write, delete, manage)
- Implement permission checking decorators
- Implement route-level permission guards
- Implement resource-level permission checks (can edit this transaction?)
- Create role assignment and update endpoints

**Files / Modules Affected:**
- `app/tenants/models.py` (TenantMember roles)
- `app/tenants/permissions.py`
- `app/core/dependencies.py`
- `app/identity/permissions.py`

**Acceptance Criteria:**
- [ ] Roles are defined and documented
- [ ] Permissions are mapped to roles
- [ ] Route guards enforce role requirements
- [ ] Resource-level checks work (user can only edit own transactions)
- [ ] Role can be assigned and updated
- [ ] Owner cannot be removed without transferring ownership

**Test Requirements:**
- [ ] Test each role's permissions
- [ ] Test route guards
- [ ] Test resource-level checks
- [ ] Test role assignment
- [ ] Test ownership transfer

**Dependencies:**
- AUTH-301, SAAS-201

**Estimated Effort:** 6 hours

---

#### AUTH-305: Tenant Member Invitation

**Card ID:** AUTH-305  
**Epic:** AUTH-300 — Authentication  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement invitation system for adding members to a tenant.

**Scope:**
- Create invitation endpoint: POST /tenants/members/invite
- Generate invitation token
- Send invitation email
- Create accept invitation endpoint
- Handle new user registration from invitation
- Handle existing user joining from invitation
- Set role from invitation
- Expire invitations after 7 days

**Files / Modules Affected:**
- `app/tenants/models.py` (Invitation)
- `app/tenants/services.py`
- `app/tenants/routes.py`
- `app/templates/emails/invitation.html`

**Acceptance Criteria:**
- [ ] Tenant admin can invite by email
- [ ] Invitation token is generated securely
- [ ] Invitation email is sent
- [ ] New user can register and join via invitation
- [ ] Existing user can join via invitation
- [ ] Role is set from invitation
- [ ] Expired invitations are rejected
- [ ] Used invitations are rejected

**Test Requirements:**
- [ ] Test invitation flow for new user
- [ ] Test invitation flow for existing user
- [ ] Test expired invitation
- [ ] Test used invitation
- [ ] Test role assignment

**Dependencies:**
- AUTH-304

**Estimated Effort:** 6 hours

---

#### USR-400: User Profile and Settings

**Card ID:** USR-400  
**Epic:** USR-400 — User Profile  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement user profile management.

**Scope:**
- Create user profile model (name, phone, avatar, address)
- Create profile CRUD endpoints
- Implement profile update validation
- Implement avatar upload
- Create profile page UI

**Files / Modules Affected:**
- `app/identity/models.py` (UserProfile)
- `app/identity/schemas.py`
- `app/identity/services.py`
- `app/identity/routes.py`

**Acceptance Criteria:**
- [ ] User can view profile
- [ ] User can update profile
- [ ] Profile validation works
- [ ] Avatar can be uploaded
- [ ] Profile is linked to user

**Test Requirements:**
- [ ] Test profile CRUD
- [ ] Test profile validation
- [ ] Test avatar upload

**Dependencies:**
- AUTH-301

**Estimated Effort:** 4 hours

---

#### USR-401: Currency and Language Preferences

**Card ID:** USR-401  
**Epic:** USR-400 — User Profile  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement currency and language preference settings.

**Scope:**
- Add currency preference to user profile (default OMR)
- Add language preference (default English, Arabic planned)
- Implement currency formatting throughout app
- Implement number formatting (OMR uses 3 decimal places)
- Create settings endpoints
- Create settings UI

**Files / Modules Affected:**
- `app/identity/models.py`
- `app/identity/schemas.py`
- `app/identity/services.py`
- `app/core/enums.py` (Currency)

**Acceptance Criteria:**
- [ ] Currency preference can be set
- [ ] Language preference can be set
- [ ] Currency formatting uses correct symbol and decimals
- [ ] OMR displays with 3 decimal places
- [ ] Settings persist across sessions
- [ ] Settings are applied to all monetary displays

**Test Requirements:**
- [ ] Test currency formatting for different currencies
- [ ] Test OMR 3-decimal formatting
- [ ] Test settings persistence

**Dependencies:**
- USR-400

**Estimated Effort:** 4 hours

---

#### USR-402: Theme and Notification Settings

**Card ID:** USR-402  
**Epic:** USR-400 — User Profile  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement theme and notification preference settings.

**Scope:**
- Add theme preference (light/dark/system)
- Add notification preferences (email, push, SMS)
- Add notification frequency (immediate, daily digest, weekly)
- Create settings endpoints
- Apply theme to UI
- Respect notification preferences when sending alerts

**Files / Modules Affected:**
- `app/identity/models.py`
- `app/identity/schemas.py`
- `app/identity/services.py`
- `app/notifications/models.py`

**Acceptance Criteria:**
- [ ] Theme can be set and applied
- [ ] Notification channels can be configured
- [ ] Notification frequency can be set
- [ ] Preferences are respected when sending notifications
- [ ] Default preferences are sensible

**Test Requirements:**
- [ ] Test theme application
- [ ] Test notification preference filtering
- [ ] Test default preferences

**Dependencies:**
- USR-400

**Estimated Effort:** 4 hours

---

#### ACC-500: Chart of Accounts (Hidden Foundation)

**Card ID:** ACC-500  
**Epic:** ACC-500 — Accounting Engine  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement the Chart of Accounts as the hidden foundation of the accounting engine.

**Scope:**
- Create Account model with hierarchy (parent-child)
- Support account types: asset, liability, income, expense, equity
- Create default COA for new tenants (standard personal finance accounts)
- Implement account CRUD (admin/accountant only)
- Implement account balance calculation
- Create account tree view (accountant view)

**Files / Modules Affected:**
- `app/accounting/models.py` (Account)
- `app/accounting/schemas.py`
- `app/accounting/services.py`
- `app/accounting/routes.py`
- `scripts/seed_data.py` (default COA)

**Acceptance Criteria:**
- [ ] Account model supports hierarchy
- [ ] Account types are enforced
- [ ] Default COA is created for new tenants
- [ ] Account balance is calculated correctly
- [ ] Account CRUD is restricted to admin/accountant
- [ ] Account tree view shows hierarchy

**Test Requirements:**
- [ ] Test account creation
- [ ] Test account hierarchy
- [ ] Test balance calculation
- [ ] Test default COA seeding
- [ ] Test permission restrictions

**Dependencies:**
- SAAS-200

**Estimated Effort:** 8 hours

---

#### ACC-501: Account Types and Hierarchy

**Card ID:** ACC-501  
**Epic:** ACC-500 — Accounting Engine  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement account type system and hierarchical account structure.

**Scope:**
- Define account type enum (asset, liability, income, expense, equity)
- Implement parent-child relationships
- Implement account code system (e.g., 1000 Assets, 2000 Liabilities)
- Validate account type consistency (children match parent type)
- Implement account level calculation (sum of children)
- Create account type reporting helpers

**Files / Modules Affected:**
- `app/accounting/models.py`
- `app/accounting/schemas.py`
- `app/accounting/services.py`
- `app/core/enums.py`

**Acceptance Criteria:**
- [ ] Account types are defined and enforced
- [ ] Parent-child relationships work
- [ ] Account codes are validated
- [ ] Children match parent type
- [ ] Parent balance sums children
- [ ] Account type helpers work for reporting

**Test Requirements:**
- [ ] Test account type validation
- [ ] Test parent-child relationships
- [ ] Test balance rollup
- [ ] Test type consistency validation

**Dependencies:**
- ACC-500

**Estimated Effort:** 6 hours

---

#### ACC-502: Opening Balances

**Card ID:** ACC-502  
**Epic:** ACC-500 — Accounting Engine  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement opening balance setup for accounts.

**Scope:**
- Add opening_balance field to Account
- Create opening balance entry form
- Generate opening balance journal entry automatically
- Validate that total assets = total liabilities + equity (accounting equation)
- Allow opening balance adjustment
- Show opening balance in account history

**Files / Modules Affected:**
- `app/accounting/models.py`
- `app/accounting/services.py`
- `app/accounting/routes.py`

**Acceptance Criteria:**
- [ ] Opening balance can be set per account
- [ ] Opening balance generates journal entry
- [ ] Accounting equation is validated
- [ ] Opening balance can be adjusted
- [ ] Opening balance appears in account history
- [ ] Invalid opening balances are rejected

**Test Requirements:**
- [ ] Test opening balance creation
- [ ] Test journal entry generation
- [ ] Test accounting equation validation
- [ ] Test adjustment flow

**Dependencies:**
- ACC-501

**Estimated Effort:** 4 hours

---

### Phase 2: Financial Life MVP

---

#### TRX-600: Simple Transaction Entry

**Card ID:** TRX-600  
**Epic:** TRX-600 — Transactions  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement simple transaction entry for normal users (no accounting jargon).

**Scope:**
- Create transaction form: date, description, amount, category, account
- Support income, expense, and transfer types
- Auto-suggest category based on description
- Create transaction with single API call
- Auto-generate journal entry behind the scenes
- Show confirmation with account balance update

**Files / Modules Affected:**
- `app/transactions/models.py` (Transaction, Category)
- `app/transactions/schemas.py`
- `app/transactions/services.py`
- `app/transactions/routes.py`
- `app/accounting/services.py` (journal entry generation)

**Acceptance Criteria:**
- [ ] User can add income transaction
- [ ] User can add expense transaction
- [ ] User can add transfer between accounts
- [ ] Category is auto-suggested from description
- [ ] Journal entry is auto-generated (hidden from user)
- [ ] Account balance updates immediately
- [ ] Form validation works correctly
- [ ] Transaction appears in transaction list

**Test Requirements:**
- [ ] Test transaction creation
- [ ] Test journal entry auto-generation
- [ ] Test balance update
- [ ] Test category auto-suggestion
- [ ] Test transfer between accounts
- [ ] Test validation errors

**Dependencies:**
- ACC-502

**Estimated Effort:** 8 hours

---

#### TRX-601: Transaction List, Search, and Filter

**Card ID:** TRX-601  
**Epic:** TRX-600 — Transactions  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement transaction listing with search, filter, and pagination.

**Scope:**
- Create transaction list endpoint with pagination
- Implement search by description
- Implement filter by: date range, category, account, type, amount range
- Implement sort by: date, amount, description
- Create transaction list UI with HTMX
- Implement infinite scroll or pagination

**Files / Modules Affected:**
- `app/transactions/services.py`
- `app/transactions/routes.py`
- `app/templates/pages/transactions/list.html`

**Acceptance Criteria:**
- [ ] Transactions are paginated
- [ ] Search by description works
- [ ] Filter by date range works
- [ ] Filter by category works
- [ ] Filter by account works
- [ ] Filter by type works
- [ ] Sort by date, amount, description works
- [ ] UI updates with HTMX without full page reload

**Test Requirements:**
- [ ] Test pagination
- [ ] Test search
- [ ] Test each filter
- [ ] Test sorting
- [ ] Test combined filters

**Dependencies:**
- TRX-600

**Estimated Effort:** 6 hours

---

#### TRX-602: Split Transactions

**Card ID:** TRX-602  
**Epic:** TRX-600 — Transactions  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement split transactions (one payment, multiple categories).

**Scope:**
- Add split transaction model (TransactionSplit)
- Allow multiple categories with amounts per transaction
- Validate that split amounts sum to total
- Generate journal entries for each split
- Show splits in transaction list and detail
- Allow editing splits

**Files / Modules Affected:**
- `app/transactions/models.py` (TransactionSplit)
- `app/transactions/schemas.py`
- `app/transactions/services.py`
- `app/transactions/routes.py`

**Acceptance Criteria:**
- [ ] User can create split transaction
- [ ] Multiple categories can be assigned
- [ ] Split amounts must sum to total
- [ ] Journal entries are generated for each split
- [ ] Splits are displayed in transaction list
- [ ] Splits can be edited
- [ ] Validation prevents unbalanced splits

**Test Requirements:**
- [ ] Test split creation
- [ ] Test amount sum validation
- [ ] Test journal entry generation for splits
- [ ] Test split editing
- [ ] Test unbalanced split rejection

**Dependencies:**
- TRX-600

**Estimated Effort:** 6 hours

---

#### TRX-603: Transfer Between Accounts

**Card ID:** TRX-603  
**Epic:** TRX-600 — Transactions  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement account transfers with proper double-entry handling.

**Scope:**
- Create transfer form (from account, to account, amount, date, description)
- Generate two transactions (debit from, credit to)
- Generate balanced journal entry
- Handle currency conversion if accounts have different currencies
- Show transfer in both account histories
- Allow transfer reversal

**Files / Modules Affected:**
- `app/transactions/services.py`
- `app/transactions/routes.py`
- `app/accounting/services.py`

**Acceptance Criteria:**
- [ ] User can create transfer between accounts
- [ ] Two transactions are created (debit and credit)
- [ ] Journal entry is balanced
- [ ] Transfer appears in both account histories
- [ ] Currency conversion is handled
- [ ] Transfer can be reversed
- [ ] Validation prevents negative transfers

**Test Requirements:**
- [ ] Test transfer creation
- [ ] Test journal entry balance
- [ ] Test both account histories
- [ ] Test currency conversion
- [ ] Test transfer reversal

**Dependencies:**
- TRX-600

**Estimated Effort:** 6 hours

---

#### TRX-604: Transaction Categories

**Card ID:** TRX-604  
**Epic:** TRX-600 — Transactions  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement transaction categories with user customization.

**Scope:**
- Create default categories (Dining, Transport, Bills, Shopping, etc.)
- Allow user to create custom categories
- Support category hierarchy (parent-child)
- Support category icons and colors
- Implement category spending totals
- Allow category archiving (soft delete)

**Files / Modules Affected:**
- `app/transactions/models.py` (Category)
- `app/transactions/schemas.py`
- `app/transactions/services.py`
- `app/transactions/routes.py`
- `scripts/seed_data.py` (default categories)

**Acceptance Criteria:**
- [ ] Default categories are created for new tenants
- [ ] User can create custom categories
- [ ] Category hierarchy is supported
- [ ] Categories have icons and colors
- [ ] Category spending totals are calculated
- [ ] Categories can be archived
- [ ] Archived categories are hidden from new transactions

**Test Requirements:**
- [ ] Test category creation
- [ ] Test category hierarchy
- [ ] Test default category seeding
- [ ] Test spending totals
- [ ] Test archiving

**Dependencies:**
- ACC-500

**Estimated Effort:** 6 hours

---

#### TRX-605: Transaction Attachments

**Card ID:** TRX-605  
**Epic:** TRX-600 — Transactions  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement receipt and document attachment for transactions.

**Scope:**
- Add attachment model (file path, file type, file size)
- Implement file upload endpoint
- Store files securely (outside web root)
- Validate file types (images, PDFs)
- Limit file size (5MB per file, 50MB per tenant)
- Show attachments in transaction detail
- Allow attachment download

**Files / Modules Affected:**
- `app/transactions/models.py` (Attachment)
- `app/transactions/services.py`
- `app/transactions/routes.py`
- Storage configuration

**Acceptance Criteria:**
- [ ] Files can be uploaded
- [ ] File types are validated
- [ ] File size is limited
- [ ] Files are stored securely
- [ ] Attachments appear in transaction detail
- [ ] Files can be downloaded
- [ ] Tenant storage quota is enforced

**Test Requirements:**
- [ ] Test file upload
- [ ] Test file type validation
- [ ] Test file size limit
- [ ] Test download
- [ ] Test quota enforcement

**Dependencies:**
- TRX-600

**Estimated Effort:** 4 hours

---

#### IMP-700: CSV Import

**Card ID:** IMP-700  
**Epic:** IMP-700 — Imports  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement CSV transaction import with mapping and preview.

**Scope:**
- Create CSV upload endpoint
- Parse CSV file (detect encoding, delimiter)
- Column mapping UI (map CSV columns to app fields)
- Preview first 10 rows before import
- Detect duplicates against existing transactions
- Import valid rows, log errors for invalid rows
- Create import job tracking
- Generate journal entries for imported transactions

**Files / Modules Affected:**
- `app/imports/models.py` (ImportJob, ImportMapping)
- `app/imports/parsers/csv_parser.py`
- `app/imports/services.py`
- `app/imports/routes.py`
- `app/imports/tasks.py` (background processing)

**Acceptance Criteria:**
- [ ] CSV files can be uploaded
- [ ] Encoding and delimiter are detected
- [ ] Columns can be mapped to app fields
- [ ] Preview shows first 10 rows
- [ ] Duplicates are detected
- [ ] Valid rows are imported
- [ ] Errors are logged and reported
- [ ] Import job status is tracked
- [ ] Journal entries are generated

**Test Requirements:**
- [ ] Test CSV parsing with various formats
- [ ] Test column mapping
- [ ] Test duplicate detection
- [ ] Test error handling
- [ ] Test import job tracking
- [ ] Test large file handling (1000+ rows)

**Dependencies:**
- TRX-600

**Estimated Effort:** 10 hours

---

#### IMP-701: Excel Import

**Card ID:** IMP-701  
**Epic:** IMP-700 — Imports  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement Excel (.xlsx) transaction import.

**Scope:**
- Create Excel upload endpoint
- Parse .xlsx files (multiple sheets)
- Sheet selection UI
- Header row detection
- Same mapping, preview, and duplicate detection as CSV
- Support multiple currencies in one file
- Import job tracking

**Files / Modules Affected:**
- `app/imports/parsers/excel_parser.py`
- `app/imports/services.py`
- `app/imports/routes.py`

**Acceptance Criteria:**
- [ ] Excel files can be uploaded
- [ ] Multiple sheets are supported
- [ ] Sheet selection works
- [ ] Header row is detected
- [ ] Column mapping works
- [ ] Preview works
- [ ] Duplicate detection works
- [ ] Multiple currencies are supported

**Test Requirements:**
- [ ] Test Excel parsing
- [ ] Test multi-sheet handling
- [ ] Test header detection
- [ ] Test currency handling

**Dependencies:**
- IMP-700

**Estimated Effort:** 6 hours

---

#### IMP-702: SMS Import Parser

**Card ID:** IMP-702  
**Epic:** IMP-700 — Imports  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement SMS bank alert parsing for major Omani banks.

**Scope:**
- Create SMS parser for common Omani bank formats
- Support: Bank Muscat, OAB, Alizz, Sohar International, NBO, HSBC Oman
- Parse: bank name, account mask, amount, date, description, balance
- Detect debit vs credit
- Suggest category based on description
- Allow user to paste SMS text or forward to app
- Learn from user corrections (improve parsing over time)
- Create SMS import UI

**Files / Modules Affected:**
- `app/imports/parsers/sms_parser.py`
- `app/imports/services.py`
- `app/imports/routes.py`
- `app/imports/models.py` (SMSPattern)

**Acceptance Criteria:**
- [ ] SMS from major Omani banks are parsed
- [ ] Bank name is detected
- [ ] Amount is extracted
- [ ] Date is extracted
- [ ] Description is extracted
- [ ] Debit/credit is detected
- [ ] Category is suggested
- [ ] User can correct parsing errors
- [ ] Parser learns from corrections

**Test Requirements:**
- [ ] Test parsing for each bank format
- [ ] Test debit/credit detection
- [ ] Test category suggestion
- [ ] Test user correction flow
- [ ] Test learning mechanism

**Dependencies:**
- TRX-600

**Estimated Effort:** 10 hours

---

#### IMP-703: Import Job Management UI

**Card ID:** IMP-703  
**Epic:** IMP-700 — Imports  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Create UI for managing import jobs (history, status, retry).

**Scope:**
- Create import job list page
- Show status: pending, processing, preview, completed, failed
- Show statistics: total, imported, duplicates, errors
- Allow retry for failed rows
- Allow download of error report
- Show import history
- Allow re-import with same mapping

**Files / Modules Affected:**
- `app/imports/routes.py`
- `app/templates/pages/imports/list.html`
- `app/templates/pages/imports/detail.html`

**Acceptance Criteria:**
- [ ] Import jobs are listed
- [ ] Status is shown clearly
- [ ] Statistics are accurate
- [ ] Failed rows can be retried
- [ ] Error report can be downloaded
- [ ] Import history is preserved
- [ ] Re-import with same mapping works

**Test Requirements:**
- [ ] Test job listing
- [ ] Test status transitions
- [ ] Test retry flow
- [ ] Test error report download

**Dependencies:**
- IMP-700

**Estimated Effort:** 4 hours

---

#### BILL-800: Bill Creation and Tracking

**Card ID:** BILL-800  
**Epic:** BILL-800 — Bills  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement bill tracking for recurring and one-time bills.

**Scope:**
- Create bill model (name, amount, due date, frequency, category, account)
- Support frequencies: once, weekly, monthly, quarterly, yearly
- Create bill instance model (each occurrence)
- Mark bills as paid/unpaid
- Link bill payment to transaction
- Show upcoming bills
- Show bill history

**Files / Modules Affected:**
- `app/bills/models.py` (Bill, BillInstance)
- `app/bills/schemas.py`
- `app/bills/services.py`
- `app/bills/routes.py`

**Acceptance Criteria:**
- [ ] Bills can be created with name, amount, due date
- [ ] Frequency is supported
- [ ] Bill instances are generated automatically
- [ ] Bills can be marked as paid
- [ ] Paid bills link to transactions
- [ ] Upcoming bills are shown
- [ ] Bill history is tracked
- [ ] Bills can be edited and deleted

**Test Requirements:**
- [ ] Test bill creation
- [ ] Test instance generation for each frequency
- [ ] Test marking as paid
- [ ] Test transaction linking
- [ ] Test upcoming bills display
- [ ] Test edit and delete

**Dependencies:**
- TRX-600

**Estimated Effort:** 8 hours

---

#### BILL-801: Bill Reminders and Alerts

**Card ID:** BILL-801  
**Epic:** BILL-800 — Bills  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement bill reminder notifications.

**Scope:**
- Generate reminders before due date (configurable: 3 days, 1 day, day of)
- Show overdue bills prominently
- Send notification based on user preferences
- Allow snooze reminders
- Allow mark as paid from reminder
- Track reminder history

**Files / Modules Affected:**
- `app/bills/services.py`
- `app/bills/tasks.py` (Celery tasks for reminders)
- `app/notifications/services.py`

**Acceptance Criteria:**
- [ ] Reminders are generated before due date
- [ ] Overdue bills are highlighted
- [ ] Notifications are sent per user preferences
- [ ] Reminders can be snoozed
- [ ] Bills can be marked paid from reminder
- [ ] Reminder history is tracked

**Test Requirements:**
- [ ] Test reminder generation timing
- [ ] Test overdue detection
- [ ] Test notification sending
- [ ] Test snooze functionality

**Dependencies:**
- BILL-800, NOTIF-1600

**Estimated Effort:** 6 hours

---

#### SUB-900: Subscription Tracking

**Card ID:** SUB-900  
**Epic:** SUB-900 — Subscriptions  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement subscription tracking for recurring services.

**Scope:**
- Create subscription model (name, amount, frequency, start date, next renewal)
- Support monthly, yearly, quarterly, weekly frequencies
- Calculate next renewal date automatically
- Show subscription list with monthly equivalent cost
- Detect potential duplicates (same name/amount)
- Categorize subscriptions
- Show subscription spending total

**Files / Modules Affected:**
- `app/subscriptions/models.py` (Subscription, SubscriptionPayment)
- `app/subscriptions/schemas.py`
- `app/subscriptions/services.py`
- `app/subscriptions/routes.py`

**Acceptance Criteria:**
- [ ] Subscriptions can be created
- [ ] Frequency is supported
- [ ] Next renewal is calculated automatically
- [ ] Monthly equivalent cost is shown
- [ ] Duplicates are detected
- [ ] Subscriptions are categorized
- [ ] Total subscription spending is calculated
- [ ] Subscriptions can be edited and cancelled

**Test Requirements:**
- [ ] Test subscription creation
- [ ] Test next renewal calculation
- [ ] Test monthly equivalent
- [ ] Test duplicate detection
- [ ] Test total calculation

**Dependencies:**
- TRX-600

**Estimated Effort:** 6 hours

---

#### SUB-901: Subscription Renewal Alerts

**Card ID:** SUB-901  
**Epic:** SUB-900 — Subscriptions  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement alerts for upcoming subscription renewals.

**Scope:**
- Alert before renewal (configurable: 7 days, 3 days, 1 day)
- Show upcoming renewals in dashboard
- Allow cancellation tracking
- Track subscription price changes
- Notify on price increase
- Allow "review subscription" action

**Files / Modules Affected:**
- `app/subscriptions/tasks.py`
- `app/subscriptions/services.py`
- `app/notifications/services.py`

**Acceptance Criteria:**
- [ ] Alerts are sent before renewal
- [ ] Upcoming renewals appear in dashboard
- [ ] Cancellation is tracked
- [ ] Price changes are detected
- [ ] Price increase notifications are sent
- [ ] Review action is available

**Test Requirements:**
- [ ] Test alert timing
- [ ] Test price change detection
- [ ] Test notification sending

**Dependencies:**
- SUB-900, NOTIF-1600

**Estimated Effort:** 4 hours

---

#### BDG-1000: Budget Creation

**Card ID:** BDG-1000  
**Epic:** BDG-1000 — Budgets  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement budget creation and management.

**Scope:**
- Create budget model (name, period, start date, end date)
- Create budget category model (category, allocated amount)
- Support monthly budgets (default)
- Support custom date ranges
- Allow rollover (unused budget carries forward)
- Create budget UI

**Files / Modules Affected:**
- `app/budgets/models.py` (Budget, BudgetCategory)
- `app/budgets/schemas.py`
- `app/budgets/services.py`
- `app/budgets/routes.py`

**Acceptance Criteria:**
- [ ] Budgets can be created with name and period
- [ ] Categories can be added with allocated amounts
- [ ] Monthly budgets are supported
- [ ] Custom date ranges are supported
- [ ] Rollover can be enabled
- [ ] Budgets can be edited and deleted
- [ ] Multiple budgets can exist

**Test Requirements:**
- [ ] Test budget creation
- [ ] Test category allocation
- [ ] Test period handling
- [ ] Test rollover
- [ ] Test edit and delete

**Dependencies:**
- TRX-604

**Estimated Effort:** 6 hours

---

#### BDG-1001: Budget Categories and Periods

**Card ID:** BDG-1001  
**Epic:** BDG-1000 — Budgets  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement budget category tracking across periods.

**Scope:**
- Track spending per budget category
- Calculate remaining budget per category
- Show spending progress bar per category
- Support budget templates (quick start)
- Copy previous period's budget
- Adjust allocations mid-period

**Files / Modules Affected:**
- `app/budgets/services.py`
- `app/budgets/routes.py`
- `app/templates/pages/budgets/detail.html`

**Acceptance Criteria:**
- [ ] Spending is tracked per category
- [ ] Remaining budget is calculated
- [ ] Progress bars are shown
- [ ] Budget templates are available
- [ ] Previous budgets can be copied
- [ ] Allocations can be adjusted mid-period

**Test Requirements:**
- [ ] Test spending tracking
- [ ] Test remaining calculation
- [ ] Test template copying
- [ ] Test mid-period adjustment

**Dependencies:**
- BDG-1000

**Estimated Effort:** 6 hours

---

#### BDG-1002: Budget vs Actual

**Card ID:** BDG-1002  
**Epic:** BDG-1000 — Budgets  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement budget vs actual spending comparison.

**Scope:**
- Compare allocated vs spent per category
- Show variance (over/under budget)
- Show percentage spent per category
- Generate budget vs actual report
- Show trends (are you spending more or less than usual?)
- Drill down into category transactions

**Files / Modules Affected:**
- `app/budgets/services.py`
- `app/budgets/routes.py`
- `app/reports/generators/expense_analysis.py`

**Acceptance Criteria:**
- [ ] Allocated vs spent is shown per category
- [ ] Variance is calculated
- [ ] Percentage spent is shown
- [ ] Report can be generated
- [ ] Trends are shown
- [ ] Transactions can be drilled down

**Test Requirements:**
- [ ] Test budget vs actual calculation
- [ ] Test variance calculation
- [ ] Test percentage calculation
- [ ] Test report generation

**Dependencies:**
- BDG-1001

**Estimated Effort:** 6 hours

---

#### BDG-1003: Overspending Alerts

**Card ID:** BDG-1003  
**Epic:** BDG-1000 — Budgets  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement alerts when budget categories are overspent or near limit.

**Scope:**
- Alert at 80% of budget (warning)
- Alert at 100% of budget (overspent)
- Alert at 50% with half period remaining (on track warning)
- Send notification per user preferences
- Show alerts in dashboard
- Allow alert threshold customization

**Files / Modules Affected:**
- `app/budgets/tasks.py`
- `app/budgets/services.py`
- `app/notifications/services.py`

**Acceptance Criteria:**
- [ ] 80% warning is generated
- [ ] 100% overspent alert is generated
- [ ] 50% mid-period warning is generated
- [ ] Notifications are sent
- [ ] Alerts appear in dashboard
- [ ] Thresholds can be customized

**Test Requirements:**
- [ ] Test threshold alerts
- [ ] Test notification sending
- [ ] Test dashboard display
- [ ] Test threshold customization

**Dependencies:**
- BDG-1002, NOTIF-1600

**Estimated Effort:** 4 hours

---

#### DB-1100: Dashboard Skeleton

**Card ID:** DB-1100  
**Epic:** DB-1100 — Dashboard  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Create the dashboard layout and navigation skeleton.

**Scope:**
- Create base template with Bootstrap 5
- Implement responsive navigation
- Create dashboard layout with widget grid
- Implement HTMX for partial updates
- Create sidebar navigation
- Implement mobile menu
- Create user menu (profile, settings, logout)

**Files / Modules Affected:**
- `app/templates/base.html`
- `app/templates/partials/navbar.html`
- `app/templates/partials/sidebar.html`
- `app/static/css/custom.css`
- `app/static/js/htmx.min.js`

**Acceptance Criteria:**
- [ ] Base template is responsive
- [ ] Navigation works on desktop and mobile
- [ ] Dashboard layout has widget grid
- [ ] HTMX is included and working
- [ ] Sidebar navigation is implemented
- [ ] Mobile menu works
- [ ] User menu has profile, settings, logout

**Test Requirements:**
- [ ] Test responsive layout
- [ ] Test navigation links
- [ ] Test HTMX partial updates
- [ ] Test mobile menu

**Dependencies:**
- AUTH-301

**Estimated Effort:** 8 hours

---

#### DB-1101: Today Screen (Daily Brief)

**Card ID:** DB-1101  
**Epic:** DB-1100 — Dashboard  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement the "Today" screen — the default landing page showing daily financial snapshot.

**Scope:**
- Show current date and greeting
- Show today's transactions (if any)
- Show upcoming bills (next 7 days)
- Show budget status (categories near limit)
- Show account balances summary
- Show net worth snapshot
- Show any AI alerts or insights
- Create quick-action buttons (add transaction, pay bill)

**Files / Modules Affected:**
- `app/templates/pages/dashboard/today.html`
- `app/routers/dashboard.py` (or service aggregation)
- `app/bills/services.py`
- `app/budgets/services.py`
- `app/accounting/services.py`

**Acceptance Criteria:**
- [ ] Today's date and greeting are shown
- [ ] Today's transactions are listed
- [ ] Upcoming bills are shown
- [ ] Budget status is summarized
- [ ] Account balances are shown
- [ ] Net worth is shown
- [ ] AI alerts appear if any
- [ ] Quick actions are available

**Test Requirements:**
- [ ] Test today screen with data
- [ ] Test today screen without data
- [ ] Test upcoming bills display
- [ ] Test budget status summary

**Dependencies:**
- DB-1100, TRX-600, BILL-800, BDG-1000

**Estimated Effort:** 8 hours

---

#### DB-1102: Cash Flow Widget

**Card ID:** DB-1102  
**Epic:** DB-1100 — Dashboard  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement cash flow widget showing income vs expenses over time.

**Scope:**
- Calculate monthly cash flow (income - expenses)
- Show cash flow chart (line or bar chart)
- Show current month vs previous month
- Show average monthly cash flow
- Show cash flow trend (improving/declining)
- Allow time range selection (3, 6, 12 months)

**Files / Modules Affected:**
- `app/templates/partials/widgets/cashflow.html`
- `app/reports/generators/cash_flow.py`
- `app/routers/dashboard.py`

**Acceptance Criteria:**
- [ ] Monthly cash flow is calculated
- [ ] Chart is displayed
- [ ] Current vs previous month is shown
- [ ] Average is calculated
- [ ] Trend is shown
- [ ] Time range can be selected

**Test Requirements:**
- [ ] Test cash flow calculation
- [ ] Test chart rendering
- [ ] Test time range selection
- [ ] Test trend calculation

**Dependencies:**
- DB-1100, TRX-600

**Estimated Effort:** 6 hours

---

#### DB-1103: Net Worth Widget

**Card ID:** DB-1103  
**Epic:** DB-1100 — Dashboard  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement net worth widget showing assets minus liabilities over time.

**Scope:**
- Calculate current net worth (assets - liabilities)
- Show net worth history chart
- Show net worth change (this month, last month, YTD)
- Break down by asset type and liability type
- Show net worth goal progress (if set)
- Allow time range selection

**Files / Modules Affected:**
- `app/templates/partials/widgets/networth.html`
- `app/reports/generators/net_worth.py`
- `app/routers/dashboard.py`

**Acceptance Criteria:**
- [ ] Current net worth is calculated
- [ ] History chart is displayed
- [ ] Net worth change is shown
- [ ] Breakdown by type is shown
- [ ] Goal progress is shown (if applicable)
- [ ] Time range can be selected

**Test Requirements:**
- [ ] Test net worth calculation
- [ ] Test chart rendering
- [ ] Test change calculation
- [ ] Test breakdown

**Dependencies:**
- DB-1100, ACC-502

**Estimated Effort:** 6 hours

---

#### DB-1104: Bills and Subscriptions Widget

**Card ID:** DB-1104  
**Epic:** DB-1100 — Dashboard  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement widget showing upcoming bills and subscriptions.

**Scope:**
- Show upcoming bills (next 7 days)
- Show overdue bills
- Show upcoming subscription renewals (next 30 days)
- Show total monthly subscription cost
- Allow quick actions (mark paid, view details)
- Color-code by urgency (green/yellow/red)

**Files / Modules Affected:**
- `app/templates/partials/widgets/bills_subscriptions.html`
- `app/bills/services.py`
- `app/subscriptions/services.py`
- `app/routers/dashboard.py`

**Acceptance Criteria:**
- [ ] Upcoming bills are shown
- [ ] Overdue bills are highlighted
- [ ] Upcoming renewals are shown
- [ ] Monthly subscription total is shown
- [ ] Quick actions work
- [ ] Color coding is applied

**Test Requirements:**
- [ ] Test upcoming bills display
- [ ] Test overdue highlighting
- [ ] Test renewal display
- [ ] Test total calculation
- [ ] Test quick actions

**Dependencies:**
- DB-1100, BILL-800, SUB-900

**Estimated Effort:** 4 hours

---

#### DB-1105: Goals Widget

**Card ID:** DB-1105  
**Epic:** DB-1100 — Dashboard  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement widget showing financial goals progress.

**Scope:**
- Show active goals with progress bars
- Show goal target and current amount
- Show days/months until target date
- Show required monthly savings to reach goal
- Allow quick contribution action
- Show recently completed goals

**Files / Modules Affected:**
- `app/templates/partials/widgets/goals.html`
- `app/goals/services.py`
- `app/routers/dashboard.py`

**Acceptance Criteria:**
- [ ] Active goals are shown with progress
- [ ] Target and current amounts are shown
- [ ] Time until target is calculated
- [ ] Required monthly savings is calculated
- [ ] Quick contribution action works
- [ ] Completed goals are shown

**Test Requirements:**
- [ ] Test goal progress calculation
- [ ] Test time until target
- [ ] Test required savings calculation
- [ ] Test contribution action

**Dependencies:**
- DB-1100, GOAL-1400

**Estimated Effort:** 4 hours

---

### Phase 3: AI CFO / Digital Twin

---

#### AI-1200: AI Orchestrator Architecture

**Card ID:** AI-1200  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Build the AI orchestrator that routes requests to the correct engine and manages context.

**Scope:**
- Create AI orchestrator service
- Implement request classification (which engine should handle this?)
- Manage conversation context
- Enforce safety rules before processing
- Track cost and token usage per request
- Implement fallback to rule-based when LLM unavailable
- Return structured responses with confidence scores

**Files / Modules Affected:**
- `app/ai_cfo/services.py` (orchestrator)
- `app/ai_cfo/schemas.py`
- `app/ai_cfo/routes.py`

**Acceptance Criteria:**
- [ ] Requests are classified correctly
- [ ] Correct engine is invoked
- [ ] Conversation context is maintained
- [ ] Safety rules are enforced
- [ ] Cost is tracked per request
- [ ] Fallback works when LLM is down
- [ ] Responses include confidence scores

**Test Requirements:**
- [ ] Test request classification
- [ ] Test engine routing
- [ ] Test context management
- [ ] Test safety enforcement
- [ ] Test fallback behavior

**Dependencies:**
- PF-005

**Estimated Effort:** 10 hours

---

#### AI-1201: LLM Client and Prompt Management

**Card ID:** AI-1201  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement the LLM client wrapper and prompt template system.

**Scope:**
- Create OpenAI client wrapper with retry logic
- Implement prompt template system (Jinja2 for prompts)
- Create prompt templates for each engine
- Implement context injection (financial data into prompts)
- Handle API errors and rate limits
- Support multiple LLM providers (OpenAI primary, fallback)
- Implement response parsing and validation

**Files / Modules Affected:**
- `app/ai_cfo/llm/client.py`
- `app/ai_cfo/llm/prompts.py`
- `app/ai_cfo/llm/safety.py`

**Acceptance Criteria:**
- [ ] OpenAI client is configured
- [ ] Retry logic handles transient failures
- [ ] Prompt templates are defined for each engine
- [ ] Financial context is injected into prompts
- [ ] API errors are handled gracefully
- [ ] Rate limits are respected
- [ ] Responses are parsed and validated

**Test Requirements:**
- [ ] Test client connection
- [ ] Test retry logic
- [ ] Test prompt rendering
- [ ] Test error handling
- [ ] Test response parsing

**Dependencies:**
- AI-1200

**Estimated Effort:** 8 hours

---

#### AI-1202: Cost Control and Token Tracking

**Card ID:** AI-1202  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement token usage tracking and cost control per tenant.

**Scope:**
- Track tokens used per request
- Track cost per request (input + output tokens)
- Aggregate usage per tenant (daily, monthly)
- Enforce plan limits (reject if quota exceeded)
- Alert when approaching limit (80%, 95%)
- Show usage dashboard
- Implement cost optimization (use cheaper model for simple queries)

**Files / Modules Affected:**
- `app/ai_cfo/llm/cost_control.py`
- `app/ai_cfo/models.py` (AIUsageLog)
- `app/ai_cfo/routes.py` (usage dashboard)

**Acceptance Criteria:**
- [ ] Tokens are tracked per request
- [ ] Cost is calculated per request
- [ ] Usage is aggregated per tenant
- [ ] Plan limits are enforced
- [ ] Alerts are sent at thresholds
- [ ] Usage dashboard is available
- [ ] Cost optimization selects appropriate model

**Test Requirements:**
- [ ] Test token tracking accuracy
- [ ] Test cost calculation
- [ ] Test limit enforcement
- [ ] Test alert generation
- [ ] Test model selection optimization

**Dependencies:**
- AI-1201

**Estimated Effort:** 6 hours

---

#### AI-1203: AI Safety and Disclaimer System

**Card ID:** AI-1203  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement AI safety rules and automatic disclaimer injection.

**Scope:**
- Implement all 10 safety rules as configurable checks
- Inject disclaimer into every AI response
- Implement content filtering (prevent harmful advice)
- Implement confidence scoring
- Log all AI interactions for audit
- Implement human review flag for low-confidence responses
- Create safety dashboard for admins

**Files / Modules Affected:**
- `app/ai_cfo/llm/safety.py`
- `app/ai_cfo/models.py` (AIInsight, AIConversation)
- `app/ai_cfo/services.py`

**Acceptance Criteria:**
- [ ] All 10 safety rules are implemented
- [ ] Disclaimer is injected into every response
- [ ] Content filtering blocks harmful advice
- [ ] Confidence scores are calculated
- [ ] All interactions are logged
- [ ] Low-confidence responses are flagged
- [ ] Admin safety dashboard exists

**Test Requirements:**
- [ ] Test each safety rule
- [ ] Test disclaimer injection
- [ ] Test content filtering
- [ ] Test confidence scoring
- [ ] Test audit logging

**Dependencies:**
- AI-1201

**Estimated Effort:** 8 hours

---

#### AI-1204: Financial Digital Twin Data Model

**Card ID:** AI-1204  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement the Financial Digital Twin data model and storage.

**Scope:**
- Create AIDigitalTwin model
- Store current financial state snapshot
- Store health score components
- Store cash flow forecast
- Store risk indicators
- Implement twin update triggers
- Implement twin versioning (history)

**Files / Modules Affected:**
- `app/ai_cfo/models.py` (AIDigitalTwin)
- `app/ai_cfo/services.py` (twin management)
- `app/ai_cfo/tasks.py` (background updates)

**Acceptance Criteria:**
- [ ] Digital Twin model is created
- [ ] Current state is stored
- [ ] Health components are stored
- [ ] Cash flow forecast is stored
- [ ] Risk indicators are stored
- [ ] Twin updates on data changes
- [ ] Twin history is versioned

**Test Requirements:**
- [ ] Test twin creation
- [ ] Test twin update triggers
- [ ] Test data storage
- [ ] Test versioning

**Dependencies:**
- AI-1200, TRX-600, ACC-502

**Estimated Effort:** 8 hours

---

#### AI-1205: Financial Health Engine

**Card ID:** AI-1205  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Build the Financial Health Engine that calculates component scores.

**Scope:**
- Calculate Cash Flow Score (income vs expenses stability)
- Calculate Debt Management Score (debt-to-income, payment history)
- Calculate Savings Score (savings rate, emergency fund adequacy)
- Calculate Budget Discipline Score (adherence to budgets)
- Calculate Emergency Fund Score (months of expenses covered)
- Calculate Net Worth Growth Score (trend over time)
- Combine into overall Financial Health Score (0-100)
- Store component scores in Digital Twin

**Files / Modules Affected:**
- `app/ai_cfo/engines/health_engine.py`
- `app/ai_cfo/models.py`
- `app/ai_cfo/services.py`

**Acceptance Criteria:**
- [ ] Each component score is calculated correctly
- [ ] Overall score is weighted average of components
- [ ] Scores are stored in Digital Twin
- [ ] Scores update when data changes
- [ ] Score calculation is explainable (not black box)
- [ ] Scores are bounded (0-100)

**Test Requirements:**
- [ ] Test each component score with known data
- [ ] Test overall score calculation
- [ ] Test score updates
- [ ] Test boundary conditions

**Dependencies:**
- AI-1204

**Estimated Effort:** 10 hours

---

#### AI-1206: Financial Health Score

**Card ID:** AI-1206  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Expose the Financial Health Score in the UI with explanations.

**Scope:**
- Create health score endpoint
- Create health score widget for dashboard
- Show component score breakdown
- Show score history over time
- Explain why each score is what it is
- Suggest specific improvements per component
- Allow score recalculation on demand

**Files / Modules Affected:**
- `app/ai_cfo/routes.py`
- `app/templates/partials/widgets/health_score.html`
- `app/ai_cfo/engines/health_engine.py`

**Acceptance Criteria:**
- [ ] Health score is displayed
- [ ] Component breakdown is shown
- [ ] Score history is charted
- [ ] Explanations are human-readable
- [ ] Improvements are suggested
- [ ] Recalculation works on demand

**Test Requirements:**
- [ ] Test score display
- [ ] Test component breakdown
- [ ] Test history chart
- [ ] Test explanations
- [ ] Test recalculation

**Dependencies:**
- AI-1205

**Estimated Effort:** 6 hours

---

#### AI-1207: Cash Flow Intelligence Engine

**Card ID:** AI-1207  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Build the Cash Flow Intelligence Engine that analyzes income and expense patterns.

**Scope:**
- Analyze income stability (regular vs irregular)
- Analyze expense patterns (fixed vs variable vs discretionary)
- Detect seasonal trends
- Calculate runway (how long current savings last)
- Predict cash flow for next 3, 6, 12 months
- Identify cash flow risks (upcoming large expenses, income gaps)
- Generate cash flow insights

**Files / Modules Affected:**
- `app/ai_cfo/engines/cashflow_engine.py`
- `app/ai_cfo/models.py`
- `app/ai_cfo/services.py`

**Acceptance Criteria:**
- [ ] Income stability is analyzed
- [ ] Expense patterns are categorized
- [ ] Seasonal trends are detected
- [ ] Runway is calculated
- [ ] Cash flow is predicted for 3, 6, 12 months
- [ ] Risks are identified
- [ ] Insights are generated with confidence scores

**Test Requirements:**
- [ ] Test income stability analysis
- [ ] Test expense pattern detection
- [ ] Test seasonal trend detection
- [ ] Test runway calculation
- [ ] Test prediction accuracy
- [ ] Test risk identification

**Dependencies:**
- AI-1204

**Estimated Effort:** 10 hours

---

#### AI-1208: Spending Analyzer Engine

**Card ID:** AI-1208  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Build the Spending Analyzer that identifies patterns, anomalies, and opportunities.

**Scope:**
- Analyze spending by category over time
- Detect unusual spending (outliers vs historical average)
- Identify spending trends (increasing/decreasing)
- Compare spending to similar users (anonymized benchmarks)
- Identify potential savings opportunities
- Detect duplicate or erroneous transactions
- Generate spending insights

**Files / Modules Affected:**
- `app/ai_cfo/engines/spending_engine.py`
- `app/ai_cfo/models.py`
- `app/ai_cfo/services.py`

**Acceptance Criteria:**
- [ ] Spending is analyzed by category
- [ ] Unusual spending is detected
- [ ] Trends are identified
- [ ] Benchmarks are available (if data sufficient)
- [ ] Savings opportunities are identified
- [ ] Duplicates are detected
- [ ] Insights are actionable

**Test Requirements:**
- [ ] Test category analysis
- [ ] Test outlier detection
- [ ] Test trend identification
- [ ] Test duplicate detection
- [ ] Test savings suggestions

**Dependencies:**
- AI-1204

**Estimated Effort:** 8 hours

---

#### AI-1209: Subscription Analyzer

**Card ID:** AI-1209  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Build the Subscription Analyzer that identifies unused or overpriced subscriptions.

**Scope:**
- Analyze subscription usage (if usage data available)
- Detect price increases over time
- Identify duplicate subscriptions (e.g., multiple streaming services)
- Calculate total subscription burden (% of income)
- Suggest cancellations or downgrades
- Compare to market rates (if available)
- Generate subscription insights

**Files / Modules Affected:**
- `app/ai_cfo/engines/spending_engine.py` (or dedicated subscription analyzer)
- `app/ai_cfo/models.py`
- `app/subscriptions/services.py`

**Acceptance Criteria:**
- [ ] Subscriptions are analyzed
- [ ] Price increases are detected
- [ ] Duplicates are identified
- [ ] Subscription burden is calculated
- [ ] Suggestions are generated
- [ ] Insights are actionable

**Test Requirements:**
- [ ] Test price increase detection
- [ ] Test duplicate identification
- [ ] Test burden calculation
- [ ] Test suggestion generation

**Dependencies:**
- AI-1208, SUB-900

**Estimated Effort:** 6 hours

---

#### AI-1210: Bill Predictor

**Card ID:** AI-1210  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Build the Bill Predictor that forecasts upcoming bills and detects anomalies.

**Scope:**
- Predict next bill amounts based on historical data
- Detect bill amount anomalies (unexpected increase)
- Predict bill due dates
- Alert if bill is unusually high
- Suggest budget adjustments for seasonal bills
- Generate bill insights

**Files / Modules Affected:**
- `app/ai_cfo/engines/cashflow_engine.py` (or dedicated bill predictor)
- `app/ai_cfo/models.py`
- `app/bills/services.py`

**Acceptance Criteria:**
- [ ] Next bill amounts are predicted
- [ ] Anomalies are detected
- [ ] Due dates are predicted
- [ ] Alerts are generated for unusual bills
- [ ] Budget adjustments are suggested
- [ ] Predictions improve over time

**Test Requirements:**
- [ ] Test bill prediction accuracy
- [ ] Test anomaly detection
- [ ] Test alert generation
- [ ] Test suggestion quality

**Dependencies:**
- AI-1207, BILL-800

**Estimated Effort:** 6 hours

---

#### AI-1211: Debt Optimizer

**Card ID:** AI-1211  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Build the Debt Optimizer that recommends repayment strategies.

**Scope:**
- Calculate debt-to-income ratio
- Rank debts by interest rate (avalanche) and balance (snowball)
- Recommend optimal payment allocation
- Calculate payoff timeline for each strategy
- Simulate impact of extra payments
- Generate debt reduction plan
- Update recommendations as debts are paid

**Files / Modules Affected:**
- `app/ai_cfo/engines/debt_optimizer.py`
- `app/ai_cfo/models.py`
- `app/loans/services.py`

**Acceptance Criteria:**
- [ ] Debt-to-income is calculated
- [ ] Avalanche ranking is generated
- [ ] Snowball ranking is generated
- [ ] Optimal payment allocation is recommended
- [ ] Payoff timeline is calculated
- [ ] Extra payment impact is simulated
- [ ] Recommendations update dynamically

**Test Requirements:**
- [ ] Test debt-to-income calculation
- [ ] Test ranking algorithms
- [ ] Test payment allocation
- [ ] Test payoff timeline
- [ ] Test simulation accuracy

**Dependencies:**
- AI-1204, LOAN-1500

**Estimated Effort:** 8 hours

---

#### AI-1212: Savings Optimizer

**Card ID:** AI-1212  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Build the Savings Optimizer that recommends how much to save and where.

**Scope:**
- Calculate current savings rate (% of income)
- Recommend target savings rate based on goals
- Suggest which goal to prioritize
- Calculate impact of increased savings on goal timelines
- Identify areas to reduce spending to increase savings
- Generate savings plan
- Track savings rate over time

**Files / Modules Affected:**
- `app/ai_cfo/engines/savings_optimizer.py`
- `app/ai_cfo/models.py`
- `app/goals/services.py`

**Acceptance Criteria:**
- [ ] Current savings rate is calculated
- [ ] Target rate is recommended
- [ ] Goal priorities are suggested
- [ ] Impact of increased savings is calculated
- [ ] Spending reduction areas are identified
- [ ] Savings plan is generated
- [ ] Savings rate is tracked over time

**Test Requirements:**
- [ ] Test savings rate calculation
- [ ] Test target recommendation
- [ ] Test goal prioritization
- [ ] Test impact calculation
- [ ] Test spending reduction suggestions

**Dependencies:**
- AI-1204, GOAL-1400

**Estimated Effort:** 8 hours

---

#### AI-1213: Goal Planner

**Card ID:** AI-1213  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Build the Goal Planner that creates realistic savings plans for financial goals.

**Scope:**
- Calculate required monthly savings for each goal
- Prioritize goals based on urgency and importance
- Adjust timeline based on savings capacity
- Suggest goal consolidation or deferral
- Calculate probability of achieving goal on time
- Generate goal achievement plan
- Update plan as circumstances change

**Files / Modules Affected:**
- `app/ai_cfo/engines/goal_planner.py`
- `app/ai_cfo/models.py`
- `app/goals/services.py`

**Acceptance Criteria:**
- [ ] Required monthly savings is calculated
- [ ] Goals are prioritized
- [ ] Timeline is adjusted realistically
- [ ] Consolidation/deferral is suggested when needed
- [ ] Achievement probability is calculated
- [ ] Plan is generated and updated

**Test Requirements:**
- [ ] Test required savings calculation
- [ ] Test prioritization logic
- [ ] Test timeline adjustment
- [ ] Test probability calculation

**Dependencies:**
- AI-1212

**Estimated Effort:** 8 hours

---

#### AI-1214: What-If Simulator

**Card ID:** AI-1214  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Build the What-If Simulator that allows users to explore financial scenarios.

**Scope:**
- Simulate: "What if I save RO X more per month?"
- Simulate: "What if I buy a car with a loan?"
- Simulate: "What if my salary increases by Y%?"
- Simulate: "What if I pay off my credit card early?"
- Simulate: "What if I have an emergency expense of RO Z?"
- Show before/after comparison
- Show impact on goals, cash flow, and net worth
- Generate simulation report

**Files / Modules Affected:**
- `app/ai_cfo/engines/whatif_simulator.py`
- `app/ai_cfo/routes.py`
- `app/templates/pages/ai/simulator.html`

**Acceptance Criteria:**
- [ ] Common scenarios are supported
- [ ] Before/after comparison is shown
- [ ] Impact on goals is calculated
- [ ] Impact on cash flow is calculated
- [ ] Impact on net worth is calculated
- [ ] Simulation report is generated
- [ ] Simulations are fast (< 2 seconds)

**Test Requirements:**
- [ ] Test each scenario type
- [ ] Test comparison accuracy
- [ ] Test impact calculations
- [ ] Test performance

**Dependencies:**
- AI-1204, AI-1207

**Estimated Effort:** 10 hours

---

#### AI-1215: Recommendation Engine

**Card ID:** AI-1215  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Build the Recommendation Engine that produces prioritized, actionable financial advice.

**Scope:**
- Collect insights from all engines
- Prioritize recommendations by impact and urgency
- Format recommendations with: title, description, reasoning, expected impact, action
- Support recommendation types: pay debt, save more, reduce spending, review subscription, etc.
- Allow user to dismiss, approve, or snooze recommendations
- Track recommendation outcomes
- Learn from user actions (which recommendations are acted upon)

**Files / Modules Affected:**
- `app/ai_cfo/engines/recommendation_engine.py`
- `app/ai_cfo/models.py` (AIInsight)
- `app/ai_cfo/routes.py`

**Acceptance Criteria:**
- [ ] Recommendations are collected from all engines
- [ ] Prioritization is logical (urgency + impact)
- [ ] Each recommendation has title, description, reasoning, impact, action
- [ ] Multiple types are supported
- [ ] User can dismiss, approve, or snooze
- [ ] Outcomes are tracked
- [ ] Engine learns from user actions

**Test Requirements:**
- [ ] Test prioritization logic
- [ ] Test recommendation format
- [ ] Test user actions
- [ ] Test outcome tracking
- [ ] Test learning mechanism

**Dependencies:**
- AI-1205, AI-1207, AI-1208, AI-1211, AI-1212, AI-1213

**Estimated Effort:** 10 hours

---

#### AI-1216: Daily Brief Generation

**Card ID:** AI-1216  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement the Daily Brief — a personalized financial summary generated each morning.

**Scope:**
- Generate brief at configurable time (default 7 AM)
- Include: today's bills, yesterday's spending, budget status, upcoming events
- Include: any AI alerts or recommendations
- Format as concise, readable summary
- Send via email or show in dashboard
- Allow user to customize brief contents
- Track brief engagement (opened, acted upon)

**Files / Modules Affected:**
- `app/ai_cfo/engines/daily_brief.py`
- `app/ai_cfo/tasks.py`
- `app/templates/emails/daily_brief.html`
- `app/notifications/services.py`

**Acceptance Criteria:**
- [ ] Brief is generated daily at configured time
- [ ] Today's bills are included
- [ ] Yesterday's spending is summarized
- [ ] Budget status is included
- [ ] Upcoming events are listed
- [ ] AI alerts are included
- [ ] Format is concise and readable
- [ ] Delivery method is configurable
- [ ] Contents are customizable

**Test Requirements:**
- [ ] Test brief generation timing
- [ ] Test content accuracy
- [ ] Test delivery
- [ ] Test customization
- [ ] Test engagement tracking

**Dependencies:**
- AI-1215, NOTIF-1600

**Estimated Effort:** 8 hours

---

#### AI-1217: Weekly Review Generation

**Card ID:** AI-1217  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement the Weekly Review — a summary of the week's financial activity.

**Scope:**
- Generate review every Sunday (configurable)
- Include: total income, total expenses, net cash flow
- Include: top spending categories, unusual transactions
- Include: budget progress, goal progress
- Include: AI insights and recommendations
- Compare to previous week
- Format as engaging, readable summary

**Files / Modules Affected:**
- `app/ai_cfo/engines/weekly_review.py`
- `app/ai_cfo/tasks.py`
- `app/templates/emails/weekly_review.html`

**Acceptance Criteria:**
- [ ] Review is generated weekly
- [ ] Income, expenses, cash flow are summarized
- [ ] Top categories are listed
- [ ] Unusual transactions are highlighted
- [ ] Budget and goal progress are shown
- [ ] AI insights are included
- [ ] Week-over-week comparison is shown
- [ ] Format is engaging

**Test Requirements:**
- [ ] Test review generation
- [ ] Test content accuracy
- [ ] Test comparison logic
- [ ] Test delivery

**Dependencies:**
- AI-1216

**Estimated Effort:** 6 hours

---

#### AI-1218: Monthly Review Generation

**Card ID:** AI-1218  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement the Monthly Review — a comprehensive financial report.

**Scope:**
- Generate review on 1st of each month
- Include: complete income statement, expense breakdown, net worth change
- Include: budget vs actual, goal progress, debt reduction
- Include: Financial Health Score and component changes
- Include: AI recommendations for the month ahead
- Compare to previous month and same month last year
- Format as comprehensive but readable report

**Files / Modules Affected:**
- `app/ai_cfo/engines/monthly_review.py`
- `app/ai_cfo/tasks.py`
- `app/templates/emails/monthly_review.html`
- `app/reports/generators/`

**Acceptance Criteria:**
- [ ] Review is generated monthly
- [ ] Income statement is included
- [ ] Expense breakdown is included
- [ ] Net worth change is shown
- [ ] Budget vs actual is compared
- [ ] Goal progress is shown
- [ ] Health score is included
- [ ] Recommendations are included
- [ ] Comparisons are shown

**Test Requirements:**
- [ ] Test monthly generation
- [ ] Test content accuracy
- [ ] Test comparison logic
- [ ] Test delivery

**Dependencies:**
- AI-1217

**Estimated Effort:** 8 hours

---

#### AI-1219: Proactive Alerts Engine

**Card ID:** AI-1219  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Build the Proactive Alerts Engine that detects issues and opportunities without user asking.

**Scope:**
- Detect low account balances
- Detect upcoming cash flow problems
- Detect overspending in categories
- Detect unusual transactions (potential fraud)
- Detect missed bills
- Detect subscription price increases
- Detect goal off-track
- Send alerts via preferred channel
- Allow alert configuration (thresholds, channels, quiet hours)

**Files / Modules Affected:**
- `app/ai_cfo/engines/proactive_alerts.py`
- `app/ai_cfo/tasks.py`
- `app/notifications/services.py`

**Acceptance Criteria:**
- [ ] Low balance alerts work
- [ ] Cash flow alerts work
- [ ] Overspending alerts work
- [ ] Unusual transaction alerts work
- [ ] Missed bill alerts work
- [ ] Price increase alerts work
- [ ] Goal off-track alerts work
- [ ] Alerts respect user preferences
- [ ] Alert thresholds are configurable

**Test Requirements:**
- [ ] Test each alert type
- [ ] Test threshold configuration
- [ ] Test channel delivery
- [ ] Test quiet hours
- [ ] Test alert deduplication

**Dependencies:**
- AI-1215, NOTIF-1600

**Estimated Effort:** 8 hours

---

#### AI-1220: AI Chat Interface

**Card ID:** AI-1220  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Implement the AI Chat interface for conversational financial guidance.

**Scope:**
- Create chat UI (message list, input, send button)
- Implement WebSocket or polling for real-time feel
- Store conversation history
- Send user message to AI orchestrator
- Display AI response with formatting
- Support suggested questions/quick actions
- Show typing indicator
- Allow conversation history view
- Export conversation (optional)

**Files / Modules Affected:**
- `app/ai_cfo/routes.py` (chat endpoints)
- `app/templates/pages/ai/chat.html`
- `app/ai_cfo/models.py` (AIConversation)
- `app/ai_cfo/services.py`

**Acceptance Criteria:**
- [ ] Chat UI is functional
- [ ] Messages are sent and received
- [ ] Conversation history is stored
- [ ] AI responses are formatted
- [ ] Suggested questions are shown
- [ ] Typing indicator works
- [ ] History can be viewed
- [ ] Context is maintained across messages

**Test Requirements:**
- [ ] Test message sending
- [ ] Test response receiving
- [ ] Test history storage
- [ ] Test context maintenance
- [ ] Test suggested questions

**Dependencies:**
- AI-1200, AI-1201

**Estimated Effort:** 10 hours

---

#### AI-1221: AI Memory System

**Card ID:** AI-1221  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement the AI Memory system that maintains context across sessions.

**Scope:**
- Store short-term memory (current conversation, last 10 messages)
- Store medium-term memory (recent insights, user reactions, 30 days)
- Store long-term memory (preferences, risk tolerance, dismissed recommendations, recurring patterns)
- Implement memory retrieval for context injection
- Implement memory summarization (compress old memories)
- Allow user to view and delete memory
- Ensure memory is tenant-scoped and private

**Files / Modules Affected:**
- `app/ai_cfo/models.py` (AIMemory)
- `app/ai_cfo/services.py` (memory management)
- `app/ai_cfo/llm/prompts.py`

**Acceptance Criteria:**
- [ ] Short-term memory works (conversation context)
- [ ] Medium-term memory works (recent insights)
- [ ] Long-term memory works (preferences, patterns)
- [ ] Memory is retrieved for context injection
- [ ] Old memories are summarized
- [ ] User can view and delete memory
- [ ] Memory is tenant-scoped and private

**Test Requirements:**
- [ ] Test memory storage
- [ ] Test memory retrieval
- [ ] Test summarization
- [ ] Test privacy (no cross-tenant leakage)
- [ ] Test user deletion

**Dependencies:**
- AI-1220

**Estimated Effort:** 8 hours

---

#### AI-1222: AI Confidence Scoring

**Card ID:** AI-1222  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement confidence scoring for all AI insights and recommendations.

**Scope:**
- Calculate confidence based on data quality and quantity
- Calculate confidence based on historical accuracy
- Calculate confidence based on model certainty
- Display confidence to user (e.g., "High confidence", "Medium confidence")
- Flag low-confidence insights for review
- Adjust confidence thresholds based on user feedback
- Log confidence scores for analysis

**Files / Modules Affected:**
- `app/ai_cfo/services.py`
- `app/ai_cfo/models.py`
- `app/ai_cfo/engines/`

**Acceptance Criteria:**
- [ ] Confidence is calculated for all insights
- [ ] Confidence is displayed to user
- [ ] Low-confidence insights are flagged
- [ ] Thresholds are adjustable
- [ ] User feedback adjusts confidence
- [ ] Scores are logged

**Test Requirements:**
- [ ] Test confidence calculation
- [ ] Test display
- [ ] Test flagging
- [ ] Test feedback loop

**Dependencies:**
- AI-1203

**Estimated Effort:** 6 hours

---

#### AI-1223: Dashboard v2 (AI-Centric)

**Card ID:** AI-1223  
**Epic:** AI-1200 — AI Financial Coach  
**Priority:** Critical  
**Status:** Backlog

**Goal:**  
Redesign the dashboard to be AI-centric with insights, recommendations, and health score.

**Scope:**
- Add Financial Health Score widget (prominent)
- Add AI recommendations widget (top 3 actions)
- Add AI insights widget (recent discoveries)
- Add "Ask AI" quick action
- Add cash flow prediction widget
- Add goal progress with AI suggestions
- Add spending anomaly alerts
- Keep existing widgets (bills, subscriptions, net worth)
- Make dashboard personalized based on user behavior

**Files / Modules Affected:**
- `app/templates/pages/dashboard/index.html`
- `app/routers/dashboard.py`
- `app/ai_cfo/services.py`
- `app/ai_cfo/routes.py`

**Acceptance Criteria:**
- [ ] Health score is prominently displayed
- [ ] Top 3 recommendations are shown
- [ ] Recent insights are displayed
- [ ] "Ask AI" is easily accessible
- [ ] Cash flow prediction is shown
- [ ] Goal progress has AI suggestions
- [ ] Spending anomalies are highlighted
- [ ] Dashboard is personalized
- [ ] Layout is responsive

**Test Requirements:**
- [ ] Test widget display
- [ ] Test personalization
- [ ] Test responsiveness
- [ ] Test data accuracy

**Dependencies:**
- AI-1206, AI-1215, AI-1216, AI-1219

**Estimated Effort:** 10 hours

---

### Phase 4: Family, Automation, Admin, Billing

---

#### FAM-1300: Family Model and Roles

**Card ID:** FAM-1300  
**Epic:** FAM-1300 — Family Finance  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement the family data model with roles and permissions.

**Scope:**
- Create Family model
- Create FamilyMember model with roles
- Implement role-based permissions
- Support family creation and member invitation
- Support family switching (if user belongs to multiple)
- Integrate with existing tenant system

**Files / Modules Affected:**
- `app/family/models.py` (Family, FamilyMember)
- `app/family/schemas.py`
- `app/family/services.py`
- `app/family/routes.py`
- `app/family/permissions.py`

**Acceptance Criteria:**
- [ ] Family can be created
- [ ] Members can be invited
- [ ] Roles are enforced
- [ ] Permissions work correctly
- [ ] Family switching works
- [ ] Integration with tenant system is seamless

**Test Requirements:**
- [ ] Test family creation
- [ ] Test member invitation
- [ ] Test each role's permissions
- [ ] Test family switching
- [ ] Test tenant integration

**Dependencies:**
- AUTH-305

**Estimated Effort:** 8 hours

---

#### FAM-1301: Shared and Private Accounts

**Card ID:** FAM-1301  
**Epic:** FAM-1300 — Family Finance  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement shared and private account visibility within families.

**Scope:**
- Add visibility field to accounts (private, shared, restricted)
- Implement account access rules based on family role
- Show shared accounts in family dashboard
- Show private accounts only to owner
- Allow account sharing configuration
- Handle account access in transactions and reports

**Files / Modules Affected:**
- `app/accounting/models.py` (Account visibility)
- `app/family/services.py`
- `app/family/permissions.py`
- `app/accounting/services.py`

**Acceptance Criteria:**
- [ ] Accounts can be marked private or shared
- [ ] Shared accounts are visible to family members
- [ ] Private accounts are visible only to owner
- [ ] Access rules are enforced
- [ ] Sharing can be configured
- [ ] Transactions respect account visibility

**Test Requirements:**
- [ ] Test visibility settings
- [ ] Test shared account access
- [ ] Test private account protection
- [ ] Test transaction visibility
- [ ] Test report filtering

**Dependencies:**
- FAM-1300, ACC-500

**Estimated Effort:** 6 hours

---

#### FAM-1302: Family Goals

**Card ID:** FAM-1302  
**Epic:** FAM-1300 — Family Finance  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement shared financial goals for families.

**Scope:**
- Create family goal model (shared goal, contributions from members)
- Track individual contributions to family goals
- Show family goal progress
- Allow goal contribution from any family member
- Generate family goal reports
- Integrate with AI goal planner

**Files / Modules Affected:**
- `app/goals/models.py` (FamilyGoal, FamilyGoalContribution)
- `app/goals/services.py`
- `app/goals/routes.py`
- `app/family/services.py`

**Acceptance Criteria:**
- [ ] Family goals can be created
- [ ] Members can contribute
- [ ] Contributions are tracked per member
- [ ] Progress is shown
- [ ] Reports are generated
- [ ] AI planner integrates with family goals

**Test Requirements:**
- [ ] Test family goal creation
- [ ] Test member contributions
- [ ] Test contribution tracking
- [ ] Test progress calculation
- [ ] Test AI integration

**Dependencies:**
- FAM-1300, GOAL-1400

**Estimated Effort:** 6 hours

---

#### FAM-1303: Family Budgets

**Card ID:** FAM-1303  
**Epic:** FAM-1300 — Family Finance  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement shared budgets for families.

**Scope:**
- Create family budget model
- Track spending across all family members
- Show family budget vs actual
- Alert when family budget is near limit
- Allow per-member budget allocation
- Generate family budget reports

**Files / Modules Affected:**
- `app/budgets/models.py` (FamilyBudget)
- `app/budgets/services.py`
- `app/family/services.py`

**Acceptance Criteria:**
- [ ] Family budgets can be created
- [ ] Spending is tracked across members
- [ ] Budget vs actual is shown
- [ ] Alerts work for family budgets
- [ ] Per-member allocation is supported
- [ ] Reports are generated

**Test Requirements:**
- [ ] Test family budget creation
- [ ] Test cross-member tracking
- [ ] Test alert generation
- [ ] Test allocation
- [ ] Test reports

**Dependencies:**
- FAM-1300, BDG-1000

**Estimated Effort:** 6 hours

---

#### FAM-1304: Allowance and Chore Tracking

**Card ID:** FAM-1304  
**Epic:** FAM-1300 — Family Finance  
**Priority:** Low  
**Status:** Backlog

**Goal:**  
Implement allowance and chore tracking for children.

**Scope:**
- Create allowance model (amount, frequency, child)
- Create chore model (description, value, assigned to, completed)
- Automate allowance transfers
- Track chore completion
- Link chore completion to allowance
- Show child dashboard (simplified view)
- Parent approval for chore completion

**Files / Modules Affected:**
- `app/family/models.py` (Allowance, Chore)
- `app/family/services.py`
- `app/family/routes.py`
- `app/templates/pages/family/child_dashboard.html`

**Acceptance Criteria:**
- [ ] Allowances can be configured
- [ ] Chores can be created and assigned
- [ ] Allowance transfers are automated
- [ ] Chore completion is tracked
- [ ] Child dashboard is simplified
- [ ] Parent approval is required

**Test Requirements:**
- [ ] Test allowance configuration
- [ ] Test chore assignment
- [ ] Test automation
- [ ] Test parent approval
- [ ] Test child dashboard

**Dependencies:**
- FAM-1300

**Estimated Effort:** 8 hours

---

#### FAM-1305: Family Dashboard

**Card ID:** FAM-1305  
**Epic:** FAM-1300 — Family Finance  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Create a family dashboard showing combined financial health.

**Scope:**
- Show combined net worth
- Show combined cash flow
- Show family goals progress
- Show family budget status
- Show member contributions
- Show recent family transactions
- Allow drill-down to individual members
- Respect privacy settings (private accounts hidden)

**Files / Modules Affected:**
- `app/templates/pages/family/dashboard.html`
- `app/family/services.py`
- `app/routers/dashboard.py`

**Acceptance Criteria:**
- [ ] Combined net worth is shown
- [ ] Combined cash flow is shown
- [ ] Family goals are displayed
- [ ] Family budget status is shown
- [ ] Member contributions are tracked
- [ ] Recent transactions are shown
- [ ] Drill-down works
- [ ] Privacy is respected

**Test Requirements:**
- [ ] Test combined calculations
- [ ] Test privacy filtering
- [ ] Test drill-down
- [ ] Test member contributions

**Dependencies:**
- FAM-1301, FAM-1302, FAM-1303

**Estimated Effort:** 6 hours

---

#### GOAL-1400: Goal Creation and Tracking

**Card ID:** GOAL-1400  
**Epic:** GOAL-1400 — Goals  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement financial goal creation and progress tracking.

**Scope:**
- Create goal model (name, target amount, current amount, target date, category)
- Support goal types: emergency fund, car, house, education, vacation, retirement, custom
- Create goal contribution model
- Track progress percentage
- Show goal timeline
- Allow goal editing and deletion
- Support goal archiving

**Files / Modules Affected:**
- `app/goals/models.py` (Goal, GoalContribution)
- `app/goals/schemas.py`
- `app/goals/services.py`
- `app/goals/routes.py`

**Acceptance Criteria:**
- [ ] Goals can be created with target and date
- [ ] Goal types are supported
- [ ] Contributions are tracked
- [ ] Progress percentage is calculated
- [ ] Timeline is shown
- [ ] Goals can be edited and deleted
- [ ] Goals can be archived

**Test Requirements:**
- [ ] Test goal creation
- [ ] Test contribution tracking
- [ ] Test progress calculation
- [ ] Test timeline
- [ ] Test edit and delete

**Dependencies:**
- TRX-600

**Estimated Effort:** 6 hours

---

#### GOAL-1401: Goal Contributions

**Card ID:** GOAL-1401  
**Epic:** GOAL-1400 — Goals  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement goal contribution tracking and automated contributions.

**Scope:**
- Manual contribution entry
- Automated recurring contributions (weekly, monthly)
- Link contributions to transactions
- Show contribution history
- Calculate contribution impact on timeline
- Allow contribution adjustment
- Notify when goal is reached

**Files / Modules Affected:**
- `app/goals/services.py`
- `app/goals/routes.py`
- `app/goals/tasks.py`

**Acceptance Criteria:**
- [ ] Manual contributions work
- [ ] Automated contributions work
- [ ] Contributions link to transactions
- [ ] History is tracked
- [ ] Timeline impact is calculated
- [ ] Contributions can be adjusted
- [ ] Goal reached notification is sent

**Test Requirements:**
- [ ] Test manual contribution
- [ ] Test automated contribution
- [ ] Test timeline impact
- [ ] Test notification

**Dependencies:**
- GOAL-1400

**Estimated Effort:** 6 hours

---

#### GOAL-1402: Goal Projections

**Card ID:** GOAL-1402  
**Epic:** GOAL-1400 — Goals  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement goal achievement projections and simulations.

**Scope:**
- Calculate expected completion date based on current savings rate
- Calculate required monthly savings to meet target date
- Simulate impact of increased contributions
- Show probability of on-time achievement
- Generate goal projection chart
- Update projections as circumstances change

**Files / Modules Affected:**
- `app/goals/services.py`
- `app/ai_cfo/engines/goal_planner.py`
- `app/templates/pages/goals/projections.html`

**Acceptance Criteria:**
- [ ] Completion date is projected
- [ ] Required savings is calculated
- [ ] Impact simulation works
- [ ] Probability is calculated
- [ ] Projection chart is shown
- [ ] Projections update dynamically

**Test Requirements:**
- [ ] Test projection accuracy
- [ ] Test required savings calculation
- [ ] Test simulation
- [ ] Test probability calculation

**Dependencies:**
- GOAL-1401, AI-1213

**Estimated Effort:** 6 hours

---

#### LOAN-1500: Loan Accounts

**Card ID:** LOAN-1500  
**Epic:** LOAN-1500 — Loans  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement loan account tracking.

**Scope:**
- Create loan model (name, lender, principal, interest rate, term, start date)
- Support loan types: personal, car, home, credit card, student
- Track current balance and paid amount
- Calculate monthly payment
- Show loan amortization schedule
- Link loan payments to transactions

**Files / Modules Affected:**
- `app/loans/models.py` (LoanAccount, LoanPayment)
- `app/loans/schemas.py`
- `app/loans/services.py`
- `app/loans/routes.py`

**Acceptance Criteria:**
- [ ] Loans can be created with all details
- [ ] Loan types are supported
- [ ] Balance and paid amount are tracked
- [ ] Monthly payment is calculated
- [ ] Amortization schedule is generated
- [ ] Payments link to transactions
- [ ] Loans can be edited and deleted

**Test Requirements:**
- [ ] Test loan creation
- [ ] Test balance tracking
- [ ] Test payment calculation
- [ ] Test amortization schedule
- [ ] Test transaction linking

**Dependencies:**
- TRX-600, ACC-500

**Estimated Effort:** 8 hours

---

#### LOAN-1501: Interest Calculation

**Card ID:** LOAN-1501  
**Epic:** LOAN-1500 — Loans  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement accurate interest calculation for various loan types.

**Scope:**
- Support simple interest
- Support compound interest (monthly, daily)
- Support reducing balance method
- Support flat rate method
- Calculate total interest over loan term
- Calculate interest saved from early payments
- Handle Islamic finance (profit rate) considerations

**Files / Modules Affected:**
- `app/loans/services.py`
- `app/loans/models.py`

**Acceptance Criteria:**
- [ ] Simple interest is calculated correctly
- [ ] Compound interest is calculated correctly
- [ ] Reducing balance is calculated correctly
- [ ] Flat rate is calculated correctly
- [ ] Total interest is accurate
- [ ] Interest saved from early payments is calculated
- [ ] Islamic finance rates are supported

**Test Requirements:**
- [ ] Test simple interest
- [ ] Test compound interest
- [ ] Test reducing balance
- [ ] Test flat rate
- [ ] Test early payment savings
- [ ] Test Islamic finance rates

**Dependencies:**
- LOAN-1500

**Estimated Effort:** 6 hours

---

#### LOAN-1502: Repayment Schedule

**Card ID:** LOAN-1502  
**Epic:** LOAN-1500 — Loans  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Generate and display loan repayment schedules.

**Scope:**
- Generate full amortization schedule
- Show payment number, date, principal, interest, balance
- Handle extra payments (recalculate schedule)
- Handle missed payments
- Show schedule summary (total payments, total interest)
- Export schedule to CSV/Excel
- Show schedule chart

**Files / Modules Affected:**
- `app/loans/services.py`
- `app/loans/routes.py`
- `app/templates/pages/loans/schedule.html`

**Acceptance Criteria:**
- [ ] Full schedule is generated
- [ ] Principal and interest are split per payment
- [ ] Extra payments recalculate schedule
- [ ] Missed payments are handled
- [ ] Summary is shown
- [ ] Export works
- [ ] Chart is displayed

**Test Requirements:**
- [ ] Test schedule generation
- [ ] Test extra payment recalculation
- [ ] Test missed payment handling
- [ ] Test export
- [ ] Test chart accuracy

**Dependencies:**
- LOAN-1501

**Estimated Effort:** 6 hours

---

#### LOAN-1503: Snowball Strategy

**Card ID:** LOAN-1503  
**Epic:** LOAN-1500 — Loans  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement debt snowball repayment strategy.

**Scope:**
- Rank debts by balance (smallest first)
- Calculate payoff order
- Simulate snowball effect (payments from paid-off debts applied to next)
- Show snowball timeline
- Compare snowball vs current approach
- Generate snowball recommendation

**Files / Modules Affected:**
- `app/loans/services.py`
- `app/ai_cfo/engines/debt_optimizer.py`
- `app/templates/pages/loans/snowball.html`

**Acceptance Criteria:**
- [ ] Debts are ranked by balance
- [ ] Payoff order is calculated
- [ ] Snowball effect is simulated
- [ ] Timeline is shown
- [ ] Comparison to current approach is shown
- [ ] Recommendation is generated

**Test Requirements:**
- [ ] Test ranking
- [ ] Test simulation
- [ ] Test timeline
- [ ] Test comparison

**Dependencies:**
- LOAN-1502

**Estimated Effort:** 4 hours

---

#### LOAN-1504: Avalanche Strategy

**Card ID:** LOAN-1504  
**Epic:** LOAN-1500 — Loans  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement debt avalanche repayment strategy.

**Scope:**
- Rank debts by interest rate (highest first)
- Calculate payoff order
- Simulate avalanche effect
- Show avalanche timeline
- Compare avalanche vs snowball vs current
- Generate avalanche recommendation
- Show interest saved with avalanche

**Files / Modules Affected:**
- `app/loans/services.py`
- `app/ai_cfo/engines/debt_optimizer.py`
- `app/templates/pages/loans/avalanche.html`

**Acceptance Criteria:**
- [ ] Debts are ranked by interest rate
- [ ] Payoff order is calculated
- [ ] Avalanche effect is simulated
- [ ] Timeline is shown
- [ ] Comparison to snowball and current is shown
- [ ] Interest saved is calculated
- [ ] Recommendation is generated

**Test Requirements:**
- [ ] Test ranking
- [ ] Test simulation
- [ ] Test timeline
- [ ] Test comparison
- [ ] Test interest saved

**Dependencies:**
- LOAN-1502

**Estimated Effort:** 4 hours

---

#### LOAN-1505: Loan Simulator

**Card ID:** LOAN-1505  
**Epic:** LOAN-1500 — Loans  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Build a loan simulator for exploring different loan scenarios.

**Scope:**
- Simulate new loan (principal, rate, term)
- Compare different loan offers
- Simulate impact of extra payments
- Simulate impact of refinancing
- Show total cost comparison
- Generate loan recommendation

**Files / Modules Affected:**
- `app/loans/services.py`
- `app/ai_cfo/engines/whatif_simulator.py`
- `app/templates/pages/loans/simulator.html`

**Acceptance Criteria:**
- [ ] New loans can be simulated
- [ ] Loan offers can be compared
- [ ] Extra payment impact is shown
- [ ] Refinancing impact is shown
- [ ] Total cost comparison works
- [ ] Recommendation is generated

**Test Requirements:**
- [ ] Test simulation accuracy
- [ ] Test comparison
- [ ] Test extra payment impact
- [ ] Test refinancing impact

**Dependencies:**
- LOAN-1504, AI-1214

**Estimated Effort:** 6 hours

---

#### NOTIF-1600: Email Notifications

**Card ID:** NOTIF-1600  
**Epic:** NOTIF-1600 — Notifications  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement email notification system.

**Scope:**
- Configure SMTP or email service (SendGrid, AWS SES)
- Create email template system
- Implement email queue (Celery + Redis)
- Support HTML and plain text emails
- Implement email delivery tracking
- Handle bounces and failures
- Create email preview for testing

**Files / Modules Affected:**
- `app/notifications/channels/email.py`
- `app/notifications/services.py`
- `app/notifications/tasks.py`
- `app/templates/emails/base.html`

**Acceptance Criteria:**
- [ ] Emails can be sent
- [ ] Templates are supported
- [ ] Queue system works
- [ ] HTML and text versions are sent
- [ ] Delivery is tracked
- [ ] Bounces are handled
- [ ] Preview works for testing

**Test Requirements:**
- [ ] Test email sending
- [ ] Test template rendering
- [ ] Test queue processing
- [ ] Test bounce handling
- [ ] Test preview

**Dependencies:**
- PF-100

**Estimated Effort:** 6 hours

---

#### NOTIF-1601: Push Notifications

**Card ID:** NOTIF-1601  
**Epic:** NOTIF-1600 — Notifications  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement push notification system for browsers and mobile.

**Scope:**
- Implement Web Push API for browsers
- Store push subscription data
- Send push notifications via service worker
- Support notification actions (click to open, dismiss)
- Track push notification engagement
- Handle subscription expiration

**Files / Modules Affected:**
- `app/notifications/channels/push.py`
- `app/notifications/models.py` (PushSubscription)
- `app/static/js/service-worker.js`
- `app/notifications/services.py`

**Acceptance Criteria:**
- [ ] Push subscriptions can be created
- [ ] Push notifications are sent
- [ ] Service worker handles notifications
- [ ] Actions work (click, dismiss)
- [ ] Engagement is tracked
- [ ] Expired subscriptions are cleaned up

**Test Requirements:**
- [ ] Test subscription
- [ ] Test push sending
- [ ] Test service worker
- [ ] Test actions
- [ ] Test cleanup

**Dependencies:**
- NOTIF-1600

**Estimated Effort:** 6 hours

---

#### NOTIF-1602: Notification Preferences

**Card ID:** NOTIF-1602  
**Epic:** NOTIF-1600 — Notifications  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement user notification preference management.

**Scope:**
- Create notification preference model
- Allow channel selection per notification type (email, push, SMS, none)
- Allow frequency selection (immediate, daily digest, weekly)
- Allow quiet hours configuration
- Allow notification type enable/disable
- Create preferences UI
- Apply preferences to all notification sends

**Files / Modules Affected:**
- `app/notifications/models.py` (NotificationPreference)
- `app/notifications/schemas.py`
- `app/notifications/services.py`
- `app/notifications/routes.py`

**Acceptance Criteria:**
- [ ] Preferences can be configured per type
- [ ] Channel selection works
- [ ] Frequency selection works
- [ ] Quiet hours are respected
- [ ] Types can be enabled/disabled
- [ ] UI is intuitive
- [ ] Preferences are applied to all sends

**Test Requirements:**
- [ ] Test preference storage
- [ ] Test channel filtering
- [ ] Test frequency filtering
- [ ] Test quiet hours
- [ ] Test enable/disable

**Dependencies:**
- NOTIF-1600

**Estimated Effort:** 4 hours

---

#### NOTIF-1603: Daily Summary Email

**Card ID:** NOTIF-1603  
**Epic:** NOTIF-1600 — Notifications  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement daily summary email with financial snapshot.

**Scope:**
- Generate daily summary at configured time
- Include: yesterday's transactions, account balances, upcoming bills
- Include: budget status, goal progress
- Include: any AI alerts
- Format as clean, readable email
- Respect user preferences (opt-in/out)
- Track open rates

**Files / Modules Affected:**
- `app/notifications/tasks.py`
- `app/templates/emails/daily_summary.html`
- `app/notifications/services.py`

**Acceptance Criteria:**
- [ ] Daily summary is generated
- [ ] Content is accurate and relevant
- [ ] Format is clean and readable
- [ ] Preferences are respected
- [ ] Open rates are tracked
- [ ] Unsubscribe works

**Test Requirements:**
- [ ] Test generation timing
- [ ] Test content accuracy
- [ ] Test preference respect
- [ ] Test tracking

**Dependencies:**
- NOTIF-1600, NOTIF-1602

**Estimated Effort:** 4 hours

---

#### NOTIF-1604: Monthly Summary Email

**Card ID:** NOTIF-1604  
**Epic:** NOTIF-1600 — Notifications  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement monthly summary email with comprehensive financial review.

**Scope:**
- Generate monthly summary on 1st of month
- Include: income, expenses, net worth change
- Include: budget vs actual, goal progress, debt reduction
- Include: top spending categories, unusual transactions
- Include: Financial Health Score
- Include: AI recommendations for month ahead
- Format as comprehensive but readable email

**Files / Modules Affected:**
- `app/notifications/tasks.py`
- `app/templates/emails/monthly_summary.html`
- `app/notifications/services.py`

**Acceptance Criteria:**
- [ ] Monthly summary is generated
- [ ] All key metrics are included
- [ ] Format is comprehensive but readable
- [ ] Preferences are respected
- [ ] Open rates are tracked

**Test Requirements:**
- [ ] Test generation
- [ ] Test content accuracy
- [ ] Test metrics inclusion
- [ ] Test tracking

**Dependencies:**
- NOTIF-1603

**Estimated Effort:** 4 hours

---

#### ADMIN-1700: Super Admin Dashboard

**Card ID:** ADMIN-1700  
**Epic:** ADMIN-1700 — Administration  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Create super admin dashboard for platform management.

**Scope:**
- Show platform overview (tenants, users, transactions)
- Show system health (database, Redis, queue)
- Show recent errors and exceptions
- Show AI usage and costs
- Show revenue metrics (if billing enabled)
- Allow admin actions (suspend tenant, reset password, etc.)
- Implement admin authentication (separate from tenant auth)

**Files / Modules Affected:**
- `app/admin/routes.py`
- `app/admin/services.py`
- `app/admin/permissions.py`
- `app/templates/pages/admin/dashboard.html`

**Acceptance Criteria:**
- [ ] Platform overview is shown
- [ ] System health is monitored
- [ ] Errors are displayed
- [ ] AI usage is tracked
- [ ] Revenue metrics are shown
- [ ] Admin actions work
- [ ] Admin auth is separate and secure

**Test Requirements:**
- [ ] Test dashboard data
- [ ] Test admin actions
- [ ] Test auth separation
- [ ] Test security

**Dependencies:**
- AUTH-301, SAAS-200

**Estimated Effort:** 8 hours

---

#### ADMIN-1701: Tenant Management

**Card ID:** ADMIN-1701  
**Epic:** ADMIN-1700 — Administration  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement tenant management for super admins.

**Scope:**
- List all tenants with pagination
- View tenant details (members, plan, usage)
- Suspend/activate tenant
- Change tenant plan
- Delete tenant (with confirmation)
- Export tenant data
- Impersonate tenant admin (for support)

**Files / Modules Affected:**
- `app/admin/routes.py`
- `app/admin/services.py`
- `app/templates/pages/admin/tenants.html`

**Acceptance Criteria:**
- [ ] Tenants are listed
- [ ] Details are viewable
- [ ] Suspend/activate works
- [ ] Plan changes work
- [ ] Deletion works with confirmation
- [ ] Export works
- [ ] Impersonation works for support

**Test Requirements:**
- [ ] Test listing
- [ ] Test details
- [ ] Test suspend/activate
- [ ] Test plan change
- [ ] Test deletion
- [ ] Test impersonation

**Dependencies:**
- ADMIN-1700

**Estimated Effort:** 6 hours

---

#### ADMIN-1702: Subscription Management

**Card ID:** ADMIN-1702  
**Epic:** ADMIN-1700 — Administration  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement subscription and plan management.

**Scope:**
- Create and edit plans
- Configure plan features and limits
- View subscription revenue
- Handle subscription changes
- Process refunds
- Generate subscription reports

**Files / Modules Affected:**
- `app/admin/routes.py`
- `app/admin/services.py`
- `app/tenants/models.py`
- `app/templates/pages/admin/subscriptions.html`

**Acceptance Criteria:**
- [ ] Plans can be created and edited
- [ ] Features and limits are configurable
- [ ] Revenue is tracked
- [ ] Subscription changes are handled
- [ ] Refunds can be processed
- [ ] Reports are generated

**Test Requirements:**
- [ ] Test plan CRUD
- [ ] Test feature configuration
- [ ] Test revenue tracking
- [ ] Test refund processing

**Dependencies:**
- ADMIN-1701, BILLING-1800

**Estimated Effort:** 6 hours

---

#### ADMIN-1703: Audit Logs

**Card ID:** ADMIN-1703  
**Epic:** ADMIN-1700 — Administration  
**Priority:** High  
**Status:** Backlog

**Goal:**  
Implement comprehensive audit logging.

**Scope:**
- Log all financial data changes (who, what, when, old value, new value)
- Log all authentication events (login, logout, failed attempts)
- Log all AI interactions (prompt, response, cost)
- Log all admin actions
- Implement audit log search and filter
- Implement audit log export
- Retain logs for required period (configurable)

**Files / Modules Affected:**
- `app/admin/models.py` (AuditLog)
- `app/admin/services.py`
- `app/admin/routes.py`
- `app/core/middleware.py` (logging)

**Acceptance Criteria:**
- [ ] Financial changes are logged
- [ ] Auth events are logged
- [ ] AI interactions are logged
- [ ] Admin actions are logged
- [ ] Logs are searchable
- [ ] Logs are exportable
- [ ] Retention is configurable

**Test Requirements:**
- [ ] Test financial change logging
- [ ] Test auth event logging
- [ ] Test AI interaction logging
- [ ] Test search
- [ ] Test export

**Dependencies:**
- ADMIN-1700

**Estimated Effort:** 8 hours

---

#### ADMIN-1704: System Monitoring

**Card ID:** ADMIN-1704  
**Epic:** ADMIN-1700 — Administration  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement system monitoring and alerting.

**Scope:**
- Monitor database health (connections, slow queries)
- Monitor Redis health (memory, connections)
- Monitor Celery queue health (backlog, failed tasks)
- Monitor application errors (Sentry integration)
- Monitor API response times
- Alert on anomalies
- Create system status page

**Files / Modules Affected:**
- `app/admin/services.py`
- `app/admin/routes.py`
- `app/templates/pages/admin/monitoring.html`
- Monitoring integrations

**Acceptance Criteria:**
- [ ] Database health is monitored
- [ ] Redis health is monitored
- [ ] Celery queue is monitored
- [ ] Errors are tracked
- [ ] API response times are tracked
- [ ] Alerts are sent on anomalies
- [ ] Status page is available

**Test Requirements:**
- [ ] Test monitoring data collection
- [ ] Test alerting thresholds
- [ ] Test status page

**Dependencies:**
- ADMIN-1700

**Estimated Effort:** 6 hours

---

#### BILLING-1800: Stripe Integration

**Card ID:** BILLING-1800  
**Epic:** BILLING-1800 — Billing  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement Stripe payment integration.

**Scope:**
- Setup Stripe account and API keys
- Create Stripe products and prices for plans
- Implement checkout session creation
- Handle webhook events (payment success, failure, subscription update)
- Store Stripe customer ID and subscription ID
- Implement payment method management
- Handle trial periods

**Files / Modules Affected:**
- `app/admin/services.py` (billing)
- `app/tenants/models.py` (Stripe fields)
- `app/tenants/routes.py` (billing endpoints)
- Webhook handlers

**Acceptance Criteria:**
- [ ] Stripe is configured
- [ ] Products and prices are created
- [ ] Checkout works
- [ ] Webhooks are handled
- [ ] Customer data is stored
- [ ] Payment methods can be managed
- [ ] Trials are supported

**Test Requirements:**
- [ ] Test checkout flow
- [ ] Test webhook handling
- [ ] Test payment method management
- [ ] Test trial handling

**Dependencies:**
- SAAS-202

**Estimated Effort:** 10 hours

---

#### BILLING-1801: Invoice Generation

**Card ID:** BILLING-1801  
**Epic:** BILLING-1800 — Billing  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement invoice generation and delivery.

**Scope:**
- Generate invoice on payment
- Include: plan name, period, amount, tax (if applicable)
- Support OMR currency formatting
- Generate PDF invoice
- Email invoice to billing contact
- Store invoice history
- Allow invoice download

**Files / Modules Affected:**
- `app/admin/services.py`
- `app/admin/models.py` (Invoice)
- `app/templates/emails/invoice.html`
- PDF generation library

**Acceptance Criteria:**
- [ ] Invoices are generated on payment
- [ ] Content is accurate
- [ ] OMR formatting is correct
- [ ] PDF is generated
- [ ] Invoice is emailed
- [ ] History is stored
- [ ] Download works

**Test Requirements:**
- [ ] Test invoice generation
- [ ] Test PDF creation
- [ ] Test email delivery
- [ ] Test download

**Dependencies:**
- BILLING-1800

**Estimated Effort:** 6 hours

---

#### BILLING-1802: Payment Processing

**Card ID:** BILLING-1802  
**Epic:** BILLING-1800 — Billing  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement payment processing and retry logic.

**Scope:**
- Process one-time payments
- Process recurring subscription payments
- Handle payment failures (retry logic)
- Handle expired cards
- Send payment failure notifications
- Implement dunning (grace period, suspension)
- Update tenant status based on payment

**Files / Modules Affected:**
- `app/admin/services.py`
- `app/tenants/services.py`
- `app/notifications/services.py`
- Webhook handlers

**Acceptance Criteria:**
- [ ] One-time payments work
- [ ] Recurring payments work
- [ ] Failed payments are retried
- [ ] Expired cards are handled
- [ ] Failure notifications are sent
- [ ] Dunning process works
- [ ] Tenant status updates correctly

**Test Requirements:**
- [ ] Test payment processing
- [ ] Test retry logic
- [ ] Test failure handling
- [ ] Test dunning
- [ ] Test status updates

**Dependencies:**
- BILLING-1800

**Estimated Effort:** 8 hours

---

#### BILLING-1803: Billing History

**Card ID:** BILLING-1803  
**Epic:** BILLING-1800 — Billing  
**Priority:** Low  
**Status:** Backlog

**Goal:**  
Implement billing history for tenants.

**Scope:**
- Show payment history
- Show invoice history
- Show subscription changes
- Show refund history
- Allow download of all invoices
- Show upcoming payments

**Files / Modules Affected:**
- `app/tenants/routes.py`
- `app/templates/pages/tenants/billing.html`
- `app/admin/services.py`

**Acceptance Criteria:**
- [ ] Payment history is shown
- [ ] Invoice history is shown
- [ ] Subscription changes are tracked
- [ ] Refunds are shown
- [ ] Invoices can be downloaded
- [ ] Upcoming payments are shown

**Test Requirements:**
- [ ] Test history display
- [ ] Test download
- [ ] Test upcoming payments

**Dependencies:**
- BILLING-1801

**Estimated Effort:** 4 hours

---

### Phase 5: Scale, API, Bank Feeds, Mobile

---

#### API-1900: REST API v1

**Card ID:** API-1900  
**Epic:** API-1900 — API  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Expose all features as a public REST API.

**Scope:**
- Create API routes under /api/v1/
- Implement all CRUD operations for major entities
- Implement API authentication (API keys)
- Implement rate limiting
- Implement request/response logging
- Document all endpoints
- Version API (v1)

**Files / Modules Affected:**
- `app/api/routes.py`
- `app/api/schemas.py`
- `app/api/services.py`
- `app/api/permissions.py`

**Acceptance Criteria:**
- [ ] All major entities have API endpoints
- [ ] CRUD operations work
- [ ] API key authentication works
- [ ] Rate limiting is enforced
- [ ] Requests are logged
- [ ] Documentation is complete
- [ ] Versioning is implemented

**Test Requirements:**
- [ ] Test all endpoints
- [ ] Test authentication
- [ ] Test rate limiting
- [ ] Test error responses

**Dependencies:**
- All previous feature cards

**Estimated Effort:** 12 hours

---

#### API-1901: OpenAPI Documentation

**Card ID:** API-1901  
**Epic:** API-1900 — API  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Auto-generate and publish OpenAPI documentation.

**Scope:**
- Ensure all API endpoints have proper docstrings
- Configure FastAPI OpenAPI schema
- Customize documentation UI
- Add example requests and responses
- Publish /docs and /redoc endpoints
- Generate static documentation (optional)

**Files / Modules Affected:**
- `app/main.py` (OpenAPI config)
- All route files (docstrings)

**Acceptance Criteria:**
- [ ] /docs endpoint works
- [ ] /redoc endpoint works
- [ ] All endpoints are documented
- [ ] Examples are provided
- [ ] Documentation is accurate
- [ ] Static docs are generated (optional)

**Test Requirements:**
- [ ] Test /docs endpoint
- [ ] Test /redoc endpoint
- [ ] Verify documentation accuracy

**Dependencies:**
- API-1900

**Estimated Effort:** 4 hours

---

#### API-1902: API Key Management

**Card ID:** API-1902  
**Epic:** API-1900 — API  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement API key generation and management.

**Scope:**
- Generate secure API keys
- Associate keys with tenants/users
- Implement API key authentication middleware
- Allow key revocation
- Allow key rotation
- Show API key usage
- Implement key scopes (read-only, read-write)

**Files / Modules Affected:**
- `app/api/models.py` (ApiKey)
- `app/api/services.py`
- `app/api/routes.py`
- `app/api/permissions.py`

**Acceptance Criteria:**
- [ ] Keys can be generated
- [ ] Keys are associated with users/tenants
- [ ] Key authentication works
- [ ] Keys can be revoked
- [ ] Keys can be rotated
- [ ] Usage is tracked
- [ ] Scopes are enforced

**Test Requirements:**
- [ ] Test key generation
- [ ] Test authentication
- [ ] Test revocation
- [ ] Test rotation
- [ ] Test scopes

**Dependencies:**
- API-1900

**Estimated Effort:** 6 hours

---

#### API-1903: Webhooks

**Card ID:** API-1903  
**Epic:** API-1900 — API  
**Priority:** Low  
**Status:** Backlog

**Goal:**  
Implement webhook system for event notifications.

**Scope:**
- Allow tenants to register webhook URLs
- Define webhook event types (transaction created, bill due, etc.)
- Implement webhook delivery with retry
- Implement webhook signature verification
- Show webhook delivery history
- Allow webhook testing

**Files / Modules Affected:**
- `app/api/models.py` (Webhook)
- `app/api/services.py`
- `app/api/routes.py`
- `app/api/tasks.py`

**Acceptance Criteria:**
- [ ] Webhooks can be registered
- [ ] Events are defined
- [ ] Delivery works with retry
- [ ] Signatures are verified
- [ ] History is shown
- [ ] Testing works

**Test Requirements:**
- [ ] Test registration
- [ ] Test delivery
- [ ] Test retry
- [ ] Test signature verification
- [ ] Test history

**Dependencies:**
- API-1900

**Estimated Effort:** 8 hours

---

#### REP-2000: Income Statement Report

**Card ID:** REP-2000  
**Epic:** REP-2000 — Reports  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Generate Income Statement (Profit & Loss) report.

**Scope:**
- Calculate total income for period
- Calculate total expenses for period
- Calculate net income (income - expenses)
- Show income and expense breakdown by category
- Support date range selection
- Export to PDF and Excel
- Show comparison to previous period

**Files / Modules Affected:**
- `app/reports/generators/income_statement.py`
- `app/reports/services.py`
- `app/reports/routes.py`
- `app/templates/pages/reports/income_statement.html`

**Acceptance Criteria:**
- [ ] Income is calculated correctly
- [ ] Expenses are calculated correctly
- [ ] Net income is accurate
- [ ] Breakdown by category works
- [ ] Date range selection works
- [ ] Export to PDF and Excel works
- [ ] Comparison works

**Test Requirements:**
- [ ] Test calculation accuracy
- [ ] Test breakdown
- [ ] Test export
- [ ] Test comparison

**Dependencies:**
- TRX-600, ACC-500

**Estimated Effort:** 6 hours

---

#### REP-2001: Balance Sheet Report

**Card ID:** REP-2001  
**Epic:** REP-2000 — Reports  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Generate Balance Sheet report.

**Scope:**
- Calculate total assets
- Calculate total liabilities
- Calculate equity (assets - liabilities)
- Show asset and liability breakdown
- Support date selection (as of date)
- Export to PDF and Excel
- Show comparison to previous period

**Files / Modules Affected:**
- `app/reports/generators/balance_sheet.py`
- `app/reports/services.py`
- `app/reports/routes.py`
- `app/templates/pages/reports/balance_sheet.html`

**Acceptance Criteria:**
- [ ] Assets are calculated correctly
- [ ] Liabilities are calculated correctly
- [ ] Equity is accurate
- [ ] Breakdown works
- [ ] Date selection works
- [ ] Export works
- [ ] Comparison works

**Test Requirements:**
- [ ] Test calculation accuracy
- [ ] Test breakdown
- [ ] Test export
- [ ] Test comparison

**Dependencies:**
- ACC-500

**Estimated Effort:** 6 hours

---

#### REP-2002: Cash Flow Report

**Card ID:** REP-2002  
**Epic:** REP-2000 — Reports  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Generate Cash Flow report.

**Scope:**
- Calculate operating cash flow
- Calculate investing cash flow
- Calculate financing cash flow
- Calculate net cash flow
- Show monthly cash flow trend
- Support date range selection
- Export to PDF and Excel

**Files / Modules Affected:**
- `app/reports/generators/cash_flow.py`
- `app/reports/services.py`
- `app/reports/routes.py`
- `app/templates/pages/reports/cash_flow.html`

**Acceptance Criteria:**
- [ ] Operating cash flow is calculated
- [ ] Investing cash flow is calculated
- [ ] Financing cash flow is calculated
- [ ] Net cash flow is accurate
- [ ] Monthly trend is shown
- [ ] Date range works
- [ ] Export works

**Test Requirements:**
- [ ] Test calculation accuracy
- [ ] Test trend
- [ ] Test export

**Dependencies:**
- TRX-600, ACC-500

**Estimated Effort:** 6 hours

---

#### REP-2003: Net Worth Report

**Card ID:** REP-2003  
**Epic:** REP-2000 — Reports  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Generate Net Worth report with history.

**Scope:**
- Calculate current net worth
- Show net worth history over time
- Show asset and liability composition
- Show net worth change (amount and percentage)
- Support date range selection
- Export to PDF and Excel
- Show net worth goal progress

**Files / Modules Affected:**
- `app/reports/generators/net_worth.py`
- `app/reports/services.py`
- `app/reports/routes.py`
- `app/templates/pages/reports/net_worth.html`

**Acceptance Criteria:**
- [ ] Current net worth is calculated
- [ ] History is shown
- [ ] Composition is shown
- [ ] Change is calculated
- [ ] Date range works
- [ ] Export works
- [ ] Goal progress is shown

**Test Requirements:**
- [ ] Test calculation accuracy
- [ ] Test history
- [ ] Test export

**Dependencies:**
- ACC-500

**Estimated Effort:** 6 hours

---

#### REP-2004: Expense Analysis Report

**Card ID:** REP-2004  
**Epic:** REP-2000 — Reports  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Generate detailed expense analysis report.

**Scope:**
- Show expense breakdown by category
- Show expense trends over time
- Show top expenses
- Show expense comparison to budget
- Identify highest growth categories
- Support date range selection
- Export to PDF and Excel

**Files / Modules Affected:**
- `app/reports/generators/expense_analysis.py`
- `app/reports/services.py`
- `app/reports/routes.py`
- `app/templates/pages/reports/expense_analysis.html`

**Acceptance Criteria:**
- [ ] Breakdown by category works
- [ ] Trends are shown
- [ ] Top expenses are listed
- [ ] Budget comparison works
- [ ] Growth categories are identified
- [ ] Date range works
- [ ] Export works

**Test Requirements:**
- [ ] Test breakdown accuracy
- [ ] Test trends
- [ ] Test comparison
- [ ] Test export

**Dependencies:**
- TRX-600, BDG-1000

**Estimated Effort:** 6 hours

---

#### REP-2005: Category Trends Report

**Card ID:** REP-2005  
**Epic:** REP-2000 — Reports  
**Priority:** Low  
**Status:** Backlog

**Goal:**  
Generate category trends report showing spending patterns over time.

**Scope:**
- Show spending per category over months
- Show category growth/decline rates
- Compare categories
- Show seasonal patterns
- Support date range selection
- Export to PDF and Excel

**Files / Modules Affected:**
- `app/reports/generators/category_trends.py`
- `app/reports/services.py`
- `app/reports/routes.py`

**Acceptance Criteria:**
- [ ] Monthly spending per category is shown
- [ ] Growth/decline rates are calculated
- [ ] Category comparison works
- [ ] Seasonal patterns are shown
- [ ] Date range works
- [ ] Export works

**Test Requirements:**
- [ ] Test monthly data
- [ ] Test growth rates
- [ ] Test comparison
- [ ] Test export

**Dependencies:**
- REP-2004

**Estimated Effort:** 4 hours

---

#### DOC-2100: Document Upload

**Card ID:** DOC-2100  
**Epic:** DOC-2100 — Document Management  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement document upload and storage.

**Scope:**
- Create document model (name, type, size, path, category)
- Implement file upload endpoint
- Store files securely (encrypted at rest)
- Support images, PDFs, and common document types
- Implement file size limits (10MB per file, 100MB per tenant)
- Create document list UI
- Allow document download

**Files / Modules Affected:**
- `app/documents/models.py` (Document)
- `app/documents/schemas.py`
- `app/documents/services.py`
- `app/documents/routes.py`
- Storage configuration

**Acceptance Criteria:**
- [ ] Files can be uploaded
- [ ] Types are validated
- [ ] Files are stored securely
- [ ] Size limits are enforced
- [ ] Documents are listed
- [ ] Download works
- [ ] Tenant quota is enforced

**Test Requirements:**
- [ ] Test upload
- [ ] Test validation
- [ ] Test size limits
- [ ] Test download
- [ ] Test quota

**Dependencies:**
- TRX-600

**Estimated Effort:** 6 hours

---

#### DOC-2101: OCR for Receipts

**Card ID:** DOC-2101  
**Epic:** DOC-2100 — Document Management  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement OCR for extracting text from receipt images.

**Scope:**
- Integrate OCR library (Tesseract or cloud API)
- Extract text from receipt images
- Parse extracted text for: date, amount, merchant, items
- Show extracted data for review
- Allow user to correct OCR errors
- Store extracted data with document

**Files / Modules Affected:**
- `app/documents/services.py`
- `app/documents/tasks.py`
- OCR library integration

**Acceptance Criteria:**
- [ ] Text is extracted from images
- [ ] Date is parsed
- [ ] Amount is parsed
- [ ] Merchant is parsed
- [ ] Extracted data is shown for review
- [ ] User can correct errors
- [ ] Data is stored with document

**Test Requirements:**
- [ ] Test OCR accuracy
- [ ] Test parsing
- [ ] Test correction flow
- [ ] Test storage

**Dependencies:**
- DOC-2100

**Estimated Effort:** 8 hours

---

#### DOC-2102: AI Receipt Reading

**Card ID:** DOC-2102  
**Epic:** DOC-2100 — Document Management  
**Priority:** Low  
**Status:** Backlog

**Goal:**  
Use AI to intelligently parse receipts and suggest transactions.

**Scope:**
- Send receipt image to AI for parsing
- Extract structured data: date, amount, merchant, category, items
- Suggest transaction creation from receipt
- Allow one-click transaction creation
- Learn from user corrections
- Handle multiple currencies

**Files / Modules Affected:**
- `app/documents/services.py`
- `app/ai_cfo/llm/client.py`
- `app/ai_cfo/llm/prompts.py`

**Acceptance Criteria:**
- [ ] AI parses receipt accurately
- [ ] Structured data is extracted
- [ ] Transaction is suggested
- [ ] One-click creation works
- [ ] Corrections improve future parsing
- [ ] Multiple currencies are handled

**Test Requirements:**
- [ ] Test parsing accuracy
- [ ] Test suggestion quality
- [ ] Test one-click creation
- [ ] Test learning

**Dependencies:**
- DOC-2101, AI-1201

**Estimated Effort:** 8 hours

---

#### DOC-2103: Document Categories

**Card ID:** DOC-2103  
**Epic:** DOC-2100 — Document Management  
**Priority:** Low  
**Status:** Backlog

**Goal:**  
Implement document categorization and organization.

**Scope:**
- Create document category model
- Support categories: receipt, invoice, statement, contract, other
- Auto-categorize based on content (AI or rules)
- Allow manual categorization
- Filter documents by category
- Search documents by content (OCR text)

**Files / Modules Affected:**
- `app/documents/models.py` (DocumentCategory)
- `app/documents/services.py`
- `app/documents/routes.py`

**Acceptance Criteria:**
- [ ] Categories are defined
- [ ] Auto-categorization works
- [ ] Manual categorization works
- [ ] Filter by category works
- [ ] Search by content works

**Test Requirements:**
- [ ] Test auto-categorization
- [ ] Test manual categorization
- [ ] Test filter
- [ ] Test search

**Dependencies:**
- DOC-2100

**Estimated Effort:** 4 hours

---

#### MOB-2200: Responsive UI Improvements

**Card ID:** MOB-2200  
**Epic:** MOB-2200 — Mobile  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Improve responsive design for mobile devices.

**Scope:**
- Audit all pages for mobile usability
- Fix layout issues on small screens
- Optimize touch targets (min 44px)
- Implement mobile-optimized navigation
- Test on iOS and Android browsers
- Optimize form inputs for mobile
- Implement pull-to-refresh where appropriate

**Files / Modules Affected:**
- `app/templates/` (all pages)
- `app/static/css/custom.css`
- `app/static/js/mobile.js`

**Acceptance Criteria:**
- [ ] All pages are usable on mobile
- [ ] Layout issues are fixed
- [ ] Touch targets are optimized
- [ ] Navigation works on mobile
- [ ] Forms are mobile-friendly
- [ ] iOS and Android are tested

**Test Requirements:**
- [ ] Test on iOS Safari
- [ ] Test on Android Chrome
- [ ] Test navigation
- [ ] Test forms
- [ ] Test touch targets

**Dependencies:**
- All UI cards

**Estimated Effort:** 10 hours

---

#### MOB-2201: PWA Support

**Card ID:** MOB-2201  
**Epic:** MOB-2200 — Mobile  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement Progressive Web App (PWA) support.

**Scope:**
- Create web app manifest
- Implement service worker for caching
- Add "Add to Home Screen" support
- Implement offline page
- Cache critical assets
- Handle offline form submission (queue for sync)
- Implement app icons

**Files / Modules Affected:**
- `app/static/manifest.json`
- `app/static/js/service-worker.js`
- `app/templates/base.html` (manifest link)
- App icons

**Acceptance Criteria:**
- [ ] Manifest is valid
- [ ] Service worker registers
- [ ] "Add to Home Screen" works
- [ ] Offline page works
- [ ] Critical assets are cached
- [ ] Form queue works offline
- [ ] Icons are provided

**Test Requirements:**
- [ ] Test manifest
- [ ] Test service worker
- [ ] Test offline page
- [ ] Test caching
- [ ] Test form queue

**Dependencies:**
- MOB-2200

**Estimated Effort:** 8 hours

---

#### MOB-2202: Offline Support

**Card ID:** MOB-2202  
**Epic:** MOB-2200 — Mobile  
**Priority:** Low  
**Status:** Backlog

**Goal:**  
Implement offline data access and synchronization.

**Scope:**
- Cache recent transactions for offline viewing
- Allow offline transaction entry (queue for sync)
- Sync queued data when connection restored
- Handle sync conflicts
- Show offline indicator
- Cache dashboard data

**Files / Modules Affected:**
- `app/static/js/offline.js`
- `app/static/js/service-worker.js`
- `app/templates/base.html` (offline indicator)

**Acceptance Criteria:**
- [ ] Recent transactions are cached
- [ ] Offline entry works
- [ ] Sync works when online
- [ ] Conflicts are handled
- [ ] Offline indicator is shown
- [ ] Dashboard data is cached

**Test Requirements:**
- [ ] Test offline viewing
- [ ] Test offline entry
- [ ] Test sync
- [ ] Test conflict handling
- [ ] Test indicator

**Dependencies:**
- MOB-2201

**Estimated Effort:** 10 hours

---

#### FEED-2300: Bank Feed Architecture

**Card ID:** FEED-2300  
**Epic:** FEED-2300 — Bank Feeds  
**Priority:** Low  
**Status:** Backlog

**Goal:**  
Design the bank feed integration architecture.

**Scope:**
- Research bank API availability in Oman/Middle East
- Design feed connector interface
- Implement feed polling mechanism
- Design transaction matching algorithm
- Implement feed status tracking
- Document feed security requirements

**Files / Modules Affected:**
- `docs/architecture/bank-feeds.md`
- `app/imports/parsers/bank_feed_parser.py` (stub)

**Acceptance Criteria:**
- [ ] Architecture is documented
- [ ] Connector interface is defined
- [ ] Polling mechanism is designed
- [ ] Matching algorithm is defined
- [ ] Status tracking is designed
- [ ] Security requirements are documented

**Test Requirements:**
- N/A (architecture)

**Dependencies:**
- None

**Estimated Effort:** 6 hours

---

#### FEED-2301: OFX/QIF Import

**Card ID:** FEED-2301  
**Epic:** FEED-2300 — Bank Feeds  
**Priority:** Low  
**Status:** Backlog

**Goal:**  
Implement OFX and QIF file import.

**Scope:**
- Parse OFX files (bank statement format)
- Parse QIF files (Quicken format)
- Extract transactions, accounts, balances
- Map to internal transaction model
- Handle duplicate detection
- Support import job workflow

**Files / Modules Affected:**
- `app/imports/parsers/ofx_parser.py`
- `app/imports/parsers/qif_parser.py`
- `app/imports/services.py`

**Acceptance Criteria:**
- [ ] OFX files are parsed
- [ ] QIF files are parsed
- [ ] Transactions are extracted
- [ ] Accounts and balances are extracted
- [ ] Mapping to internal model works
- [ ] Duplicate detection works

**Test Requirements:**
- [ ] Test OFX parsing
- [ ] Test QIF parsing
- [ ] Test extraction
- [ ] Test mapping
- [ ] Test duplicates

**Dependencies:**
- IMP-700

**Estimated Effort:** 6 hours

---

#### FEED-2302: PDF Statement Parsing

**Card ID:** FEED-2302  
**Epic:** FEED-2300 — Bank Feeds  
**Priority:** Low  
**Status:** Backlog

**Goal:**  
Implement PDF bank statement parsing.

**Scope:**
- Extract text from PDF statements
- Parse transaction data from text
- Handle multiple bank formats
- Implement table extraction
- Support scanned PDFs (OCR)
- Map to internal transaction model

**Files / Modules Affected:**
- `app/imports/parsers/pdf_parser.py`
- `app/imports/services.py`
- PDF/OCR libraries

**Acceptance Criteria:**
- [ ] PDF text is extracted
- [ ] Transactions are parsed
- [ ] Multiple bank formats are supported
- [ ] Table extraction works
- [ ] Scanned PDFs are handled
- [ ] Mapping to internal model works

**Test Requirements:**
- [ ] Test PDF extraction
- [ ] Test transaction parsing
- [ ] Test bank formats
- [ ] Test scanned PDFs

**Dependencies:**
- DOC-2101

**Estimated Effort:** 8 hours

---

#### FEED-2303: Bank API Integration

**Card ID:** FEED-2303  
**Epic:** FEED-2300 — Bank Feeds  
**Priority:** Low  
**Status:** Backlog

**Goal:**  
Implement direct bank API integration (when available).

**Scope:**
- Research available bank APIs in target markets
- Implement OAuth connection flow
- Implement transaction sync
- Implement balance sync
- Handle API errors and rate limits
- Implement connection health monitoring
- Support multiple banks

**Files / Modules Affected:**
- `app/imports/parsers/bank_feed_parser.py`
- `app/imports/services.py`
- `app/imports/routes.py`
- OAuth integration

**Acceptance Criteria:**
- [ ] OAuth connection works
- [ ] Transactions sync
- [ ] Balances sync
- [ ] Errors are handled
- [ ] Rate limits are respected
- [ ] Health is monitored
- [ ] Multiple banks are supported

**Test Requirements:**
- [ ] Test OAuth flow
- [ ] Test transaction sync
- [ ] Test balance sync
- [ ] Test error handling
- [ ] Test rate limiting

**Dependencies:**
- FEED-2300

**Estimated Effort:** 12 hours

---

#### SCALE-2400: Performance Optimization

**Card ID:** SCALE-2400  
**Epic:** SCALE-2400 — Scale  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Optimize application performance for scale.

**Scope:**
- Profile slow queries and endpoints
- Optimize database queries (N+1, missing indexes)
- Implement query result caching
- Optimize template rendering
- Implement connection pooling tuning
- Optimize static asset delivery
- Implement database query logging

**Files / Modules Affected:**
- All service files
- `app/core/db.py`
- `app/core/cache.py`
- Database indexes

**Acceptance Criteria:**
- [ ] Slow queries are identified and fixed
- [ ] N+1 queries are eliminated
- [ ] Caching is implemented
- [ ] Template rendering is optimized
- [ ] Connection pooling is tuned
- [ ] Static assets are optimized
- [ ] Query logging works

**Test Requirements:**
- [ ] Test query performance
- [ ] Test caching
- [ ] Test endpoint response times
- [ ] Benchmark before/after

**Dependencies:**
- All previous cards

**Estimated Effort:** 10 hours

---

#### SCALE-2401: Caching Layer

**Card ID:** SCALE-2401  
**Epic:** SCALE-2400 — Scale  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement comprehensive caching strategy.

**Scope:**
- Cache frequently accessed data (accounts, categories, settings)
- Cache computed data (dashboard widgets, reports)
- Implement cache invalidation on data changes
- Use Redis for distributed caching
- Implement cache warming for common queries
- Monitor cache hit rates
- Implement cache fallback (serve stale if cache down)

**Files / Modules Affected:**
- `app/core/cache.py`
- All service files
- Redis configuration

**Acceptance Criteria:**
- [ ] Frequently accessed data is cached
- [ ] Computed data is cached
- [ ] Invalidation works on changes
- [ ] Redis is used for caching
- [ ] Cache warming works
- [ ] Hit rates are monitored
- [ ] Fallback works

**Test Requirements:**
- [ ] Test cache storage
- [ ] Test invalidation
- [ ] Test warming
- [ ] Test fallback
- [ ] Test hit rates

**Dependencies:**
- SCALE-2400

**Estimated Effort:** 8 hours

---

#### SCALE-2402: Database Indexing Strategy

**Card ID:** SCALE-2402  
**Epic:** SCALE-2400 — Scale  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement optimal database indexing strategy.

**Scope:**
- Identify slow queries from logs
- Add indexes on frequently queried columns
- Add composite indexes for common filter combinations
- Add indexes for sorting
- Monitor index usage
- Remove unused indexes
- Document indexing strategy

**Files / Modules Affected:**
- Alembic migrations (index additions)
- `docs/architecture/indexing.md`

**Acceptance Criteria:**
- [ ] Slow queries are identified
- [ ] Indexes are added on queried columns
- [ ] Composite indexes are added
- [ ] Sorting indexes are added
- [ ] Usage is monitored
- [ ] Unused indexes are removed
- [ ] Strategy is documented

**Test Requirements:**
- [ ] Test query performance with indexes
- [ ] Test index usage
- [ ] Benchmark improvements

**Dependencies:**
- SCALE-2400

**Estimated Effort:** 6 hours

---

#### SCALE-2403: Background Job Optimization

**Card ID:** SCALE-2403  
**Epic:** SCALE-2400 — Scale  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Optimize Celery background job processing.

**Scope:**
- Implement job priority queues
- Implement job retry with exponential backoff
- Implement dead letter queue for failed jobs
- Monitor job processing times
- Optimize job batching
- Implement job concurrency limits
- Add job monitoring dashboard

**Files / Modules Affected:**
- `app/tasks/celery_app.py`
- `app/tasks/` (all task files)
- Monitoring dashboard

**Acceptance Criteria:**
- [ ] Priority queues work
- [ ] Retry with backoff works
- [ ] Dead letter queue works
- [ ] Processing times are monitored
- [ ] Batching is optimized
- [ ] Concurrency limits work
- [ ] Dashboard exists

**Test Requirements:**
- [ ] Test priority queues
- [ ] Test retry logic
- [ ] Test dead letter queue
- [ ] Test batching
- [ ] Test concurrency

**Dependencies:**
- SCALE-2400

**Estimated Effort:** 6 hours

---

#### SCALE-2404: Docker Containerization

**Card ID:** SCALE-2404  
**Epic:** SCALE-2400 — Scale  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Containerize the application with Docker.

**Scope:**
- Create Dockerfile for application
- Create docker-compose.yml for local development
- Create docker-compose.prod.yml for production
- Configure multi-stage build
- Setup health checks
- Configure environment variables for Docker
- Document Docker usage

**Files / Modules Affected:**
- `docker/Dockerfile`
- `docker/docker-compose.yml`
- `docker/docker-compose.prod.yml`
- `docker/nginx.conf`
- `docs/dev/docker.md`

**Acceptance Criteria:**
- [ ] Dockerfile builds successfully
- [ ] docker-compose works for local dev
- [ ] Production compose works
- [ ] Multi-stage build is optimized
- [ ] Health checks work
- [ ] Environment variables are configured
- [ ] Documentation is complete

**Test Requirements:**
- [ ] Test Docker build
- [ ] Test local compose
- [ ] Test production compose
- [ ] Test health checks

**Dependencies:**
- All previous cards

**Estimated Effort:** 8 hours

---

#### SCALE-2405: CI/CD Pipeline

**Card ID:** SCALE-2405  
**Epic:** SCALE-2400 — Scale  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement CI/CD pipeline with GitHub Actions.

**Scope:**
- Create GitHub Actions workflow for testing
- Create workflow for linting and formatting
- Create workflow for security scanning
- Create workflow for deployment
- Implement automated testing on PR
- Implement branch protection rules
- Document CI/CD process

**Files / Modules Affected:**
- `.github/workflows/test.yml`
- `.github/workflows/lint.yml`
- `.github/workflows/security.yml`
- `.github/workflows/deploy.yml`
- `docs/dev/ci-cd.md`

**Acceptance Criteria:**
- [ ] Test workflow runs on PR
- [ ] Lint workflow runs on PR
- [ ] Security scan runs on PR
- [ ] Deploy workflow works
- [ ] Branch protection is configured
- [ ] Documentation is complete

**Test Requirements:**
- [ ] Test workflow execution
- [ ] Test linting
- [ ] Test security scan
- [ ] Test deploy

**Dependencies:**
- SCALE-2404

**Estimated Effort:** 8 hours

---

#### SCALE-2406: Monitoring and Alerting

**Card ID:** SCALE-2406  
**Epic:** SCALE-2400 — Scale  
**Priority:** Medium  
**Status:** Backlog

**Goal:**  
Implement production monitoring and alerting.

**Scope:**
- Integrate application monitoring (Sentry, DataDog, or Prometheus)
- Setup error alerting
- Setup performance alerting
- Setup uptime monitoring
- Create runbooks for common issues
- Implement log aggregation
- Create monitoring dashboards

**Files / Modules Affected:**
- Monitoring integrations
- `docs/ops/monitoring.md`
- `docs/ops/runbooks.md`

**Acceptance Criteria:**
- [ ] Monitoring is integrated
- [ ] Error alerts work
- [ ] Performance alerts work
- [ ] Uptime monitoring works
- [ ] Runbooks are documented
- [ ] Logs are aggregated
- [ ] Dashboards exist

**Test Requirements:**
- [ ] Test monitoring integration
- [ ] Test alerts
- [ ] Test dashboards

**Dependencies:**
- SCALE-2404

**Estimated Effort:** 8 hours

---

## 18. Migration from Old Plan to New Plan

### Concept Mapping

| Old Concept | New Concept | Notes |
|-------------|-------------|-------|
| AI Chat | AI CFO Interface + Financial Digital Twin + Recommendation Engine | Not just chat — full intelligence system |
| AI Health Score | Financial Health Engine + Digital Twin | Part of broader Digital Twin |
| Family Member Invitation | Family Finance Product Module | Full module with roles, permissions, shared/private accounts |
| Chart of Accounts as main menu | Hidden Accounting Engine + Accountant View | Still exists, but hidden from normal users |
| Flask app factory | FastAPI modular monolith | New framework, same modular spirit |
| Manual Journal Entries | Auto-generated behind transactions | Users don't see unless in accountant view |
| Bank Feeds | CSV/Excel/SMS Import first, bank feeds later | Phased approach for Oman market |
| AI Widget | AI-Centric Dashboard v2 | Dashboard rebuilt around AI insights |
| Budget vs Actual | Budget vs Actual + AI Budget Advisor | AI enhances traditional budgeting |
| Reports | Reports + AI Monthly Review | AI generates narrative reviews |
| Notifications | Smart Notifications + Proactive Alerts | AI-driven, not just scheduled |
| Document Management | Documents + OCR + AI Receipt Reading | AI enhances document processing |
| Import/Export | Import Strategy (phased) + Export | Oman-focused import strategy |
| Admin Portal | Super Admin + Tenant Admin + Audit Logs | Enhanced with monitoring |
| API | REST API v1 + OpenAPI + Webhooks | Full API-first design |
| Mobile | Responsive UI + PWA + Offline Support | Progressive enhancement |

### Data Model Changes

| Old Model | New Model | Changes |
|-----------|-----------|---------|
| User | User + UserProfile | Separated auth and profile |
| Tenant | Tenant + Plan + Subscription | Added billing context |
| Transaction | Transaction + JournalEntry + JournalEntryLine | Double-entry now explicit |
| Account | Account (with hierarchy) | Added parent-child, codes |
| Category | Category (with hierarchy) | Added hierarchy, icons |
| Budget | Budget + BudgetCategory | More granular tracking |
| Goal | Goal + GoalContribution | Contribution tracking added |
| Loan | LoanAccount + LoanPayment | Full loan management |
| AIConversation | AIConversation + AIInsight + AIDigitalTwin | Much richer AI model |
| Family | Family + FamilyMember + FamilyAccountAccess | Full access control |

### Technology Changes

| Aspect | Old | New |
|--------|-----|-----|
| Framework | Flask | FastAPI |
| Validation | Flask-WTF / Marshmallow | Pydantic |
| Async | Not supported natively | Native async/await |
| Documentation | Manual | Auto-generated OpenAPI |
| Dependency Injection | Manual | Built-in Depends() |
| API Design | Ad-hoc | API-first, versioned |
| Frontend | Server-rendered + minimal JS | Server-rendered + HTMX |
| Background Jobs | Celery | Celery (same) |
| Architecture | Monolithic (implied) | Modular monolith (explicit) |

---

## 19. Risks and Mitigations

### Risk Register

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| 1 | **AI Cost Overrun** | High | Medium | Implement strict token tracking, use cheaper models for simple queries, set per-tenant limits, implement fallback to rule-based |
| 2 | **Tenant Data Leak** | Critical | Low | PostgreSQL RLS, application-level filtering, encryption at rest, regular security audits, penetration testing |
| 3 | **Scope Creep** | High | High | Strict adherence to MVP priority order, weekly scope reviews, defer non-essential features to Phase 5, use Kanban WIP limits |
| 4 | **User Trust (AI Advice)** | High | Medium | Clear disclaimers, confidence scores, never modify data without approval, audit trail, human review for low-confidence |
| 5 | **Bank Feed Unavailability** | Medium | High | Prioritize SMS/Excel/CSV import, design bank feed as pluggable module, don't depend on bank APIs for core functionality |
| 6 | **Over-Complexity** | High | Medium | Modular monolith (not microservices), hide accounting complexity, simple user-facing screens, iterative AI feature rollout |
| 7 | **Financial Advice Legal Risk** | Critical | Medium | Clear disclaimers on every AI response, no specific investment/tax advice, educational guidance only, terms of service review |
| 8 | **Performance at Scale** | Medium | Medium | PostgreSQL RLS with indexing, Redis caching, Celery for background jobs, query optimization, connection pooling |
| 9 | **Team Skill Gap (FastAPI)** | Medium | Medium | FastAPI is intuitive for Flask developers, comprehensive documentation, start with simple endpoints, pair programming |
| 10 | **AI Hallucination** | High | Medium | Structured prompts with financial context, response validation, confidence scoring, human review for critical recommendations |
| 11 | **Oman Market Specifics** | Medium | Medium | OMR default currency, Islamic finance considerations, SMS import priority, Arabic language support planned |
| 12 | **Third-Party Dependency (OpenAI)** | Medium | Medium | Support multiple LLM providers, implement fallback to rule-based, don't store critical logic in LLM prompts |
| 13 | **Data Migration Complexity** | Medium | Low | Since starting fresh, no migration needed. If migrating from old system, plan dedicated migration sprint |
| 14 | **Family Finance Complexity** | Medium | Medium | Start with simple family model, add complexity incrementally, clear role definitions, extensive permission testing |
| 15 | **Mobile Experience Gap** | Medium | Medium | Responsive design from day one, PWA in Phase 5, API-first enables future native app |

### Risk Response Strategy

| Risk | Strategy | Trigger | Response |
|------|----------|---------|----------|
| AI Cost Overrun | Mitigate | Token usage > 80% of budget | Switch to cheaper model, reduce AI features, notify admin |
| Tenant Data Leak | Prevent | Any security finding | Immediate patch, incident response, notify affected tenants |
| Scope Creep | Avoid | New feature request | Evaluate against MVP priority, defer to Phase 5 if not critical |
| User Trust | Mitigate | Negative user feedback on AI | Improve explanations, add human review, enhance disclaimers |
| Bank Feed Unavailable | Accept | Bank API unavailable | Continue with SMS/CSV import, monitor bank API availability |
| Over-Complexity | Avoid | Module coupling > acceptable | Refactor, enforce module boundaries, simplify user-facing features |
| Legal Risk | Transfer | Legal challenge | Insurance, clear terms of service, legal review of disclaimers |
| Performance | Mitigate | Response time > 500ms | Optimize queries, add caching, scale infrastructure |
| Skill Gap | Mitigate | Development velocity low | Training, documentation, code reviews, external consultation |
| AI Hallucination | Mitigate | Incorrect AI recommendation | Improve prompts, add validation, increase confidence thresholds |

---

## 20. Final Build Order: First 30 Cards

The following is the exact sequence for building the first 30 cards. Each card should be completed, tested, and reviewed before moving to the next. This sequence ensures foundational layers are built before dependent features.

```
PHASE 0: Product & Architecture Reframe (Week 1)
═══════════════════════════════════════════════════════

Card 1:  PF-000   Decide Final Product Name and Vision
Card 2:  PF-001   Choose FastAPI Architecture and Document
Card 3:  PF-002   Define Modular Monolith Boundaries
Card 4:  PF-003   Define PostgreSQL RLS Tenant Strategy
Card 5:  PF-004   Define Financial Digital Twin Model
Card 6:  PF-005   Define AI CFO Safety Rules
Card 7:  PF-006   Define User Navigation Around Financial Life
Card 8:  PF-007   Define Normal User View vs Accountant View
Card 9:  PF-008   Define Import Strategy (Manual, CSV, Excel, SMS)
Card 10: PF-009   Define MVP User Journey
Card 11: PF-010   Define Family Finance Model
Card 12: PF-011   Write PLAN_V2.md (This Document)
Card 13: PF-012   Setup Development Environment
Card 14: PF-013   Create Project Skeleton and Folder Structure
Card 15: PF-014   Setup PostgreSQL and Redis
Card 16: PF-015   Setup Git Repository and Branching Strategy

PHASE 1: SaaS Foundation (Weeks 2-5)
═══════════════════════════════════════════════════════

Card 17: PF-100   Project Architecture & Configuration System
Card 18: PF-101   Database Layer: SQLAlchemy, Alembic, Base Models
Card 19: PF-102   Logging, Exception Handling, and Middleware
Card 20: PF-103   PostgreSQL RLS Implementation
Card 21: SAAS-200  Tenant Model and CRUD
Card 22: SAAS-201  Tenant Isolation Middleware
Card 23: SAAS-202  Subscription Plans (Free, Premium, Family)
Card 24: SAAS-203  Usage Limits and Quotas
Card 25: AUTH-300  User Registration
Card 26: AUTH-301  User Login and JWT
Card 27: AUTH-302  Forgot Password
Card 28: AUTH-303  Email Verification
Card 29: AUTH-304  Role-Based Access Control (RBAC)
Card 30: AUTH-305  Tenant Member Invitation

═══════════════════════════════════════════════════════
```

### Build Order Rationale

1. **Phase 0 First:** All architecture and product decisions must be made before code. This prevents rework and ensures alignment.
2. **Configuration Before Code:** PF-100 (config) must be in place before any feature uses settings.
3. **Database Before Models:** PF-101 (DB layer) must exist before any models can be defined.
4. **RLS Before Tenants:** PF-103 (RLS) must be ready before SAAS-200 creates tenant data.
5. **Tenants Before Auth:** SAAS-200 (tenant) must exist before AUTH-300 creates users in tenants.
6. **Auth Before Everything:** AUTH-300 through AUTH-305 must be complete before any protected feature can be built.
7. **Each Card is Independent:** While sequenced, each card has clear acceptance criteria and can be handed to a coding agent independently.

### After Card 30

Cards 31-50 continue Phase 1 and start Phase 2:

```
Card 31: USR-400   User Profile and Settings
Card 32: USR-401   Currency and Language Preferences
Card 33: USR-402   Theme and Notification Settings
Card 34: ACC-500   Chart of Accounts (Hidden Foundation)
Card 35: ACC-501   Account Types and Hierarchy
Card 36: ACC-502   Opening Balances
Card 37: TRX-600   Simple Transaction Entry
Card 38: TRX-601   Transaction List, Search, and Filter
Card 39: TRX-602   Split Transactions
Card 40: TRX-603   Transfer Between Accounts
Card 41: TRX-604   Transaction Categories
Card 42: TRX-605   Transaction Attachments
Card 43: IMP-700   CSV Import
Card 44: IMP-701   Excel Import
Card 45: IMP-702   SMS Import Parser
Card 46: IMP-703   Import Job Management UI
Card 47: BILL-800  Bill Creation and Tracking
Card 48: BILL-801  Bill Reminders and Alerts
Card 49: SUB-900   Subscription Tracking
Card 50: SUB-901   Subscription Renewal Alerts
```

### Development Guidelines for Coding Agents

When building each card:

1. **Read the card specification completely** before starting.
2. **Check dependencies** — ensure prerequisite cards are complete.
3. **Write tests first** (TDD where practical) or alongside implementation.
4. **Follow existing patterns** — use the same structure as previous cards.
5. **Update documentation** — if the card changes an architectural decision, update the relevant ADR.
6. **Run the full test suite** before marking complete.
7. **Request code review** — have another agent or human review before merging.
8. **Update PLAN_V2.md** — mark card as completed with date and PR link.

---

## Appendices

### Appendix A: Technology Stack Details

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11+ | Programming language |
| FastAPI | 0.104+ | Web framework |
| SQLAlchemy | 2.0+ | ORM |
| Alembic | 1.12+ | Database migrations |
| PostgreSQL | 15+ | Primary database |
| Redis | 7+ | Cache, session store, Celery broker |
| Celery | 5.3+ | Background task queue |
| Pydantic | 2.0+ | Data validation |
| Jinja2 | 3.1+ | Template engine |
| HTMX | 1.9+ | Frontend interactivity |
| Bootstrap | 5.3+ | CSS framework |
| OpenAI | 1.0+ | LLM API |
| pytest | 7.4+ | Testing framework |
| Docker | 24+ | Containerization (Phase 2+) |

### Appendix B: Default Chart of Accounts

```
1000 Assets
  1100 Cash and Bank
    1110 Bank Muscat
    1120 OAB
    1130 Alizz
    1140 Cash in Hand
  1200 Investments
    1210 Stocks
    1220 Mutual Funds
    1230 Fixed Deposits
  1300 Receivables
    1310 Loans to Others
  1400 Property
    1410 Real Estate
    1420 Vehicle

2000 Liabilities
  2100 Credit Cards
    2110 Visa
    2120 Mastercard
  2200 Loans
    2210 Personal Loan
    2220 Car Loan
    2230 Home Loan
  2300 Payables
    2310 Bills Payable

3000 Equity
  3100 Owner's Equity
  3200 Retained Earnings

4000 Income
  4100 Salary
  4200 Freelance Income
  4300 Passive Income
  4400 Other Income

5000 Expenses
  5100 Housing
    5110 Rent
    5120 Utilities
    5130 Maintenance
  5200 Transportation
    5210 Fuel
    5220 Public Transport
    5230 Vehicle Maintenance
  5300 Food
    5310 Groceries
    5320 Dining Out
  5400 Personal
    5410 Clothing
    5420 Entertainment
    5430 Healthcare
  5500 Financial
    5510 Interest Paid
    5520 Bank Fees
  5600 Education
  5700 Subscriptions
  5800 Savings & Investments
```

### Appendix C: AI Prompt Template Examples

#### Daily Brief Prompt

```
You are a Personal CFO analyzing financial data for a user in Oman.
Generate a concise daily brief in a friendly, professional tone.

User Context:
- Currency: OMR
- Today's Date: {{ date }}
- Account Balances: {{ balances }}
- Upcoming Bills (7 days): {{ upcoming_bills }}
- Yesterday's Transactions: {{ yesterday_transactions }}
- Budget Status: {{ budget_status }}
- Active Goals: {{ goals }}
- AI Alerts: {{ alerts }}

Rules:
1. Keep it under 150 words
2. Use OMR currency format (3 decimal places)
3. Highlight urgent items first
4. Suggest one actionable improvement
5. Include disclaimer: "This is educational guidance, not professional financial advice."

Generate the brief:
```

#### Spending Analysis Prompt

```
You are a Spending Analyzer. Review the user's spending patterns and identify insights.

Data:
- This Month's Spending by Category: {{ spending_by_category }}
- Last Month's Spending by Category: {{ last_month_spending }}
- Average Monthly Spending by Category: {{ average_spending }}
- Unusual Transactions: {{ unusual_transactions }}

Rules:
1. Identify top 3 spending changes (increase or decrease)
2. Flag any unusual spending
3. Suggest 2 specific ways to reduce spending without major lifestyle impact
4. Confidence score: rate your analysis (0.0-1.0)
5. Include reasoning for each insight
6. Include disclaimer

Generate insights in structured JSON format.
```

### Appendix D: Environment Variables Template

```bash
# Application
APP_NAME=AI Personal CFO
APP_ENV=development
DEBUG=true
SECRET_KEY=your-secret-key-here

# Database
DATABASE_URL=postgresql+psycopg2://pf_user:password@localhost:5432/pf_dev
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# Redis
REDIS_URL=redis://localhost:6379/0

# Email
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
EMAIL_FROM=noreply@yourdomain.com

# AI / OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_TOKENS=2000
AI_COST_LIMIT_PER_TENANT=5.0

# Security
JWT_SECRET_KEY=your-jwt-secret
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# File Storage
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE=5242880

# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Stripe (Phase 4)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PREMIUM=price_...
STRIPE_PRICE_FAMILY=price_...
```

### Appendix E: Glossary

| Term | Definition |
|------|------------|
| **Financial Digital Twin** | A living computational model of a user's financial life that mirrors, updates, predicts, and simulates financial scenarios. |
| **AI CFO** | The AI-powered financial advisory system that provides insights, recommendations, and simulations. |
| **Tenant** | A logical isolation unit representing an organization, family, or individual user. All data is scoped to a tenant. |
| **RLS** | Row-Level Security — PostgreSQL feature that enforces access control at the database row level. |
| **Modular Monolith** | A single deployable application composed of loosely coupled modules with clear boundaries, allowing future extraction into services. |
| **Double-Entry Accounting** | An accounting system where every transaction affects at least two accounts (debit and credit) with equal amounts. |
| **Snowball Strategy** | Debt repayment method focusing on paying smallest debts first for psychological wins. |
| **Avalanche Strategy** | Debt repayment method focusing on paying highest-interest debts first to minimize total interest. |
| **What-If Simulator** | AI tool that allows users to explore financial scenarios (e.g., "What if I save more?"). |
| **OMR** | Omani Rial — the default currency for the platform. |
| **HTMX** | A library that allows modern web interactions (AJAX, CSS transitions) using HTML attributes. |
| **Celery** | A distributed task queue for running background jobs. |
| **PWA** | Progressive Web App — a web application that can be installed and work offline. |

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 2.0 | 2026-07-01 | Architecture Team | Initial PLAN_V2.md — complete reframe from Flask accounting to FastAPI AI CFO |

## Approval

This plan is approved for development. All team members and coding agents should reference this document as the authoritative source for architecture, priorities, and build order.

---

> **End of PLAN_V2.md**
