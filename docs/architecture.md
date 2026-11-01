# Architecture

Detailed request flows for SERVE-CONFIDEF. For the high-level overview, see the [README](../README.md#1-architecture).

## Submitting a prediction

```mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway (SigV4)
    participant U as λ UploadVideo
    participant SI as S3 (input)
    participant R as λ RecordPredictVideo
    participant D as DynamoDB (EchoStatus)
    participant E as ECR (echo:latest)
    participant M as SageMaker async endpoint
    participant SO as S3 (preds-success / preds-fail)
    participant N as SNS (EchoPredSuccess / EchoPredFail)
    participant H as λ completion handler

    E-->>M: container image pulled at deploy
    C->>G: POST /upload (video)
    G->>U: invoke
    U->>SI: put_object(input/<job_id>.avi)
    U-->>C: { job_id }
    SI->>R: S3 event
    R->>D: put_item(status = queued)
    R->>M: invoke_endpoint_async (on successful write)
    M->>SI: read input video
    M->>SO: write prediction JSON
    M->>N: publish success / failure
    N->>H: trigger
    H->>D: update status = success / failed + output_location
```

## Polling and fetching the result

```mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway (SigV4)
    participant P as λ PollPredict
    participant F as λ FetchPredict
    participant D as DynamoDB (EchoStatus)
    participant S as S3 (preds-success)

    loop until status is success or failed
        C->>G: GET /poll?job_id=...
        G->>P: invoke
        P->>D: get_item(job_id)
        D-->>P: status (queued / success / failed)
        P-->>C: { job_id, status }
    end
    C->>G: GET /fetch?job_id=...
    G->>F: invoke
    F->>D: get_item(job_id)
    D-->>F: output_location
    F->>S: get_object(output_location)
    S-->>F: prediction JSON
    F-->>C: { job_id, status, ejection_fraction, quantiles }
```
