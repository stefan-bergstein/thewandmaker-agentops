"""Check inference through OpenShell, keeping provider credentials outside the shop front."""
import asyncio
import json
import re


async def check_inference(run, sandbox="apprentice"):
    # Stay on-topic so the input rail checks the request and the model can answer it.
    body = {"model": "oracle", "max_tokens": 200, "messages": [
        {"role": "user", "content": "In one short sentence, what does a wand maker sell?"}]}
    command = ["openshell", "sandbox", "exec", "-n", sandbox, "--no-tty", "--timeout", "100", "--",
               "curl", "--silent", "--show-error", "--fail", "--max-time", "90",
               "-H", "Content-Type: application/json", "--data", json.dumps(body),
               "https://inference.local/v1/chat/completions"]
    try:
        code, output, error = await run(command, 115)
    except asyncio.TimeoutError:
        return False, "the authenticated inference request timed out"
    if code:
        status = re.search(r"returned error:\s*(\d{3})\b", error)
        if status:
            return False, f"the authenticated inference request returned HTTP {status[1]}"
        return False, f"the sandbox inference probe exited with code {code}"
    try:
        response = json.loads(output)
        text = ((response.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        if isinstance(text, str) and text.strip():
            return True, ""
    except (ValueError, AttributeError, IndexError, TypeError):
        return False, "the model returned an invalid response"
    return False, "the model returned no answer"
