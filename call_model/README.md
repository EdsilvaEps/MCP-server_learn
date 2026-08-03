# LehmusAI Gemma FastMCP Server

A lightweight Python FastMCP server that exposes OpenAI-compatible tools for calling the remote LehmusAI model `gemma4-31b-jwwqb`.

## Setup

1. Create or activate your Python environment and install dependencies:

```bash
cd /Users/llm-plaground/Documents/projects/call_model
python -m pip install -r requirements.txt
```

2. Configure environment variables if needed:

```bash
export LEHMUS_BASE_URL="https://api.lehmus-ai.oulu.fi"
export LEHMUS_MODEL_NAME="gemma4-31b-jwwqb"
export LEHMUS_API_KEY="your_lehmus_api_key"
export SERVER_PORT=4000
export MCP_TRANSPORT="http"
```

If you are launching the server through a stdio MCP client, set:

```bash
export MCP_TRANSPORT="stdio"
```

3. Start the server:

```bash
python server.py
```

## Tools

The FastMCP server exposes these tools:

- `chatgpt_chat_completion`
- `chatgpt_text_completion`
- `gemma_chat_completion`
- `gemma_text_completion`
- `lehmus_health`

## Example requests

### Text completion

```bash
curl http://127.0.0.1:4000/v1/tools/chatgpt_text_completion -X POST \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Write a short poem about oceans."}'
```

### Chat completion

```bash
curl http://127.0.0.1:4000/v1/tools/chatgpt_chat_completion -X POST \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Summarize neutrino oscillations."}]}'
```

### Health check

```bash
curl http://127.0.0.1:4000/v1/tools/lehmus_health -X POST \
  -H "Content-Type: application/json" \
  -d '{}'
```

## Notes

- The LehmusAI endpoint is expected to support OpenAI-compatible calls for `/v1/completions` and `/v1/chat/completions`.
- If your provider uses a different URL or model name, update `LEHMUS_BASE_URL` or `LEHMUS_MODEL_NAME`.
