# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** AI in Action Day 10 lab team  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| ___ | Ingestion / Raw Owner | ___ |
| ___ | Cleaning & Quality Owner | ___ |
| ___ | Embed & Idempotency Owner | ___ |
| ___ | Monitoring / Docs Owner | ___ |

**Ngày nộp:** 2026-06-10  
**Repo:** `Lecture-Day-08-09-10`  

---

## 1. Pipeline tổng quan

Raw source là `data/raw/policy_export_dirty.csv`, mô phỏng export bẩn từ nhiều hệ thống CS, IT Helpdesk, HR và IT Security. Pipeline chạy theo luồng: ingest CSV, clean/quarantine, validate bằng expectation suite, publish snapshot vào Chroma collection `day10_kb`, ghi manifest và chạy freshness check. Run chuẩn hiện tại là `final-submit`; log/manifest ghi `raw_records=247`, `cleaned_records=27`, `quarantine_records=220`, `embed_upsert count=27`.

**Lệnh chạy một dòng:**

```bash
python etl_pipeline.py run --run-id final-submit && python grading_run.py --out artifacts/eval/grading_run.jsonl
```

---

## 2. Cleaning & expectation

Nhóm sửa allowlist để giữ đủ 5 nguồn canonical, gồm `access_control_sop`. Cleaning mở rộng thêm version cutoff theo từng doc, kiểm `exported_at` ISO datetime, dọn parser noise, quarantine HR 2025 stale text, loại chunk P2 khỏi corpus SLA P1 và canonicalize wording P1 escalation. Expectation mới đều là `halt` vì các lỗi này ảnh hưởng trực tiếp tới retrieval/grading.

### 2a. Bảng metric_impact

| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau / khi inject (số liệu) | Chứng cứ (log / CSV / commit) |
|-----------------------------------|------------------|-----------------------------|-------------------------------|
| `access_control_sop_allowlist` | `access_control_sop` bị `unknown_doc_id`, `gq_d10_10` không thể pass | Cleaned có 5 chunk `access_control_sop`; `gq_d10_10` OK | `artifacts/cleaned/cleaned_final-submit.csv`, `artifacts/eval/grading_run.jsonl` |
| `stale_doc_effective_date` | Nhiều record trước canonical version có thể lọt nếu chỉ check HR đặc biệt | `stale_doc_effective_date=77` trong quarantine | `artifacts/quarantine/quarantine_final-submit.csv` |
| `invalid_exported_at_format` | Dòng `exported_at` dạng `2026/04/...` không bị bắt | `invalid_exported_at_format=7` trong quarantine | `artifacts/quarantine/quarantine_final-submit.csv` |
| `stale_hr_2025_annual_leave_text` | HR `10 ngày phép năm` có thể lọt dù effective_date mới | `stale_hr_2025_annual_leave_text=6`; `gq_d10_09` OK | `artifacts/quarantine/quarantine_final-submit.csv`, `artifacts/eval/grading_run.jsonl` |
| `sla_p1_no_p2_chunk` | `gq_d10_06` từng fail vì chunk P2 `90 phút` đứng trên chunk P1 `10 phút` | `non_p1_sla_chunk=1`; `gq_d10_06` OK | `artifacts/quarantine/quarantine_final-submit.csv`, `artifacts/eval/grading_run.jsonl` |
| `required_doc_ids_present` | Baseline thiếu `access_control_sop` trong cleaned corpus | Expectation OK: `missing_doc_ids=[]` | `artifacts/logs/run_final-submit.log` |
| `unique_non_empty_chunk_id` | Chưa có gate đảm bảo idempotent upsert | Expectation OK: duplicate `0`, empty `0` | `artifacts/logs/run_final-submit.log` |
| `no_parser_noise_markers` | Marker `Nội dung không rõ ràng` / `!!!` có thể lọt vào retrieval | Expectation OK: violations `0` | `artifacts/logs/run_final-submit.log` |

**Rule chính:**

- Allowlist canonical: `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`, `access_control_sop`.
- Quarantine unknown doc, missing date/text, invalid exported_at, stale effective_date, stale HR 2025, duplicate chunk, non-P1 SLA chunk.
- Normalize date `DD/MM/YYYY` sang `YYYY-MM-DD`, remove parser noise, collapse repeated words, fix refund `14 ngày làm việc` thành `7 ngày làm việc`.

**Ví dụ expectation fail và cách xử lý:**

Trước khi loại chunk P2, grading `gq_d10_06` không chứa `10 phút` trong top-k. Nhóm thêm rule `non_p1_sla_chunk` và expectation `sla_p1_no_p2_chunk`; rerun `final-submit` cho kết quả `gq_d10_06 OK`.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent

Trong run sau fix, `artifacts/eval/grading_run.jsonl` có đủ 10 dòng `gq_d10_01` đến `gq_d10_10`; tất cả `contains_expected=true`, `hits_forbidden=false`, và `top1_doc_matches=true` với các câu có `expect_top1_doc_id`.

**Kịch bản inject:**

Nhóm tạo raw inject `artifacts/eval/policy_export_inject_stale_refund.csv` bằng cách thêm một dòng `policy_refund_v4` có effective date hợp lệ nhưng chứa cửa sổ stale `14 ngày làm việc`. Run inject cố ý dùng `--no-refund-fix --skip-validate`:

```bash
python etl_pipeline.py run --run-id inject-bad-refund14 --raw "$PWD/artifacts/eval/policy_export_inject_stale_refund.csv" --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
python etl_pipeline.py run --run-id final-submit
python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
```

**Kết quả định lượng hiện có:**

- Inject run: `artifacts/logs/run_inject-bad-refund14.log` có `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`, nhưng vẫn publish vì `--skip-validate`.
- Before/inject eval: `artifacts/eval/after_inject_bad.csv` có `q_refund_window` với `contains_expected=yes` nhưng `hits_forbidden=yes`.
- Inject grading: `artifacts/eval/grading_inject_bad.jsonl` fail `gq_d10_01`.
- Final fix eval: `artifacts/eval/after_fix_eval.csv` có `q_refund_window` với `hits_forbidden=no`.
- Final grading: `artifacts/eval/grading_run.jsonl` pass 10/10 grading questions.
- Restore evidence: run `final-submit` sau inject có `embed_prune_removed=1`, nghĩa là vector stale inject đã bị prune khỏi index.

---

## 4. Freshness & monitoring

Freshness đo tại boundary publish thông qua manifest. Run `final-submit` ghi `latest_exported_at=2026-04-11T00:00:00` và SLA là 24 giờ. Khi chạy vào ngày 2026-06-10, `freshness_check=FAIL` với `reason=freshness_sla_exceeded`; đây là hành vi đúng với snapshot mẫu cũ. Trong production, FAIL này sẽ báo owner nguồn dữ liệu re-export/re-ingest, còn trong lab cần ghi rõ để phân biệt pipeline quality pass với data freshness fail.

---

## 5. Liên hệ Day 09

Corpus sau embed phục vụ cùng case Day 08-09 về CS + IT Helpdesk, nhưng dùng collection riêng `day10_kb`. Cách tách này tránh ảnh hưởng collection/ngữ cảnh của Day 09 trong lúc làm thí nghiệm inject corruption, nhưng vẫn giữ cùng domain tài liệu để chứng minh agent chỉ trả lời tốt khi data path sạch và đúng version.

---

## 6. Rủi ro còn lại & việc chưa làm

- Chưa tích hợp Great Expectations/pydantic schema thật; expectation hiện là custom Python.
- Freshness chỉ đo manifest publish, chưa đo đủ ingest boundary.
- Version cutoff đang khai báo song song trong code và contract; production nên đọc từ contract/env.
- Self eval `after_fix_eval.csv` còn là keyword retrieval, chưa có LLM-judge.
