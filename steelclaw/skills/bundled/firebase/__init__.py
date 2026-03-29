"""Firebase Firestore skill — interact with Firestore REST API."""

from __future__ import annotations

import json
import httpx

from steelclaw.skills.credential_store import get_all_credentials

required_credentials = [
    {"key": "project_id", "label": "Firebase Project ID", "type": "text"},
    {"key": "access_token", "label": "Firebase Access Token", "type": "password"},
]


def _config() -> dict:
    return get_all_credentials("firebase")


def _base_url() -> str:
    config = _config()
    project = config.get("project_id", "")
    return f"https://firestore.googleapis.com/v1/projects/{project}/databases/(default)/documents"


def _headers() -> dict:
    config = _config()
    token = config.get("access_token", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _value_to_firestore(val) -> dict:
    """Convert a Python value to Firestore Value format."""
    if isinstance(val, str):
        return {"stringValue": val}
    elif isinstance(val, bool):
        return {"booleanValue": val}
    elif isinstance(val, int):
        return {"integerValue": str(val)}
    elif isinstance(val, float):
        return {"doubleValue": val}
    elif val is None:
        return {"nullValue": None}
    elif isinstance(val, list):
        return {"arrayValue": {"values": [_value_to_firestore(v) for v in val]}}
    elif isinstance(val, dict):
        return {"mapValue": {"fields": {k: _value_to_firestore(v) for k, v in val.items()}}}
    return {"stringValue": str(val)}


def _firestore_to_value(fv: dict):
    """Convert a Firestore Value to Python value."""
    if "stringValue" in fv:
        return fv["stringValue"]
    elif "integerValue" in fv:
        return int(fv["integerValue"])
    elif "doubleValue" in fv:
        return fv["doubleValue"]
    elif "booleanValue" in fv:
        return fv["booleanValue"]
    elif "nullValue" in fv:
        return None
    elif "arrayValue" in fv:
        return [_firestore_to_value(v) for v in fv["arrayValue"].get("values", [])]
    elif "mapValue" in fv:
        return {k: _firestore_to_value(v) for k, v in fv["mapValue"].get("fields", {}).items()}
    return str(fv)


def _parse_document(doc: dict) -> dict:
    """Parse Firestore document into plain dict."""
    fields = doc.get("fields", {})
    name = doc.get("name", "")
    doc_id = name.rsplit("/", 1)[-1] if name else ""
    result = {"_id": doc_id}
    for key, val in fields.items():
        result[key] = _firestore_to_value(val)
    return result


async def tool_get_document(collection: str, document_id: str) -> str:
    """Get a single Firestore document."""
    config = _config()
    if not config.get("access_token") or not config.get("project_id"):
        return "Error: Firebase credentials not configured. Run: steelclaw skills configure firebase"
    url = f"{_base_url()}/{collection}/{document_id}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=_headers())
            resp.raise_for_status()
            doc = resp.json()
        parsed = _parse_document(doc)
        return f"Document **{collection}/{document_id}**:\n```json\n{json.dumps(parsed, indent=2, default=str)}\n```"
    except Exception as e:
        return f"Error: {e}"


async def tool_set_document(collection: str, document_id: str, data: str) -> str:
    """Create or update a Firestore document."""
    config = _config()
    if not config.get("access_token") or not config.get("project_id"):
        return "Error: Firebase credentials not configured. Run: steelclaw skills configure firebase"
    try:
        doc_data = json.loads(data)
    except json.JSONDecodeError:
        return "Error: Invalid JSON data."
    fields = {k: _value_to_firestore(v) for k, v in doc_data.items()}
    url = f"{_base_url()}/{collection}/{document_id}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(url, headers=_headers(), json={"fields": fields})
            resp.raise_for_status()
            doc = resp.json()
        parsed = _parse_document(doc)
        return f"Document set **{collection}/{document_id}**:\n```json\n{json.dumps(parsed, indent=2, default=str)}\n```"
    except Exception as e:
        return f"Error: {e}"


async def tool_list_documents(collection: str, page_size: int = 20) -> str:
    """List documents in a Firestore collection."""
    config = _config()
    if not config.get("access_token") or not config.get("project_id"):
        return "Error: Firebase credentials not configured. Run: steelclaw skills configure firebase"
    url = f"{_base_url()}/{collection}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=_headers(), params={"pageSize": page_size})
            resp.raise_for_status()
            data = resp.json()
        documents = data.get("documents", [])
        if not documents:
            return f"No documents found in {collection}."
        parsed = [_parse_document(doc) for doc in documents]
        return f"Documents in **{collection}** ({len(parsed)}):\n```json\n{json.dumps(parsed, indent=2, default=str)}\n```"
    except Exception as e:
        return f"Error: {e}"
