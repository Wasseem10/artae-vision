# Agents for Humans architecture

Artae is submitted as a **Professional Agent** for safety and operations teams.
It removes the repetitive work of watching camera walls and surfaces only a
confirmed incident or a decision that needs a person.

```mermaid
flowchart LR
    Camera[Webcam, RTSP camera, or uploaded video] --> Edge[Artae edge worker]
    Edge --> YOLO[YOLO object and pose models]
    YOLO --> Rules[Temporal rules and confidence gates]
    Rules -->|confirmed event| API[FastAPI control plane]

    API --> Strands[Strands Incident Coordinator]
    Strands --> Evidence[Preserve evidence tool]
    Strands --> Notify[Notify responder tool]
    Strands --> Review[Request human review tool]

    Evidence --> Storage[(Supabase or S3 footage)]
    Notify --> Alerts[(Alert and action queue)]
    Review --> Console[Operator console]
    Alerts --> Worker[Delivery worker]
    Worker --> Responder[Assigned responder]

    API --> Database[(PostgreSQL)]
    API --> Console
```

## Responsibility boundaries

- **YOLO and temporal rules** process frames continuously. A network model is
  never placed in the real-time frame loop.
- **Strands Agents SDK** receives a compact, confirmed incident and selects the
  appropriate operational tools. Those tool choices control creation of the
  evidence job and responder alert. The tool calls and aggregate usage are stored
  with the event, without storing private chain-of-thought.
- **Safety policy** guarantees that a provider outage or omitted tool call can
  never suppress a confirmed safety alert.
- **The delivery worker** owns retries and delivery status. The model may prepare
  a notification, but it may never claim that a notification was delivered.
- **Humans remain in control** of ambiguous semantic detections and guarded
  external actions.

## Strands tool loop

```mermaid
sequenceDiagram
    participant Vision as YOLO + fall state machine
    participant API as Artae API
    participant Agent as Strands agent on Bedrock
    participant Tools as Artae tools
    participant Human as Responder

    Vision->>API: Confirmed event + confidence + clip reference
    API->>Agent: Grounded incident context
    Agent->>Tools: preserve_evidence(...)
    Agent->>Tools: notify_responder(...)
    opt Ambiguous context
        Agent->>Tools: request_human_review(...)
    end
    Tools-->>API: Auditable action plan
    API->>Human: Persistent alert and evidence
```

## Deployment boundary

The web console may remain on Vercel. The control plane and Strands coordinator
can run in Docker for the local demonstration and are designed to move to Amazon
Bedrock AgentCore Runtime. AgentCore is an optional hackathon enhancement; the
required Strands implementation is already part of the API process.
