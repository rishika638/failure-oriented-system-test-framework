import asyncio
import hmac
import logging
import os

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from fault_injection.policy import apply_delay, parse_fault
from replay.environment import validate_configured_target


logger = logging.getLogger("failure_engine.fault_proxy")
app = FastAPI(title="Synthetic Fault Proxy")
_slots = asyncio.Semaphore(16)
_MAX_RESPONSE_BYTES = 1024 * 1024


class AbortedResponse(Response):
    async def __call__(self, scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/octet-stream")],
        })
        raise ConnectionResetError("Synthetic application-level connection abort")


@app.get("/health")
async def health():
    upstream = validate_configured_target(
        os.environ.get("FAULT_UPSTREAM_URL", ""),
        set(os.environ.get("FAULT_ALLOWED_HOSTS", "").split(",")),
        "/health",
        private_hosts_env="FAULT_ALLOWED_PRIVATE_HOSTS",
    )
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(2),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.get(upstream)
            if response.status_code != 200:
                raise HTTPException(status_code=503, detail="Synthetic upstream is not ready")
    except httpx.HTTPError as error:
        raise HTTPException(status_code=503, detail="Synthetic upstream is not ready") from error
    return {"status": "ok"}


@app.get("/{path:path}")
async def proxy_get(path: str, request: Request):
    route_path = f"/{path}"
    if route_path not in {"/ping", "/dependency"} or request.url.query:
        raise HTTPException(status_code=404, detail="Synthetic proxy route not found")
    expected_token = os.environ.get("FAULT_PROXY_TOKEN", "")
    supplied_token = request.headers.get("X-Fault-Proxy-Token", "")
    if len(expected_token) < 24 or not hmac.compare_digest(supplied_token, expected_token):
        raise HTTPException(status_code=401, detail="Synthetic proxy authorization required")

    try:
        fault = parse_fault(request.headers.get("X-Engine-Fault", ""))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    upstream = validate_configured_target(
        os.environ.get("FAULT_UPSTREAM_URL", ""),
        set(os.environ.get("FAULT_ALLOWED_HOSTS", "").split(",")),
        route_path,
        private_hosts_env="FAULT_ALLOWED_PRIVATE_HOSTS",
    )
    if fault and fault.kind == "dependency":
        return Response(
            content=b'{"error":"synthetic dependency unavailable"}',
            media_type="application/json",
            status_code=503,
        )
    if fault and fault.kind == "abort":
        return AbortedResponse()
    if fault and fault.kind in {"latency", "jitter", "timeout"}:
        await asyncio.to_thread(apply_delay, fault)

    async with _slots:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(5),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream("GET", upstream, headers={"Accept": "application/json"}) as response:
                    chunks = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > _MAX_RESPONSE_BYTES:
                            raise HTTPException(status_code=502, detail="Synthetic target response exceeded size limit")
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    return Response(
                        content=content,
                        status_code=response.status_code,
                        media_type=response.headers.get("content-type", "application/octet-stream"),
                    )
        except HTTPException:
            raise
        except httpx.HTTPError as error:
            logger.warning("Synthetic upstream request failed", extra={"error_type": type(error).__name__})
            raise HTTPException(status_code=502, detail="Synthetic upstream is unavailable") from error
