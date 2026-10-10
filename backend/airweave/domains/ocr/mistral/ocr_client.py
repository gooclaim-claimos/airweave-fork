"""Mistral direct OCR API client.

Encapsulates interactions with Mistral's OCR API using direct (synchronous)
calls instead of the batch API. Each document is processed immediately,
returning results without polling.

All network calls go through :meth:`_api_call` which applies rate-limiting
(via :class:`MistralRateLimiter`) and exponential-backoff retries (via tenacity).
"""

from __future__ import annotations

import asyncio
import base64
import os
from typing import Any, Callable, Optional

import aiofiles
import httpx
from httpx import HTTPStatusError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from airweave.core.config import settings
from airweave.core.gateway_tenant import tenant_event_hooks
from airweave.core.logging import logger
from airweave.domains.ocr.mistral.models import (
    FileChunk,
    OcrResult,
)
from airweave.domains.ocr.pages import PAGE_JOIN
from airweave.domains.sync_pipeline.exceptions import SyncFailureError
from airweave.platform.rate_limiters import MistralRateLimiter

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

MAX_RETRIES = 5
RETRY_MIN_WAIT = 2  # seconds (lower than batch since direct calls are faster)
RETRY_MAX_WAIT = 30  # seconds
RETRY_MULTIPLIER = 2

# Concurrent OCR calls cap (can be higher than batch uploads since OCR is the bottleneck)
DEFAULT_OCR_CONCURRENCY = 10

# Gooclaim (T418): the gateway's OCR route takes the document inline as a data
# URL, so its media type has to be stated. Exactly the formats the converter
# hands over (models.SUPPORTED_EXTENSIONS) — no guessing.
_GATEWAY_MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors worth retrying (5xx, timeouts, rate limits).

    4xx client errors (401 Unauthorized, 403 Forbidden, 404, etc.) are
    permanent and will never succeed on retry — fail fast instead.
    """
    if isinstance(exc, HTTPStatusError):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return True


class MistralOcrClient:
    """Async client for Mistral's direct OCR API."""

    def __init__(self, concurrency: int = DEFAULT_OCR_CONCURRENCY) -> None:
        """Initialize the OCR client.

        Args:
            concurrency: Maximum number of concurrent OCR requests.
        """
        self._client: Any = None
        self._initialized = False
        self._rate_limiter = MistralRateLimiter()
        self._concurrency = concurrency
        # Gooclaim (T418): set when OCR goes through the LLM gateway (LiteLLM).
        self._gateway_url: Optional[str] = None
        self._gateway_key: Optional[str] = None

    # ------------------------------------------------------------------
    # Lazy client initialisation
    # ------------------------------------------------------------------

    def ensure_initialized(self) -> None:
        """Create the Mistral SDK client if not done yet.

        Raises:
            SyncFailureError: If the API key is missing or the SDK is not installed.
        """
        if self._initialized:
            return

        # Gooclaim (T418): through the LLM gateway when one is configured. Every
        # AI call goes through it (a provider key lives ONLY in the gateway), so
        # this mode needs no MISTRAL_API_KEY: the gateway key is ours, the gateway
        # holds Mistral's, and each page is billed to the tenant it was read for.
        gateway_url = os.getenv("LLM_GATEWAY_URL")
        if gateway_url:
            gateway_key = os.getenv("LLM_GATEWAY_API_KEY")
            if not gateway_key:
                raise SyncFailureError("LLM_GATEWAY_API_KEY required when LLM_GATEWAY_URL is set")
            self._gateway_url = gateway_url.rstrip("/")
            self._gateway_key = gateway_key
            self._client = httpx.AsyncClient(timeout=120.0, event_hooks=tenant_event_hooks())
            self._initialized = True
            logger.debug("Mistral OCR client initialized (through the LLM gateway)")
            return

        if not getattr(settings, "MISTRAL_API_KEY", None):
            raise SyncFailureError("MISTRAL_API_KEY required for document conversion")

        try:
            from mistralai import Mistral  # noqa: PLC0415

            self._client = Mistral(
                api_key=settings.MISTRAL_API_KEY,
                timeout_ms=120_000,  # 2 minutes per OCR call
            )
            self._initialized = True
            logger.debug("Mistral OCR client initialized")
        except ImportError:
            raise SyncFailureError("mistralai package required but not installed")

    # ------------------------------------------------------------------
    # Rate-limited + retried API call wrapper
    # ------------------------------------------------------------------

    async def _api_call(self, coro_fn: Callable[[], Any], operation_name: str = "ocr") -> Any:
        """Execute an async SDK call with rate-limiting and retry.

        Args:
            coro_fn: A zero-argument callable that returns a fresh coroutine
                     on each invocation. This ensures retries create a new
                     coroutine instead of re-awaiting a consumed one.
            operation_name: Label used in log messages.
        """

        @retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(MAX_RETRIES),
            wait=wait_exponential(
                multiplier=RETRY_MULTIPLIER, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT
            ),
            reraise=True,
        )
        async def _inner() -> Any:
            await self._rate_limiter.acquire()
            return await coro_fn()

        try:
            return await _inner()
        except Exception as exc:
            logger.warning(f"[MISTRAL_OCR] {operation_name} failed after retries: {exc}")
            raise

    # ------------------------------------------------------------------
    # Single file OCR
    # ------------------------------------------------------------------

    async def ocr_chunk(self, chunk: FileChunk) -> OcrResult:
        """Perform OCR on a single file chunk.

        Args:
            chunk: The chunk to process.

        Returns:
            An :class:`OcrResult` with the markdown content.

        Raises:
            Exception: If OCR fails after retries (propagates the underlying error).
        """
        file_name = os.path.basename(chunk.chunk_path)

        try:
            # 1. Read file content
            async with aiofiles.open(chunk.chunk_path, "rb") as fh:
                content = await fh.read()

            if self._gateway_url:
                ocr_resp = await self._api_call(
                    lambda: self._ocr_via_gateway(chunk, content),
                    operation_name=f"ocr_{file_name}",
                )
                markdown = self._extract_markdown(ocr_resp, file_name)
                logger.debug(f"OCR completed for {file_name} (through the LLM gateway)")
                return OcrResult(chunk=chunk, markdown=markdown)

            # 2. Upload file to get file_id
            file_resp = await self._api_call(
                lambda: self._client.files.upload_async(
                    file={"file_name": file_name, "content": content},
                    purpose="ocr",
                ),
                operation_name=f"upload_{file_name}",
            )

            # 3. Call direct OCR with file_id
            from mistralai.models import FileChunk as MistralFileChunk  # noqa: PLC0415

            ocr_resp = await self._api_call(
                lambda: self._client.ocr.process_async(
                    model="mistral-ocr-latest",
                    document=MistralFileChunk(file_id=file_resp.id),
                ),
                operation_name=f"ocr_{file_name}",
            )

            # 4. Extract markdown from pages
            markdown = self._extract_markdown(ocr_resp, file_name)

            # 5. Cleanup uploaded file (best effort)
            await self._delete_file(file_resp.id)

            logger.debug(f"OCR completed for {file_name}")
            return OcrResult(chunk=chunk, markdown=markdown)

        except Exception as exc:
            logger.error(f"OCR failed for {file_name}: {exc}")
            raise

    async def _ocr_via_gateway(self, chunk: FileChunk, content: bytes) -> dict[str, Any]:
        """Gooclaim (T418): one OCR call through the gateway's ``/v1/ocr``.

        The gateway does not proxy Mistral's Files API, so there is no upload,
        no ``file_id`` and nothing to delete afterwards: the document travels
        inline as a data URL (server to server — it never enters a model's
        context). Returns the Mistral-shaped JSON (``pages[].markdown``).
        """
        media_type = _GATEWAY_MEDIA_TYPES[chunk.extension]
        data_url = f"data:{media_type};base64,{base64.b64encode(content).decode('ascii')}"
        kind = "image_url" if chunk.is_image else "document_url"
        response = await self._client.post(
            f"{self._gateway_url}/v1/ocr",
            headers={"Authorization": f"Bearer {self._gateway_key}"},
            json={"model": "mistral-ocr-latest", "document": {"type": kind, kind: data_url}},
        )
        response.raise_for_status()  # HTTPStatusError → _is_retryable decides
        return response.json()

    # ------------------------------------------------------------------
    # Batch OCR with bounded concurrency
    # ------------------------------------------------------------------

    async def ocr_chunks(self, chunks: list[FileChunk]) -> list[OcrResult]:
        """Process multiple chunks with bounded concurrency.

        Args:
            chunks: List of chunks to OCR.

        Returns:
            List of :class:`OcrResult` objects (in same order as input).
        """
        if not chunks:
            return []

        semaphore = asyncio.Semaphore(self._concurrency)
        results: list[OcrResult | Exception] = [None] * len(chunks)  # type: ignore[assignment]

        async def _process_one(idx: int, chunk: FileChunk) -> None:
            async with semaphore:
                try:
                    results[idx] = await self.ocr_chunk(chunk)
                except Exception as exc:
                    results[idx] = exc

        await asyncio.gather(
            *[_process_one(i, c) for i, c in enumerate(chunks)],
        )

        # Separate successes from failures — failed chunks get OcrResult with error
        final_results: list[OcrResult] = []
        failed_count = 0

        for i, r in enumerate(results):
            file_name = os.path.basename(chunks[i].chunk_path)
            if isinstance(r, Exception):
                logger.error(f"OCR failed for {file_name}: {r}")
                final_results.append(OcrResult(chunk=chunks[i], markdown=None, error=str(r)))
                failed_count += 1
            elif r is None:
                logger.error(f"OCR failed for {file_name}: task did not complete")
                final_results.append(
                    OcrResult(chunk=chunks[i], markdown=None, error="task did not complete")
                )
                failed_count += 1
            else:
                final_results.append(r)

        if failed_count:
            logger.warning(
                f"OCR batch: {failed_count}/{len(chunks)} chunks failed "
                f"(continuing with {len(chunks) - failed_count} successful)"
            )

        logger.debug(
            f"OCR batch complete: {len(final_results) - failed_count}/{len(chunks)} succeeded"
        )
        return final_results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_markdown(ocr_resp: Any, file_name: str) -> Optional[str]:
        """Extract markdown text from OCR response."""
        # The SDK returns an object; the gateway route returns JSON (Gooclaim, T418).
        if isinstance(ocr_resp, dict):
            pages = ocr_resp.get("pages") or []
        else:
            pages = getattr(ocr_resp, "pages", None) or []

        if not pages:
            logger.warning(f"No pages in OCR response for {file_name}")
            return None

        # Gooclaim: every page in its place — an empty page too, or every page
        # after it would be numbered one short — joined by the page break, so a
        # chunk can say which page it came from (see domains/ocr/pages.py).
        markdown_parts = []
        for page in pages:
            if isinstance(page, dict):
                md = page.get("markdown") or ""
            else:
                md = getattr(page, "markdown", "") or ""
            markdown_parts.append(md)

        if not any(part.strip() for part in markdown_parts):
            logger.warning(f"OCR returned empty markdown for {file_name}")
            return ""

        return PAGE_JOIN.join(markdown_parts)

    async def _delete_file(self, file_id: str) -> None:
        """Best-effort deletion of uploaded file from Mistral."""
        try:
            await self._api_call(
                lambda: self._client.files.delete_async(file_id=file_id),
                operation_name=f"delete_{file_id[:8]}",
            )
        except Exception:
            pass  # Best effort
