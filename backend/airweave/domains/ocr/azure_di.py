"""Azure Document Intelligence OCR adapter.

Calls Azure DI's ``prebuilt-read`` model via HTTP. The model accepts a wider
variety of document formats than Mistral and runs without an SDK dependency.

Satisfies the :class:`~airweave.core.protocols.ocr.OcrProvider` protocol.

Submit-and-poll pattern:
    1. ``POST /documentintelligence/documentModels/prebuilt-read:analyze``
       with the raw file bytes -> 202 Accepted + ``operation-location`` header.
    2. Poll the ``operation-location`` until ``status`` is ``succeeded``
       or ``failed``.
    3. Return ``analyzeResult.content`` as the markdown payload.
"""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles
import httpx

from airweave.core.logging import logger

# Azure DI prebuilt-read supports these (PDF, common Office, common images).
_SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tiff",
    ".tif",
    ".heif",
}

_API_VERSION = "2024-11-30"
_ANALYZE_PATH = (
    f"/documentintelligence/documentModels/prebuilt-read:analyze"
    f"?api-version={_API_VERSION}"
)


class AzureDIOCR:
    """Adapter for Azure Document Intelligence ``prebuilt-read`` model.

    Usage::

        ocr: OcrProvider = AzureDIOCR(endpoint="https://x.cognitiveservices.azure.com",
                                      key="...")
        results = await ocr.convert_batch(["/tmp/doc.pdf"])
    """

    def __init__(
        self,
        endpoint: str,
        key: str,
        concurrency: int = 5,
        poll_interval_s: float = 2.0,
        max_poll_s: float = 180.0,
        timeout_s: float = 60.0,
    ) -> None:
        """Initialize the adapter.

        Args:
            endpoint: Azure DI resource endpoint (e.g.
                ``https://x.cognitiveservices.azure.com``).
            key: Subscription key (``Ocp-Apim-Subscription-Key``).
            concurrency: Max concurrent file submissions.
            poll_interval_s: Seconds between status polls.
            max_poll_s: Maximum total seconds to wait for a single file.
            timeout_s: Per-HTTP-call timeout (covers upload + each poll).
        """
        if not endpoint or not key:
            raise ValueError("AzureDIOCR requires both endpoint and key")
        self._endpoint = endpoint.rstrip("/")
        self._key = key
        self._poll_interval_s = poll_interval_s
        self._max_poll_s = max_poll_s
        self._timeout_s = timeout_s
        self._semaphore = asyncio.Semaphore(concurrency)

    async def convert_batch(self, file_paths: List[str]) -> Dict[str, Optional[str]]:
        """Convert files to markdown via Azure DI.

        Args:
            file_paths: Local file paths.

        Returns:
            Mapping of ``file_path -> markdown`` (``None`` on per-file failure).
        """
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            results = await asyncio.gather(
                *(self._convert_one(client, p) for p in file_paths),
                return_exceptions=True,
            )

        out: Dict[str, Optional[str]] = {}
        for path, value in zip(file_paths, results):
            if isinstance(value, BaseException):
                logger.warning(f"[AzureDIOCR] Failed {path}: {value}")
                out[path] = None
            else:
                out[path] = value
        return out

    async def _convert_one(
        self, client: httpx.AsyncClient, file_path: str
    ) -> Optional[str]:
        """Submit one file, poll until done, return extracted content."""
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            logger.warning(f"[AzureDIOCR] Unsupported file type: {ext}")
            return None

        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

        async with self._semaphore:
            async with aiofiles.open(file_path, "rb") as fh:
                body = await fh.read()

            submit_resp = await client.post(
                f"{self._endpoint}{_ANALYZE_PATH}",
                headers={
                    "Ocp-Apim-Subscription-Key": self._key,
                    "Content-Type": content_type,
                },
                content=body,
            )
            submit_resp.raise_for_status()
            op_url = submit_resp.headers.get("operation-location")
            if not op_url:
                logger.warning(
                    f"[AzureDIOCR] No operation-location header for {path.name}"
                )
                return None

            return await self._poll(client, op_url, path.name)

    async def _poll(
        self, client: httpx.AsyncClient, op_url: str, file_name: str
    ) -> Optional[str]:
        """Poll the analyze-results URL until terminal state."""
        deadline = asyncio.get_event_loop().time() + self._max_poll_s
        while True:
            poll_resp = await client.get(
                op_url, headers={"Ocp-Apim-Subscription-Key": self._key}
            )
            poll_resp.raise_for_status()
            payload = poll_resp.json()
            status = payload.get("status")

            if status == "succeeded":
                content = payload.get("analyzeResult", {}).get("content")
                if not content:
                    logger.warning(f"[AzureDIOCR] Empty content for {file_name}")
                    return None
                return content

            if status == "failed":
                err = payload.get("error", {})
                logger.warning(
                    f"[AzureDIOCR] Analysis failed for {file_name}: "
                    f"{err.get('code')} {err.get('message')}"
                )
                return None

            if asyncio.get_event_loop().time() >= deadline:
                logger.warning(
                    f"[AzureDIOCR] Poll deadline exceeded ({self._max_poll_s}s) "
                    f"for {file_name}"
                )
                return None

            await asyncio.sleep(self._poll_interval_s)
