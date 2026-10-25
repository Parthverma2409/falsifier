# Token Factory models

Source: `GET https://api.tokenfactory.nebius.com/v1/models?verbose=true`. Prices are USD per 1M tokens.

| Model id | Context | Input $/1M | Output $/1M | Quant | Status |
|---|---:|---:|---:|---|---|
| `deepseek-ai/DeepSeek-V4-Flash-0731` | 1024000 | $0.14 | $0.28 | fp8 |  |
| `deepseek-ai/DeepSeek-V4-Pro` | 1048576 | $1.75 | $3.5 | fp8 |  |
| `deepseek-ai/DeepSeek-V4-Pro-0813` | 979000 | $1.32 | $3.96 | fp8 |  |
| `deepseek-ai/DeepSeek-V4.1-Flash` | 1048000 | $0.3 | $1.2 | fp8 |  |
| `deepseek-ai/DeepSeek-V4.1-Flash-1017` | 1048576 | $0.3 | $1.2 | fp8 |  |
| `google/gemma-3-27b-it` | 110000 | $0.1 | $0.3 | fp8 |  |
| `meta-models/muse-spark-open` | 1048576 | $1.25 | $4.25 | fp4 |  |
| `MiniMaxAI/MiniMax-M3` | 1048576 | $0.3 | $1.2 | fp4 |  |
| `MiniMaxAI/MiniMax-M3.1-Flash` | 1048576 | $0.15 | $0.6 | fp4 |  |
| `moonshotai/Kimi-K2.6` | 262144 | $0.95 | $4 | int4 |  |
| `moonshotai/Kimi-K2.7-Code` | 262144 | $0.95 | $4 | fp4 |  |
| `moonshotai/Kimi-K3` | 1024000 | $3 | $15 | fp4 |  |
| `NousResearch/Hermes-4-405B` | 131072 | $1 | $3 | fp8 |  |
| `nvidia/nemotron-3-super-120b-a12b` | 262144 | $0.3 | $0.9 | fp4 |  |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | 1048576 | $1 | $3 | fp4 |  |
| `nvidia/Nemotron-3.5-Super-VL` | 1048576 | $0.3 | $0.9 | bf16 |  |
| `nvidia/Nemotron-3_5-Lightning` | 1048576 | $0.06 | $0.24 | bf16 |  |
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 262144 | $0.06 | $0.24 | fp8 |  |
| `openai/gpt-oss-120b` | 131072 | $0.15 | $0.6 | fp4 |  |
| `openbmb/MiniCPM-V-4_5` | 32000 | $0.658 | $1.11 | fp16 |  |
| `Qwen/Qwen3-235B-A22B-Instruct-2507` | 262144 | $0.2 | $0.6 | fp8 |  |
| `Qwen/Qwen3-30B-A3B-Instruct-2507` | 262144 | $0.1 | $0.3 | fp8 |  |
| `Qwen/Qwen3-Embedding-8B` | 40960 | $0.01 | $0 |  |  |
| `Qwen/Qwen3.5-397B-A17B` | 262144 | $0.6 | $3.6 | fp4 |  |
| `Qwen/Qwen3.8-27B` | 262144 | $0.45 | $3 | fp4 |  |
| `reflection/beam` | 1048576 | $0.25 | $1 | fp4 |  |
| `zai-org/GLM-5.1` | 202752 | $1.4 | $4.4 | fp8 |  |
| `zai-org/GLM-5.2` | 1048576 | $1.4 | $4.4 | fp4 |  |
| `zai-org/GLM-5.3` | 1024000 | $1.4 | $4.4 | fp4 |  |
| `zai-org/GLM-5.3-Flash` | 1024000 | $0.15 | $0.5 | fp4 |  |

Total: 30 models.

## NVIDIA Nemotron detail

### `nvidia/nemotron-3-super-120b-a12b`

- Nemotron 3 Super is a 120B hybrid MoE model optimized for efficient multi-agent AI and complex reasoning tasks.
- Features: tools, reasoning; quantization fp4; region us-central1
- Cached input $/1M: $0.06
- Limits: 200000.0 tokens/min, 300.0 requests/min

### `nvidia/Nemotron-3-Ultra-550b-a55b`

- Nemotron 3 Ultra is a 550B hybrid MoE model from NVIDIA, optimized for the most demanding multi-agent AI and complex reasoning tasks.
- Features: tools, reasoning; quantization fp4; region us-central1
- Cached input $/1M: $0.12
- Limits: 200000.0 tokens/min, 300.0 requests/min

### `nvidia/Nemotron-3.5-Super-VL`

- NVIDIA's multimodal model for visual understanding, coding, reasoning, and tool use. It processes text, images, and video to generate text responses.
- Features: tools, reasoning; quantization bf16; region us-north1
- Cached input $/1M: $0.06
- Limits: 2000000.0 tokens/min, 300.0 requests/min

### `nvidia/Nemotron-3_5-Lightning`

- NVIDIA's 30B-parameter hybrid MoE model with 3B active parameters per token, designed for efficient agentic reasoning, tool use, coding, and long-context workflows.
- Features: tools, reasoning; quantization bf16; region eu-north1
- Cached input $/1M: n/a
- Limits: 400000.0 tokens/min, 600.0 requests/min

### `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`

- Compact MoE model optimized for efficient reasoning, chat, and coding with strong multilingual support and long-context RAG/agent workflows.
- Features: tools, reasoning; quantization fp8; region eu-north1
- Cached input $/1M: n/a
- Limits: 800000.0 tokens/min, 100.0 requests/min
