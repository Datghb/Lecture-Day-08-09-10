# Runbook — Lab Day 10

---

## Symptom

Agent/retriever trả lời sai do data layer:

- Refund window trả lời `14 ngày` thay vì `7 ngày làm việc`.
- HR leave trả lời `10 ngày phép năm` thay vì HR 2026 `12 ngày phép năm`.
- Câu Level 4 Admin Access không tìm thấy `IT Manager` / `CISO`.
- Câu P1 escalation không lấy được `10 phút` vì chunk P2 escalation lấn top-k.
- Freshness báo `FAIL` dù pipeline chạy `PIPELINE_OK`.

---

## Detection

| Tín hiệu | Cách kiểm | Kỳ vọng |
|----------|-----------|---------|
| Expectation halt | `python etl_pipeline.py run` | Không có expectation severity `halt` fail |
| Retrieval grading | `python grading_run.py --out artifacts/eval/grading_run.jsonl` | 10/10 câu `contains_expected=true`, `hits_forbidden=false` |
| Forbidden stale text | `python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv` | Không có `hits_forbidden=yes` |
| Freshness | `python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_final-submit.json` | PASS nếu snapshot trong SLA; FAIL nếu snapshot mẫu quá cũ |
| Quarantine spike | Mở `artifacts/quarantine/quarantine_<run_id>.csv` | Reason giải thích được và khớp contract |

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Kiểm tra `artifacts/manifests/manifest_<run_id>.json` | Có `run_id`, `raw_records`, `cleaned_records`, `quarantine_records`, `latest_exported_at` |
| 2 | Mở `artifacts/logs/run_<run_id>.log` | Thấy expectation nào FAIL hoặc `PIPELINE_OK` |
| 3 | Mở `artifacts/quarantine/quarantine_<run_id>.csv` | Reason như `stale_doc_effective_date`, `unknown_doc_id`, `non_p1_sla_chunk` |
| 4 | Chạy `python grading_run.py --out artifacts/eval/grading_run.jsonl` | Xác định câu nào fail: refund, HR, access control, SLA |
| 5 | Nếu top-k sai, query Chroma hoặc xem `artifacts/eval/*.csv` | Xem `top1_doc_id`, `contains_expected`, `hits_forbidden` |

---

## Mitigation

1. Nếu expectation fail: sửa `transform/cleaning_rules.py` hoặc `quality/expectations.py`, không dùng `--skip-validate` cho run nộp bài.
2. Nếu index có chunk stale: chạy lại `python etl_pipeline.py run --run-id <new-run>` để upsert snapshot mới và prune vector cũ.
3. Nếu thiếu source hợp lệ: thêm doc_id vào `ALLOWED_DOC_IDS`, `contracts/data_contract.yaml`, và expectation `required_doc_ids_present`.
4. Nếu freshness fail do snapshot thật quá cũ: báo owner nguồn dữ liệu, tạm cảnh báo data stale, rồi re-export/re-ingest.
5. Nếu freshness fail do lab sample: ghi rõ trong report rằng `latest_exported_at=2026-04-11T00:00:00` cũ hơn SLA 24h khi chạy ngày 2026-06-10.

---

## Prevention

- Giữ allowlist, canonical source và contract YAML đồng bộ.
- Bắt buộc chạy `grading_run.py` sau mỗi thay đổi cleaning/expectation.
- Không publish khi expectation severity `halt` fail.
- Ghi `run_id` trong log, manifest, cleaned/quarantine CSV và metadata Chroma.
- Theo dõi freshness ở boundary publish; production nên thêm boundary ingest để phân biệt source stale và embed stale.
- Thêm golden questions khi có policy mới hoặc nguồn mới.
