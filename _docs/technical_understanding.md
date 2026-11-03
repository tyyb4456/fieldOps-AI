# FieldOps AI — Technical Understanding

**FieldOps AI: Autonomous Field-Service Coordination Platform**

This document explains how FieldOps AI is built with software engineering and Generative AI technologies: which technologies are used, why, what responsibilities they have, and how they communicate.

The starting stack:

- Python
- FastAPI
- PostgreSQL
- LangGraph
- Redis
- React
- LLM API
- RAG
- WhatsApp Business API

## 1. The system as a whole

FieldOps AI is divided into six major components. They work together and are not six separate applications.

| Component | Responsibility |
| --- | --- |
| **1. User Interface** | React-based applications where customers submit complaints, technicians manage jobs, and administrators monitor operations. |
| **2. Backend** | FastAPI handles requests, authentication, database operations, validation, and business logic. |
| **3. AI Layer** | LLMs understand complaints, extract information, ask questions, generate checklists, and prepare reports. |
| **4. Knowledge Layer** | RAG retrieves relevant information from equipment manuals and historical technical documentation. |
| **5. Agent Orchestration** | LangGraph manages the sequence of AI tasks, decisions, tool calls, retries, and exception handling. |
| **6. Data and Integration Layer** | PostgreSQL stores business records, Redis supports temporary state and background coordination, and external APIs connect WhatsApp and other services. |

## 2. LLM — the intelligence component

LLM stands for Large Language Model (examples: GPT, Claude, Gemini, Llama). It is an AI model capable of understanding and generating human language.

Consider this customer message:

> "My solar isn't working since morning. The inverter is blinking red and making a strange noise."

A traditional backend cannot easily understand the meaning of this sentence without predefined rules. An LLM can interpret it and extract useful information.

### What the LLM does in FieldOps AI

**A. Complaint understanding.** Convert unstructured customer messages into structured information.

Input:

> My inverter stopped working and shows error E-05.

Output:

```json
{
  "equipment": "solar_inverter",
  "symptom": "generation_stopped",
  "error_code": "E-05",
  "cause": null
}
```

**B. Clarification.** Determine what information is missing and formulate appropriate questions.

**C. Diagnostic checklist generation.** Use retrieved technical documentation to prepare a relevant checklist.

**D. Completion report generation.** Convert technician notes into a professional, structured report.

**E. Conversational interaction.** Communicate naturally with customers and technicians.

### Which LLM to use

Start with a hosted LLM API; there is no need to train a model. Evaluate providers on:

- Structured output support.
- Tool calling.
- Image understanding.
- Language quality.
- API cost.
- Latency.

Since customers in Pakistan may communicate in English, Urdu, and Roman Urdu, multilingual performance should be part of the evaluation.

> **Important:** an LLM is not the database, the scheduling engine, or the source of technical truth. It is an intelligence component that helps interpret information and prepare decisions.

## 3. AI agents — what makes FieldOps AI agentic

### Normal LLM vs. AI agent

A **normal LLM** interaction: you provide input and the model generates an answer.

```
Input:  My inverter shows error E-05.
Output: Please provide the inverter model.
```

An **AI agent** can do more. It can:

1. Understand a task.
2. Decide what information it needs.
3. Select an available tool.
4. Execute that tool.
5. Inspect the result.
6. Decide what to do next.
7. Continue until its assigned objective is complete or it needs assistance.

For example, a FieldOps AI agent receives a complaint and might decide: retrieve the registered equipment, search the technical documentation, send a clarification message asking for the missing error code, and, once the necessary information is available, prepare a work-order draft.

### Tools

Tools are functions that an agent can call to interact with external systems.

| Tool | Responsibility |
| --- | --- |
| `get_customer()` | Retrieve customer information |
| `get_equipment()` | Retrieve registered equipment |
| `search_manual()` | Search technical manuals |
| `get_service_history()` | Retrieve previous maintenance records |
| `send_message()` | Send a customer message |
| `create_work_order()` | Create a work order |
| `find_technician()` | Find eligible technicians |
| `assign_technician()` | Assign a technician |
| `update_job_status()` | Update job progress |
| `generate_report()` | Prepare completion report |

The LLM does not directly connect to PostgreSQL or WhatsApp. It requests an available tool, and the backend executes the corresponding function with appropriate authorization and validation.

**Example tool call:**

```json
{
  "tool": "get_equipment",
  "arguments": {
    "customer_id": "CUS-1042"
  }
}
```

The backend executes the function and returns:

```json
{
  "equipment_id": "SOL-1042-INV",
  "type": "solar_inverter",
  "model": "Example 10 kW model"
}
```

The AI can now use that information in its next decision. This interaction between an LLM and external functions is called **tool calling** or **function calling**.

> **Security rule:** tool calls must be checked against the authenticated user's permissions. The model must never be allowed to decide which customer records it is authorized to access.

## 4. Single agent vs. multi-agent

### Single-agent architecture

One main agent handles the entire complaint-processing workflow: understanding complaints, retrieving equipment information, searching manuals, asking clarification questions, preparing work orders, requesting technician assignment, and generating reports. It uses different tools for these operations.

### Multi-agent architecture

Different agents have separate responsibilities and communicate through a shared workflow or orchestration system.

| Agent | Responsibility |
| --- | --- |
| Complaint Agent | Understand complaints and extract information |
| Diagnostic Agent | Retrieve manuals and prepare diagnostic checklists |
| Work Order Agent | Prepare and validate work orders |
| Scheduling Agent | Coordinate technician assignments |
| Reporting Agent | Prepare completion reports |

### Recommendation

**One primary agent with specialized workflow nodes and tools.**

The workflow is relatively structured and its stages are known in advance. Five independent agents communicating with each other are not needed to complete a predictable maintenance workflow. One coordinated AI workflow with separate functions for complaint understanding, retrieval, checklist generation, and reporting is sufficient.

Specialized agents can be introduced later if testing demonstrates a measurable improvement. For example, a diagnostic agent could become independent if technical investigation becomes substantially more complex.

> Build a reliable single-agent system first. Multi-agent architecture is an advanced extension, not an MVP requirement.

## 5. LangGraph — workflow control

LangGraph is a framework for building stateful AI workflows and agents. The easiest way to understand it is as a flowchart where each step performs a particular operation. For example:

1. Receive complaint.
2. Understand complaint.
3. Check missing information.
4. Ask questions if necessary.
5. Retrieve technical documentation.
6. Generate checklist.
7. Create work order.
8. Assign technician.

### What is a graph?

- **Nodes:** individual operations.
- **Edges:** connections between operations.
- **Conditional edges:** decisions about which operation should execute next.
- **State:** shared information maintained throughout the workflow.

### Simplified workflow

```
Receive complaint
      ↓
Analyze complaint
      ↓
Is information complete?
      ├── No  → Ask questions → Wait for customer → Resume workflow after response
      └── Yes → Retrieve manuals
                      ↓
                Generate checklist
                      ↓
                Validate and create work order
                      ↓
                Assign technician
```

The workflow can make decisions and move between nodes depending on the current state.

### What is state?

State is the information the workflow needs to remember while processing a complaint. For Ahmed's complaint:

```python
state = {
    "complaint_id": "CMP-2026-00125",
    "customer_id": "CUS-1042",
    "equipment_id": "SOL-1042-INV",
    "symptoms": [
        "generation_stopped",
        "red_warning_indicator"
    ],
    "error_code": "E-05",
    "missing_information": [],
    "manual_context": [],
    "diagnostic_checklist": [],
    "work_order_id": None,
    "technician_id": None,
    "status": "processing"
}
```

Each workflow node reads relevant information from this state and updates it:

- Complaint analysis updates symptoms.
- Clarification updates missing information.
- Retrieval updates manual context.
- Work-order creation updates the work-order ID.
- Assignment updates the technician ID.

### Why not just use ordinary Python functions?

Ordinary Python functions can and should be used for most business operations. LangGraph adds useful capabilities for more complicated AI workflows:

- Conditional branching.
- Persistent workflow state.
- Pausing and resuming.
- Retry and failure handling.
- Human intervention.
- Coordination of multiple tools.

For FieldOps AI, a particularly valuable feature is the ability to pause a workflow while waiting for a customer response and resume it later. However, durable checkpointing must be configured and the relevant state persisted; keeping everything in Python memory will not work reliably when the server restarts.

> LangGraph coordinates AI workflows. It does not replace FastAPI, PostgreSQL, the scheduling algorithm, or business logic.

## 6. RAG — understanding equipment manuals

RAG stands for Retrieval-Augmented Generation.

### The problem with an ordinary LLM

If a customer reports "My inverter displays error E-05," an ordinary LLM may answer from its general training knowledge. But different manufacturers use different error codes, so the answer might be incorrect for the customer's particular equipment. This is dangerous in technical maintenance.

### How RAG solves this

Instead of depending only on the LLM's existing knowledge, relevant information retrieved from the company's own technical documentation is provided to it, such as:

- Manufacturer manuals.
- Equipment troubleshooting guides.
- Installation documentation.
- Maintenance procedures.
- Approved service bulletins.

The process has two stages.

### Stage A: Preparing the knowledge base

This happens before customers start submitting complaints.

```
Upload manufacturer PDF manuals
      ↓
Extract document text (PDF parsing)
      ↓
Split text into chunks
      ↓
Generate embeddings (convert text into numerical vectors)
      ↓
Store in vector database (text, embeddings and document metadata)
```

**1. Document extraction.** A document-processing library extracts text from the PDF, for example:

```
Error Code E-05

Description:
Refer to the model-specific protection
and troubleshooting procedure.

Recommended checks:
See troubleshooting section.
```

Real manuals may also contain tables, diagrams, and scanned pages, so extraction quality matters.

**2. Chunking.** A 300-page manual is not stored as one searchable unit. It is split into smaller sections, for example:

- Chunk 1: product specifications.
- Chunk 2: installation instructions.
- Chunk 3: error codes.
- Chunk 4: troubleshooting procedures.
- Chunk 5: maintenance instructions.

When someone asks about error E-05, the relevant section should be retrieved rather than the entire manual.

**3. Embeddings.** An embedding is a numerical representation of text. An embedding model converts text such as "Inverter showing error E-05" into a vector, which is essentially a list of numbers. Similar meanings generally produce vectors that are closer together in the embedding space, so the system can find related information even when the exact wording differs. An existing embedding API or open-source embedding model can be used; no training is needed.

**4. Vector database.** A vector database stores embeddings and allows similarity searches. The recommendation is **PostgreSQL + pgvector**: PostgreSQL is already needed for customers, equipment, work orders, and technicians, and pgvector lets both normal business records and vector embeddings live in the same database. A separate vector database is not needed for the initial MVP.

### Stage B: Retrieving knowledge when a complaint arrives

```
Customer reports error E-05
      ↓
Create search query
      ↓
Search relevant manual chunks (vector similarity + equipment metadata filters)
      ↓
Retrieve matching documentation
      ↓
Provide retrieved content to LLM
      ↓
Generate grounded response (with document references and uncertainty handling)
```

Retrieval should filter documentation by the equipment's manufacturer and model, so that instructions for a different inverter are not retrieved just because the error code looks similar.

### A critical point about RAG

RAG does not guarantee that the generated answer is correct. It only gives the LLM access to relevant external information. The system still needs:

- Document and equipment matching.
- Retrieval quality testing.
- Source citations.
- Validation of generated instructions.
- A fallback when reliable documentation is unavailable.

For safety-sensitive procedures, an LLM-generated checklist should be based on approved procedures and reviewed against predefined constraints.

## 7. Tool calling — connecting AI to business operations

Suppose the LLM determines that a work order needs to be created. It should not have unrestricted database access. Instead, specific backend functions are exposed as tools:

```python
def create_work_order(
    customer_id: str,
    equipment_id: str,
    complaint_id: str,
    priority: str,
    checklist: list
):
    # Validate customer and equipment
    # Check complaint state
    # Save work order
    # Return work order ID
    pass
```

The interaction:

```
LLM decides a work order is ready
      ↓
Requests create_work_order tool
      ↓
FastAPI executes authorized backend function
      ↓
Backend validates and saves record
      ↓
Returns WO-2026-0087
```

The LLM can then use the returned work-order ID in subsequent steps. This is the connection between AI intelligence and actual software functionality.

### Initial tools

| Tool | Called when |
| --- | --- |
| `get_customer` | Customer identity or account context is needed |
| `get_equipment` | Equipment information is needed |
| `get_service_history` | Previous maintenance information is needed |
| `search_manual` | Technical documentation is needed |
| `send_clarification` | Customer information is missing |
| `create_work_order` | Complaint is sufficiently validated |
| `find_eligible_technicians` | Job is ready for assignment |
| `assign_technician` | A valid technician is selected |
| `update_work_order` | Job information changes |
| `generate_completion_report` | Technician submits repair details |

Some of these should be called by ordinary backend workflow nodes rather than freely selected by an LLM. For example, assigning a technician should be controlled by the scheduling workflow; the LLM may request assignment, but it should not bypass eligibility checks.

> An AI agent can request an action, but the backend decides whether that action is permitted.

## 8. FastAPI — the backend

FastAPI is a Python framework for building APIs. An API (Application Programming Interface) allows different software components to communicate. FastAPI is the central communication and control layer of FieldOps AI:

- React communicates with FastAPI.
- FastAPI communicates with PostgreSQL.
- FastAPI invokes LangGraph workflows.
- FastAPI receives WhatsApp webhooks.
- FastAPI executes business operations.

### Example: submitting a complaint

React sends an HTTP request:

```
POST /api/complaints
```

```json
{
  "customer_id": "CUS-1042",
  "message": "My inverter has stopped working",
  "equipment_id": "SOL-1042-INV"
}
```

FastAPI then:

1. Authenticates the customer.
2. Validates the request.
3. Creates a complaint record.
4. Starts the complaint-processing workflow.
5. Returns the complaint ID to the frontend.

A simplified example:

```python
from fastapi import FastAPI, BackgroundTasks

app = FastAPI()

@app.post("/api/complaints")
async def submit_complaint(
    request: ComplaintRequest,
    background_tasks: BackgroundTasks
):
    complaint = await save_complaint(request)

    background_tasks.add_task(
        process_complaint,
        complaint.id
    )

    return {
        "complaint_id": complaint.id,
        "status": "received"
    }
```

This is illustrative code. In the actual implementation, a durable background job system should be used for important AI workflows rather than FastAPI's lightweight background task mechanism.

### Suggested API endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /complaints` | Submit complaint |
| `GET /complaints/{id}` | View complaint |
| `POST /complaints/{id}/messages` | Send clarification response |
| `GET /work-orders` | Retrieve work orders |
| `POST /work-orders` | Create work order |
| `GET /technicians` | Retrieve technicians |
| `POST /work-orders/{id}/assign` | Assign technician |
| `PATCH /work-orders/{id}/status` | Update job status |
| `POST /work-orders/{id}/completion` | Submit completion report |

FastAPI also provides automatic API documentation through Swagger UI, which is useful when developing and testing endpoints.

## 9. PostgreSQL — the main database

PostgreSQL stores the permanent business information of FieldOps AI. A company with 500 customers may have, for each customer, one or more solar installations, different pieces of equipment, multiple maintenance complaints, multiple work orders, and previous service records. A relational database stores and connects all of this.

### Recommended tables

| Table | Information stored |
| --- | --- |
| `users` | Login accounts and roles |
| `customers` | Customer information |
| `technicians` | Technician profiles and skills |
| `equipment` | Registered solar equipment |
| `complaints` | Customer complaints |
| `conversations` | Customer and AI interactions |
| `messages` | Individual messages |
| `documents` | Uploaded manuals and metadata |
| `document_chunks` | Extracted manual sections and embeddings |
| `work_orders` | Maintenance jobs |
| `technician_assignments` | Technician-job assignments |
| `service_records` | Historical maintenance information |
| `completion_reports` | Technician completion reports |
| `workflow_runs` | Workflow execution and status |

### Conceptual relationships

```
Customer → Equipment → Complaints → Work Orders → Assignments → Completion Reports
```

This is a conceptual relationship diagram, not the final schema. For example, a customer can own multiple equipment records, and an equipment record can have multiple maintenance complaints over time.

### Why not store everything inside the LLM?

An LLM is not a reliable permanent storage system. A database ensures that:

- Customer records persist.
- Work orders can be retrieved.
- Technician assignments remain consistent.
- Conversations can be resumed.
- Reports can be audited.
- The system can recover after restarting.

> PostgreSQL stores the truth about the business. The LLM interprets information and generates proposed outputs. The backend validates changes before updating that business truth.

## 10. Redis — background processing and temporary state

Redis is an in-memory data store. Unlike PostgreSQL, which is the primary persistent business database, Redis is commonly used for fast temporary data access and coordination.

If 50 customers submit complaints within a few minutes, each complaint may require LLM API calls, document retrieval, image processing, voice transcription, message sending, and work-order preparation. Not every operation should block the main HTTP request, so background workers are used.

### How Redis fits in

- Redis for job queuing.
- Celery (a task-processing framework) for background task execution.

```
Customer submits complaint
      ↓
FastAPI saves complaint in PostgreSQL
      ↓
Redis queue stores pending task information
      ↓
Celery worker processes complaint asynchronously
      ↓
LangGraph workflow runs the AI processing steps
```

The customer receives an immediate response ("Your complaint has been received. Reference: CMP-2026-00125.") while AI processing continues in the background.

### Is Redis needed from day one?

It is useful for the final system when running multiple background workers or managing a significant number of asynchronous operations, but it should not be introduced on day one. Development can start with FastAPI, PostgreSQL, and LangGraph; Redis and Celery can be added when implementing durable background processing.

Redis should also not be confused with LangGraph checkpoint storage. They solve different problems, although some implementations can use Redis for checkpoint persistence too.

## 11. React — the frontend

There are three primary user types, so three interfaces are designed, all within **one React application using role-based access control** (no need for three separate frontend projects).

### A. Customer dashboard

Customers can:

- Submit complaints.
- Upload photographs.
- Send text or voice messages.
- Answer clarification questions.
- View complaint status.
- Track assigned technicians.
- View completed service reports.

### B. Technician dashboard

Technicians can:

- View assigned work orders.
- Accept or reject assignments.
- View diagnostic checklists.
- Access equipment manuals.
- Update repair status.
- Submit findings.
- Upload photographs.
- Submit completion reports.

### C. Administrator dashboard

Company administrators can:

- View all complaints.
- Monitor active work orders.
- Manage customers and equipment.
- Manage technicians and skills.
- Upload equipment manuals.
- View technician workload.
- Monitor unresolved jobs.
- Review escalated cases.
- Inspect AI-generated reports.

## 12. WhatsApp Business API — customer communication

Since both web and WhatsApp complaint channels are in scope, an integration with the official WhatsApp Business Platform is needed. It allows the backend to receive and send WhatsApp messages programmatically.

### Message flow

1. Ahmed sends a WhatsApp message.
2. WhatsApp sends an event to the configured webhook.
3. FastAPI receives the webhook.
4. The backend verifies the webhook and processes the message.
5. It identifies the customer's account using a verified phone-number association.
6. It creates or updates the complaint.
7. The LangGraph workflow processes the complaint.
8. The backend sends the AI-generated clarification question through the WhatsApp API.

### Implementation considerations

- An eligible Meta business setup and configured WhatsApp Business Platform access are required.
- Message templates and customer messaging windows have platform-specific rules.
- Incoming media requires additional processing.
- Webhook events can be duplicated, so the backend needs **idempotency** protection: processing the same event twice must not accidentally create two complaints or two work orders.

**MVP approach:** implement the web channel first, then integrate WhatsApp once the complaint workflow is stable. This avoids debugging two separate problems (the AI workflow and the external messaging integration) simultaneously.

## 13. Multimodal AI — text, images and voice

Multimodal AI can process more than one type of input: text, images, audio, and video (if supported). Three modalities are prioritized.

### A. Text

The customer submits, for example, "My solar inverter shows a warning," and an LLM extracts the complaint information. This is the easiest modality and the starting point.

### B. Images

A customer uploads a photograph of an inverter display. A vision-capable LLM can potentially extract:

- Visible equipment label.
- Displayed error code.
- Warning indicators.
- Obvious external damage.

It must distinguish visible evidence from assumptions. It can report "The photograph appears to show error E-05," but should not conclude "The inverter's internal circuit is damaged," because a photograph alone cannot reliably establish that.

### C. Voice

Suppose the customer sends an Urdu voice message:

> میرا سولر صبح سے کام نہیں کر رہا، انورٹر پر لال لائٹ آ رہی ہے۔

The system converts speech into text using Automatic Speech Recognition (ASR):

```
WhatsApp voice message
      ↓
Audio file
      ↓
Speech-to-text model (transcribes Urdu or English speech)
      ↓
Transcribed complaint (text representation)
      ↓
Normal complaint-processing workflow
```

Speech-to-text services such as Whisper can be evaluated. For a Pakistan-focused use case, actual Urdu, English, and Roman Urdu examples should be tested rather than assuming all transcription services handle them equally well.

### MVP modality priority

| Modality | Priority |
| --- | --- |
| Text | Essential |
| Images | Essential |
| Voice | Advanced MVP feature |
| Video | Exclude initially |

A reliable text-and-image workflow is more valuable than a multimodal system that frequently misinterprets customer complaints.

## 14. How the technologies communicate

Tracing Ahmed's complaint through the system:

| Step | Component | What happens |
| --- | --- | --- |
| 1 | React | Customer submits complaint |
| 2 | FastAPI | Receives and validates request |
| 3 | PostgreSQL | Saves complaint |
| 4 | Redis + Celery | Schedules background processing |
| 5 | LangGraph | Starts complaint workflow |
| 6 | LLM API | Extracts symptoms and missing information |
| 7 | FastAPI tools | Retrieve customer and equipment records |
| 8 | RAG + pgvector | Retrieves relevant manual sections |
| 9 | LLM API | Generates diagnostic checklist |
| 10 | Backend | Validates and creates work order |
| 11 | Scheduling service | Selects eligible technician |
| 12 | PostgreSQL | Saves assignment |
| 13 | React / WhatsApp | Displays job updates |
| 14 | LangGraph + LLM | Prepares completion report |
| 15 | Backend | Checks evidence and closes or escalates job |

The LLM is not involved in every step:

- Saving a complaint is ordinary backend work.
- Retrieving an equipment record is a database operation.
- Selecting a technician is scheduling logic.
- Updating a work-order status is a backend operation.

The LLM is used where language understanding, reasoning over retrieved information, or content generation is genuinely needed. This separation makes the system more predictable, easier to debug, and less expensive to operate.

## 15. Recommended technology stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| Frontend | React + TypeScript | Customer, technician and administrator interfaces |
| Backend | Python + FastAPI | APIs, authentication, business logic and validation |
| AI and orchestration | LLM API + LangGraph | Complaint understanding, agents, tool calling and workflows |
| Knowledge retrieval | pgvector + embedding model | Equipment manuals and technical knowledge retrieval |
| Database | PostgreSQL | Customers, equipment, complaints, jobs and reports |
| Background processing | Redis + Celery | Background jobs and asynchronous processing |
| External integration | WhatsApp Business Platform | Customer messaging and notifications |
| Deployment | Docker | Consistent development and deployment environments |

### Additional libraries

| Requirement | Suggested technology |
| --- | --- |
| Database ORM | SQLAlchemy |
| Request validation | Pydantic |
| Database migrations | Alembic |
| PDF extraction | PyMuPDF |
| Vector search | pgvector |
| Authentication | JWT-based authentication |
| Frontend API communication | TanStack Query |
| Frontend styling | Tailwind CSS |
| Testing | Pytest |
| API testing | Postman |

These are implementation choices, not additional core systems, and not all are needed immediately.

## 16. What to avoid

| Technology or approach | Recommendation |
| --- | --- |
| Training your own LLM | Not needed |
| Training a custom vision model | Not needed |
| Five independent AI agents | Avoid initially |
| Separate vector database | Use pgvector initially |
| Kubernetes | Unnecessary for a student MVP |
| Microservices architecture | Start with a modular monolith |
| Real-time GPS tracking | Optional advanced feature |
| Complex route optimization | Not initially required |
| Autonomous electrical diagnosis | Unsafe and unrealistic |
| Multiple LLM providers simultaneously | Start with one provider |

A **modular monolith** is one backend application whose internal responsibilities are separated into modules:

```
backend/
    app/
        api/
        core/
        models/
        schemas/

        services/
            complaint_service.py
            equipment_service.py
            scheduling_service.py
            work_order_service.py
            reporting_service.py

        ai/
            llm_service.py
            rag_service.py
            tools.py
            workflows/
                complaint_graph.py

        integrations/
            whatsapp.py
            voice.py

        database/
            connection.py
```

This is much easier to develop and maintain than distributing every component into separate services.

## 17. Summary: what makes FieldOps AI intelligent

| Technology | Its actual job |
| --- | --- |
| LLM | Understand and generate language |
| AI agent | Decide which operations to request to achieve a task |
| LangGraph | Coordinate stateful AI workflows |
| RAG | Retrieve relevant technical knowledge |
| Embeddings | Represent text numerically for similarity search |
| pgvector | Search stored embeddings |
| Tool calling | Allow AI to request backend operations |
| FastAPI | Expose APIs and execute business logic |
| PostgreSQL | Store permanent business records |
| Redis | Support queues and temporary coordination |
| Celery | Execute background tasks |
| React | Provide user interfaces |
| WhatsApp API | Enable external messaging |

**Core architectural principle:** AI handles understanding and reasoning. Backend software handles business rules and controlled execution. The database maintains the authoritative operational records. LangGraph coordinates the process.

## 18. Recommended build order

1. **FastAPI + PostgreSQL:** establish the business application.
2. **React:** build customer, technician and administrator interfaces.
3. **LLM integration:** implement complaint extraction and clarification.
4. **RAG:** add equipment manuals and technical retrieval.
5. **LangGraph:** coordinate the complete complaint-processing workflow.
6. **Tool calling:** connect the AI workflow to validated backend operations.
7. **Scheduling engine:** implement deterministic technician assignment.
8. **Redis + Celery:** introduce reliable background execution.
9. **WhatsApp integration:** add the second complaint channel.
10. **Multimodal processing:** add voice transcription and improve image understanding.

This order reduces risk because the business workflow can be tested before adding more complicated AI integrations.
