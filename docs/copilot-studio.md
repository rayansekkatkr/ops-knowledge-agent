# Copilot Studio agent: Hanbit Ops Assistant

How the low-code part of the project is configured, so it can be rebuilt in any tenant in about an hour.

## Prerequisites

- A **work or school** Microsoft account (Copilot Studio does not accept personal Microsoft accounts).
  A Microsoft 365 Business trial tenant works.
- A Copilot Studio trial or license: https://go.microsoft.com/fwlink/?LinkId=2107702

## 1. Agent

| Setting | Value |
|---|---|
| Type | Standard assistant (classic experience: knowledge, tools, topics, agent flows) |
| Name | Hanbit Ops Assistant |
| Language | English (en-US) |
| Orchestration | Generative orchestration **on** (the model picks knowledge sources and tools) |
| Description | Answers employee questions about incident handling, support plans and SLAs, and security and patch policy, and can open an incident. |

Instructions:

```
You help Hanbit Logistics engineers and support staff.
Answer only from the knowledge sources and always cite the document.
If the answer is not in the documents, say so and suggest who to contact.
When a user reports a production problem, determine the severity (SEV1 to SEV4) using the incident runbook, confirm it with the user, then use the Open incident tool.
Answer in the user's language.
```

## 2. Knowledge

1. **Knowledge** > **Add knowledge** > upload the three files from [`data/copilot-studio-upload/`](../data/copilot-studio-upload/).
2. Wait until each file shows **Ready** (indexed in Dataverse, a few minutes).
3. **Settings** > **Generative AI** > **Knowledge**: turn **off** "Allow ungrounded responses" and
   "Use information from the Web", so the agent answers only from the documents.

## 3. Tool: "Open incident" (Power Automate agent flow)

1. **Tools** > **Add a tool** > **New tool** > **Agent flow**.
2. Trigger **When an agent calls the flow**, text inputs: `title`, `severity`, `service`, `description`.
3. Action **Office 365 Outlook > Send an email (V2)** to the on-call mailbox
   (or **Microsoft Teams > Post message in a chat or channel**).
4. **Respond to the agent** with a text output `ticket_id`:
   `concat('INC-', formatDateTime(utcNow(), 'yyyyMMdd-HHmm'))`.
5. Publish the flow, name the tool `Open incident`, description:
   *Opens a production incident and notifies the on-call team. Use after the severity is confirmed.*

Test: *"The Shipment Tracking API returns 500 errors for all customers."* The agent should classify it as
SEV1 from the runbook, ask for confirmation, call the flow and return the ticket id.

## 4. Tool: the Python MCP server

Copilot Studio supports MCP servers as tools, over the **Streamable HTTP** transport and an **HTTPS** URL.

1. Expose the local server through a tunnel (see the main README), with an API key.
2. **Tools** > **Add a tool** > **New tool** > **Model Context Protocol**.
3. Server URL `https://<tunnel-host>/mcp`, authentication **API key** in header `x-api-key`.
4. Server description (the orchestrator reads it to decide when to call the server):
   *Ops tools: check whether a public HTTPS endpoint is up, with latency and TLS certificate expiry.*

Test: *"Is https://www.microsoft.com up, and when does its certificate expire?"*

## Test results

| Question | Answer | Result |
|---|---|---|
| How fast must we patch a critical CVE on an internet-facing server? | 72 hours, KEV rule and CISO-approved exception mentioned | Correct, cited |
| What credit does an Enterprise customer get at 98.5% availability? | "Below 99.0%, at least 95.0%" tier: 25% of the monthly fee, to request within 30 days | Correct, cited |
| What is our parental leave policy? | Not in the documents, contact HR | No hallucination |
| 서버 비밀번호는 어디에 저장해야 하나요? (Korean) | Azure Key Vault, never in Git | Correct, but answered in English |

The test pane's activity view shows which sources were searched, which were used, and the retrieval time:
the same retrieve-then-generate loop as the Python pipeline in [`rag/`](../rag/).
To answer Korean questions in Korean, add Korean as a secondary language in **Settings** > **Languages**.

## Things to know before production

- Uploaded files are visible to **every** user of the agent, whatever their permissions. For permission-aware
  answers, use SharePoint as the knowledge source instead.
- Agents consume **Copilot Credits** at runtime. Each agent flow action consumes capacity, except when the
  flow is tested from the flow designer or the agent's test chat.
- Power Platform **DLP policies** govern which connectors (including MCP connectors) an agent may use.
