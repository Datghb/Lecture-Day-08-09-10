# Data contract — Lab Day 10

Contract nguồn chính: `contracts/data_contract.yaml`.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `policy_refund_v4` | Batch CSV export từ `data/raw/policy_export_dirty.csv`; canonical doc `data/docs/policy_refund_v4.txt` | Stale refund window `14 ngày`, duplicate chunk, ngày hiệu lực trước v4 | `refund_no_stale_14d_window`, `stale_doc_effective_date`, `duplicate_chunk_text` |
| `sla_p1_2026` | Batch CSV export; canonical doc `data/docs/sla_p1_2026.txt` | Chunk P2 gây nhiễu câu hỏi P1, missing date, duplicate escalation | `sla_p1_no_p2_chunk`, `required_doc_ids_present`, eval `gq_d10_06` |
| `it_helpdesk_faq` | Batch CSV export; canonical doc `data/docs/it_helpdesk_faq.txt` | Text rỗng, parser noise, duplicate FAQ | `chunk_min_length_8`, `no_parser_noise_markers`, eval `gq_d10_07`/`gq_d10_08` |
| `hr_leave_policy` | Batch CSV export; canonical doc `data/docs/hr_leave_policy.txt` | Conflict version HR 2025 `10 ngày phép năm` vs HR 2026 `12 ngày` | `hr_leave_no_stale_10d_annual`, `stale_hr_2025_annual_leave_text`, eval `gq_d10_09` |
| `access_control_sop` | Batch CSV export; canonical doc `data/docs/access_control_sop.txt` | Bị quarantine nhầm nếu thiếu allowlist, duplicate Level 4 | `required_doc_ids_present`, eval `gq_d10_10` |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| `chunk_id` | string | Có | Stable id sinh từ `doc_id`, cleaned text, sequence; dùng cho Chroma upsert/prune |
| `doc_id` | string | Có | Một trong 5 canonical doc id ở contract |
| `chunk_text` | string | Có | Text sau clean; tối thiểu 8 ký tự; không chứa parser noise |
| `effective_date` | date | Có | Chuẩn `YYYY-MM-DD`; phải đạt min effective date theo doc |
| `exported_at` | datetime | Có | ISO datetime; dùng làm watermark freshness trong manifest |

---

## 3. Quy tắc quarantine vs drop

Record không đạt contract được ghi vào `artifacts/quarantine/quarantine_<run_id>.csv` kèm `reason`. Pipeline không silently drop dữ liệu trước khi ghi quarantine.

Các reason chính trong run `final-submit`:

| Reason | Ý nghĩa |
|--------|---------|
| `unknown_doc_id` | Nguồn không thuộc allowlist/canonical source |
| `stale_doc_effective_date` | Record cũ hơn cutoff version của doc |
| `invalid_exported_at_format` | `exported_at` không phải ISO datetime |
| `missing_effective_date` / `missing_chunk_text` | Thiếu trường bắt buộc |
| `duplicate_chunk_text` | Trùng nội dung sau normalize |
| `stale_hr_2025_annual_leave_text` | HR 2025 `10 ngày phép năm` lọt vào export mới |
| `non_p1_sla_chunk` | Chunk P2 trong corpus `sla_p1_2026` |

SME/owner kiểm quarantine CSV trước khi quyết định sửa source, cập nhật allowlist, hoặc re-ingest.

---

## 4. Phiên bản & canonical

| Doc ID | Canonical source | Min effective date |
|--------|------------------|--------------------|
| `policy_refund_v4` | `data/docs/policy_refund_v4.txt` | `2026-02-01` |
| `sla_p1_2026` | `data/docs/sla_p1_2026.txt` | `2026-01-15` |
| `it_helpdesk_faq` | `data/docs/it_helpdesk_faq.txt` | `2026-01-20` |
| `hr_leave_policy` | `data/docs/hr_leave_policy.txt` | `2026-01-01` |
| `access_control_sop` | `data/docs/access_control_sop.txt` | `2026-01-01` |

Run chuẩn hiện tại: `final-submit`. Manifest: `artifacts/manifests/manifest_final-submit.json`.
