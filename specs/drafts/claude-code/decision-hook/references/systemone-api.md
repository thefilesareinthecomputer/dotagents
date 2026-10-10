# Ollama `/v1/systemone`, as measured on 2026-10-09

Ollama 0.40.1 on the laptop (MacBook Air M1, 16 GB). Source: docs.ollama.com/api/systemone plus live probes. Re-verify after any Ollama upgrade.

## Request

```json
{"model": "tev1:0.8b",
 "state": {"tool_name": "Bash", "tool_input": {"command": "..."}, "cwd": "...", "permission_mode": "default"},
 "questions": {"risk": {"type": "choice", "instructions": "...", "criteria": {"none": "...", "destroy": "..."}}},
 "keep_alive": "10m"}
```

- `state` is a string, object or array. Objects are serialized by the server.
- Question types: `choice` (a probability per option), `noul` (one probability that a condition holds), `score` (an ordered rubric). `choice` and `score` need `criteria`; `noul` criteria are optional.
- `keep_alive` is documented and honored: a duration string or seconds; `0` unloads; negative keeps the model loaded. The loaded model shows in `GET /api/ps` with `runner` set to `mlx` for tev1 and laya on Apple Silicon.

## Reply

```json
{"model": "tev1:0.8b",
 "answers": {"risk": {"type": "choice", "choice": "destroy",
                      "probabilities": {"none": 0.05, "destroy": 0.95, "exfil": 0.0}, "confidence": 0.87}},
 "usage": {"input_tokens": 758, "output_tokens": 0}, "prompt_eval_cached_count": 352}
```

A `noul` answer is `{"type": "noul", "noul": 0.73}`.

## Limits, as the server enforces them

| Limit | Value | Error |
|---|---|---|
| questions per request | 1 to 64 | `questions must contain 1–64 fields` |
| text plus schema | 64 KiB | HTTP 413 `text and schema must not exceed 64 KiB` |
| `choice` options | 2 to 26 | `criteria must contain 2–26 candidates` (the docs say 255; the server says 26) |
| `score` levels | 2 to 26 | same |
| streaming, tools | not supported | |

## Latency on the laptop

| Model | One `choice` question, 6 options | Five `noul` questions | Cold load | Swap from the other model |
|---|---|---|---|---|
| tev1:0.8b (812 MB tag, MLX runner) | 280 ms median, 350 max | 593 ms median | 3.1 s from disk, 1.0 s from file cache | 1.06 s |
| laya (421 M encoder, MLX runner) | 103 ms median, 111 max | 310 ms median | 1.9 s | 0.12 s |

Cost grows per question, about 110 ms each on tev1:0.8b, since each question is scored separately with the state prefix cached. One `choice` question is the cheap shape: five `noul` questions take five scoring passes for the same judgment, which measured 2.1 times the latency of the one `choice` pass.

End to end from a hook process (Python start, `/api/ps`, the question, the log write): 420 to 480 ms wall on tev1:0.8b warm, 1.1 s on a file-cached cold load.

## Memory

`GET /api/ps` `size` is not a memory reading for the MLX runner: it reported 8.07 GB for tev1:0.8b while the runner process held 0.69 GB resident, and the figure changed between calls (1.4 GB, 2.7 GB, 8.1 GB). The hook reads the runner's resident size from `ps` and uses that for MLX models; for the llamacpp runner it takes the larger of the two readings (ollama/ollama#18099 is the opposite failure, a heap that grew past what `/api/ps` reported).
