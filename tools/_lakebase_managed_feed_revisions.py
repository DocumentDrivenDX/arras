# SPDX-License-Identifier: MIT OR Apache-2.0
"""Selected Truss revision and document feed carrier validation."""

from __future__ import annotations

import base64
from typing import Any

from _lakebase_managed_common import Blocked as _Blocked
from _lakebase_managed_feed_codec import _SHA256, _XID, _json_bytes, _sha256


def _validate_revision(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
        "revision",
        "record",
        "documents",
        "reportBytesBase64",
        "reportSha256",
    }:
        raise _Blocked("feed_revision_profile_unknown")
    revision = value["revision"]
    record = value["record"]
    documents = value["documents"]
    if (
        type(revision) is not str
        or not _XID.fullmatch(revision)
        or type(record) is not dict
        or set(record) != {"rev", "accepted_at", "origin"}
        or type(record["rev"]) is not int
        or str(record["rev"]) != revision
        or type(record["accepted_at"]) is not str
        or type(record["origin"]) is not dict
        or type(documents) is not list
    ):
        raise _Blocked("feed_revision_profile_unknown")
    for document in documents:
        if type(document) is not dict or set(document) != {
            "rev",
            "ord",
            "doc_id",
            "doc_revision",
            "umf_version",
            "content_sha256",
            "document",
            "validation",
        }:
            raise _Blocked("feed_document_profile_unknown")
        source = document["document"]
        if (
            type(document["rev"]) is not int
            or document["rev"] != record["rev"]
            or type(document["ord"]) is not int
            or document["ord"] < 0
            or type(document["doc_id"]) is not str
            or not document["doc_id"]
            or type(document["doc_revision"]) is not str
            or type(document["umf_version"]) is not str
            or type(document["content_sha256"]) is not str
            or _SHA256.fullmatch(document["content_sha256"]) is None
            or type(source) is not str
            or _sha256(source.encode("utf-8")) != document["content_sha256"]
            or type(document["validation"]) is not dict
        ):
            raise _Blocked("feed_document_profile_unknown")
        parsed = _json_bytes(source.encode("utf-8"), "feed_document_profile_unknown")
        if type(parsed) is not dict or parsed.get("id") != document["doc_id"]:
            raise _Blocked("feed_document_profile_unknown")
    report_b64 = value["reportBytesBase64"]
    report_sha = value["reportSha256"]
    if revision == "0":
        if report_b64 is not None or report_sha is not None:
            raise _Blocked("feed_revision_report_mismatch")
    else:
        if (
            type(report_b64) is not str
            or type(report_sha) is not str
            or _SHA256.fullmatch(report_sha) is None
        ):
            raise _Blocked("feed_revision_report_mismatch")
        try:
            report = base64.b64decode(report_b64, validate=True)
        except (ValueError, TypeError):
            raise _Blocked("feed_revision_report_mismatch") from None
        if _sha256(report) != report_sha:
            raise _Blocked("feed_revision_report_mismatch")
    return value
