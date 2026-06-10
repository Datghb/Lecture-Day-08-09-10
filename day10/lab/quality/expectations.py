"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


REQUIRED_DOC_IDS = {
    "policy_refund_v4",
    "sla_p1_2026",
    "it_helpdesk_faq",
    "hr_leave_policy",
    "access_control_sop",
}

_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?$")


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # E7 mới: cleaned corpus phải còn đủ 5 nguồn canonical cần cho grading.
    present_doc_ids = {str(r.get("doc_id") or "").strip() for r in cleaned_rows}
    missing_doc_ids = sorted(REQUIRED_DOC_IDS - present_doc_ids)
    results.append(
        ExpectationResult(
            "required_doc_ids_present",
            len(missing_doc_ids) == 0,
            "halt",
            f"missing_doc_ids={missing_doc_ids}",
        )
    )

    # E8 mới: chunk_id phải duy nhất để upsert/prune idempotent không đè nhầm vector.
    chunk_ids = [str(r.get("chunk_id") or "").strip() for r in cleaned_rows]
    duplicate_chunk_ids = sorted([cid for cid, count in Counter(chunk_ids).items() if cid and count > 1])
    empty_chunk_ids = [cid for cid in chunk_ids if not cid]
    results.append(
        ExpectationResult(
            "unique_non_empty_chunk_id",
            not duplicate_chunk_ids and not empty_chunk_ids,
            "halt",
            f"duplicate_chunk_ids={len(duplicate_chunk_ids)} empty_chunk_ids={len(empty_chunk_ids)}",
        )
    )

    # E9 mới: exported_at cũng phải là ISO datetime, không chỉ effective_date.
    exported_bad = [
        r
        for r in cleaned_rows
        if not _ISO_DATETIME.match(str(r.get("exported_at") or "").strip())
    ]
    results.append(
        ExpectationResult(
            "exported_at_iso_datetime",
            len(exported_bad) == 0,
            "halt",
            f"non_iso_exported_at_rows={len(exported_bad)}",
        )
    )

    # E10 mới: marker nhiễu parser không được lọt vào context retrieval.
    noise_bad = [
        r
        for r in cleaned_rows
        if re.search(r"Nội dung không rõ ràng|!!!", str(r.get("chunk_text") or ""))
    ]
    results.append(
        ExpectationResult(
            "no_parser_noise_markers",
            len(noise_bad) == 0,
            "halt",
            f"violations={len(noise_bad)}",
        )
    )

    # E11 mới: corpus sla_p1_2026 trong lab không được chứa SLA P2 gây nhiễu câu P1 escalation.
    non_p1_sla = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "sla_p1_2026"
        and str(r.get("chunk_text") or "").startswith("Ticket P2:")
    ]
    results.append(
        ExpectationResult(
            "sla_p1_no_p2_chunk",
            len(non_p1_sla) == 0,
            "halt",
            f"violations={len(non_p1_sla)}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt
