"""Labels on a library document (Gooclaim, T531): which insurance product it covers.

A member's answer must come from THEIR policy's wording, and a tenant's library holds
several insurers' wordings. Each uploaded document therefore says which product(s) it
covers — by the product's IRDAI UIN, printed on page 1 of every policy wording, prospectus
and customer information sheet — or that it applies to every member ("general").

    at upload       the UIN(s) printed on the first pages are READ (`detect_uins`) and kept
                    as a suggestion (`detected_uins`) — nothing is decided by the reader
    the tenant      confirms or changes them (`product_uins`, `applies_to`) in the upload
                    screen; only a confirmed label scopes a search
    a search        Gooclaim's datasources MCP lists these labels and leaves out the
                    documents labelled for OTHER products (Airweave only finds)

The labels live in the file's sidecar, next to the file, so they travel with it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

#: An IRDAI product UIN as printed on a wording: the insurer's and the line's letters,
#: five digits, "V", six digits (e.g. GODHLIP24179V022324, UNIHLGP25038V042425).
UIN_PATTERN = re.compile(r"\b[A-Z]{5,9}\d{5}V\d{6}\b")
#: How much of a document is read for its UIN — it is printed on the first pages.
FIRST_PAGES = 2
_TEXT_CHARS = 20_000
_TEXT_EXTENSIONS = frozenset({".txt", ".md", ".html", ".htm", ".csv", ".json"})

AppliesTo = Literal["products", "general"]


def normalise_uin(value: str) -> str:
    """One spelling: no spaces, upper case — as matched against a member's policy."""
    return re.sub(r"\s+", "", value).upper()


def detect_uins(text: str) -> list[str]:
    """The UINs printed in this text, first seen first, at most five."""
    found: list[str] = []
    for match in UIN_PATTERN.findall(normalise_spaces(text).upper()):
        if match not in found:
            found.append(match)
    return found[:5]


def normalise_spaces(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text or "")


def first_pages_text(path: Path) -> str:
    """The text of the document's first pages, or "" when it cannot be read here.

    A scanned page has no text layer and Word files are read at sync time. Never raises.
    """
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            import fitz  # PyMuPDF  # noqa: PLC0415

            with fitz.open(str(path)) as doc:
                return "\n".join(doc[i].get_text() for i in range(min(FIRST_PAGES, len(doc))))
        if ext in _TEXT_EXTENSIONS:
            return path.read_text(encoding="utf-8", errors="ignore")[:_TEXT_CHARS]
    except Exception:  # an unreadable file is simply not labelled for the tenant
        return ""
    return ""


class DocumentLabels(BaseModel):
    """What the tenant confirmed a document covers."""

    #: The products (IRDAI UINs) this document is the wording, prospectus or CIS of.
    product_uins: list[str] = Field(default_factory=list, max_length=20)
    #: "products" = only members of those products; "general" = every member.
    applies_to: Optional[AppliesTo] = None

    @field_validator("product_uins")
    @classmethod
    def _uins(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for raw in value:
            uin = normalise_uin(raw)
            if not UIN_PATTERN.fullmatch(uin):
                raise ValueError("not an IRDAI UIN")
            if uin not in out:
                out.append(uin)
        return out


def labels_of(sidecar: dict[str, Any]) -> dict[str, Any]:
    """The label fields of a sidecar, as an upload listing returns them."""
    return {
        "detected_uins": list(sidecar.get("detected_uins") or []),
        "product_uins": list(sidecar.get("product_uins") or []),
        "applies_to": sidecar.get("applies_to"),
    }


def write_labels(sidecar_path: Path, labels: DocumentLabels) -> dict[str, Any]:
    """Confirmed labels into the file's sidecar; the rest of the sidecar is kept."""
    sidecar: dict[str, Any] = {}
    if sidecar_path.is_file():
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            sidecar = {}
    applies_to = labels.applies_to or ("products" if labels.product_uins else "general")
    sidecar["product_uins"] = labels.product_uins if applies_to == "products" else []
    sidecar["applies_to"] = applies_to
    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")
    return sidecar


__all__ = [
    "FIRST_PAGES",
    "UIN_PATTERN",
    "DocumentLabels",
    "detect_uins",
    "first_pages_text",
    "labels_of",
    "normalise_uin",
    "write_labels",
]
