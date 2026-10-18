# AutoFlow

AutoFlow is a personal automation and workflow platform for building, scheduling, and executing everyday tasks.

The project aims to provide a simple way to connect data sources, APIs, AI, and notification services into reusable workflows while exploring the engineering challenges behind reliable workflow execution.

## Run locally

Two terminals:

```bash
# 1. Backend: FastAPI on http://localhost:8000
cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

```bash
# 2. Frontend: Next.js on http://localhost:3000
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Everything is mocked for now (planner, tools, Telegram). See [`backend/README.md`](backend/README.md) and [`frontend/README.md`](frontend/README.md) for the API, architecture and tests.

## Overview

A workflow consists of a trigger and a series of tasks.

For example:

```text
Google Sheet
     ↓
Process Expenses
     ↓
Calculate Statistics
     ↓
   ┌─────┴─────┐
   ↓           ↓
Charts     AI Analysis
   │           │
   └─────┬─────┘
         ↓
   Generate PDF
         ↓
   Send Telegram
```

Tasks may depend on the output of other tasks. Independent tasks can be executed concurrently, while dependent tasks wait until their required dependencies have completed.

Workflows are represented internally as Directed Acyclic Graphs (DAGs).

## Example Use Cases

AutoFlow is intended to support automations such as:

- Generating a weekly expense report and sending it through Telegram
- Creating a morning brief from weather, calendar, and news data
- Monitoring websites for meaningful changes
- Scheduling recurring personal tasks
- Processing data and generating reports
- Using AI to summarize or analyze information
- Sending notifications when configured conditions are met

## Planned Architecture

```text
                    Frontend
                       │
                       ▼
                  FastAPI API
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
        PostgreSQL             Redis
             │                   │
             │                   ▼
             │                 Queue
             │                   │
             │          ┌────────┼────────┐
             │          ▼        ▼        ▼
             │        Worker   Worker   Worker
             │          │        │        │
             └──────────┴────────┴────────┘
                              │
                              ▼
                      External Services
```

## Planned Tech Stack

### Backend

- Python
- FastAPI

### Frontend

- React
- TypeScript

### Data

- PostgreSQL
- Redis

### Infrastructure

- Docker
- AWS
- AWS CDK

### CI/CD

- GitHub Actions

### Testing

- pytest

## Core Concepts

### Workflows

A workflow defines a set of tasks and the dependencies between them.

Example:

```text
Weather ─────┐
             │
Calendar ────┼──> AI Summary ──> Telegram
             │
News ────────┘
```

Weather, Calendar, and News can execute concurrently.

`AI Summary` executes only after all three dependencies have completed.

### Tasks

Tasks are individual units of work.

Planned task types include:

- HTTP requests
- Data processing
- CSV / spreadsheet processing
- AI / LLM processing
- PDF generation
- Telegram notifications
- Conditions
- Scheduled tasks

### Workflow Execution

The execution engine will be responsible for:

1. Loading the workflow definition
2. Validating the workflow DAG
3. Determining which tasks are ready
4. Queuing tasks for execution
5. Executing tasks using workers
6. Storing task results
7. Resolving dependent tasks
8. Handling failures and retries
9. Completing the workflow

## AI Integration

AI is treated as one type of task within the workflow engine rather than being the core execution system.

For example:

```text
Expense Data
     ↓
Calculate Metrics
     ↓
AI Analysis
     ↓
Generate Report
```

Planned AI capabilities include:

- Summarization
- Data analysis
- Structured output generation
- Content classification
- Meaningful-change detection
- Natural-language workflow creation

## Reliability

As the project develops, AutoFlow will explore common distributed-system reliability problems including:

- Retries
- Exponential backoff
- Timeouts
- Idempotency
- Duplicate execution
- Worker failures
- Dead-letter queues
- Concurrent execution
- Task recovery

## Project Roadmap

### Phase 1 — First Automation

Build a simple end-to-end automation:

```text
Expense Data
    ↓
Python Processing
    ↓
PDF Report
    ↓
Telegram
```

### Phase 2 — Backend

Introduce:

- FastAPI
- PostgreSQL
- Workflow CRUD APIs
- Execution tracking

### Phase 3 — Task Engine
