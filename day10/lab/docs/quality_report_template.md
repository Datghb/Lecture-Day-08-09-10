# Quality report — Lab Day 10

**run_id:** `final-submit`  
**Ngày:** 2026-06-10

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước | Sau | Ghi chú |
|--------|-------|-----|---------|
| raw_records | 247 | 247 | Raw CSV không đổi |
| cleaned_records | 40 | 27 | Sau khi thêm version cutoff, access control, noise cleanup, SLA P2 quarantine |
| quarantine_records | 207 | 220 | Quarantine tăng vì bắt thêm stale/effective/exported_at/P2 |
| Expectation halt? | Có nguy cơ halt với HR stale / refund inject | Không | Run `final-submit` tất cả expectation severity `halt` đều OK |

Run cuối ghi trong `artifacts/logs/run_final-submit.log`:

- `cleaned_records=27`
- `quarantine_records=220`
- `embed_upsert count=27`
- `PIPELINE_OK`

---

## 2. Before / after retrieval

File sau fix: `artifacts/eval/after_fix_eval.csv`  
Grading chính thức: `artifacts/eval/grading_run.jsonl`

**Câu hỏi then chốt:** refund window (`gq_d10_01`)  
**Trước:** inject `inject-bad-refund14` thêm một dòng refund stale `14 ngày làm việc`; log có `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`, `after_inject_bad.csv` có `q_refund_window` với `hits_forbidden=yes`, và `grading_inject_bad.jsonl` fail `gq_d10_01`.  
**Sau:** `gq_d10_01` OK trong `grading_run.jsonl`: `contains_expected=true`, `hits_forbidden=false`, `top1_doc_id=policy_refund_v4`.

**Versioning HR:** `gq_d10_09`  
**Trước:** raw có nhiều chunk HR 2025 `10 ngày phép năm`, một số có effective date mới nên không thể chỉ dựa vào ngày.  
**Sau:** rule `stale_hr_2025_annual_leave_text` quarantine 6 dòng; `gq_d10_09` OK: có `12 ngày phép năm`, không hit forbidden `10 ngày phép`.

**Access control:** `gq_d10_10`  
**Trước:** `access_control_sop` bị loại vì thiếu allowlist.  
**Sau:** cleaned có 5 chunk `access_control_sop`; `gq_d10_10` OK với `IT Manager` / `CISO`.

---

## 3. Freshness & monitor

Lệnh kiểm:

```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_final-submit.json
```

Kết quả hiện tại là `FAIL` vì `latest_exported_at=2026-04-11T00:00:00`, còn SLA là 24 giờ và bài chạy ngày 2026-06-10. Đây là expected failure của dữ liệu mẫu, không phải lỗi expectation/embedding.

---

## 4. Corruption inject

Kịch bản inject đã chạy:

```bash
python etl_pipeline.py run --run-id inject-bad-refund14 --raw "$PWD/artifacts/eval/policy_export_inject_stale_refund.csv" --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
```

Mục tiêu inject là cố ý publish chunk refund stale `14 ngày làm việc`. Kết quả:

- `artifacts/logs/run_inject-bad-refund14.log`: expectation refund stale fail với `violations=1`.
- `artifacts/eval/after_inject_bad.csv`: `q_refund_window` có `hits_forbidden=yes`.
- `artifacts/eval/grading_inject_bad.jsonl`: `gq_d10_01` fail.
- Sau khi chạy lại `final-submit`, `artifacts/eval/after_fix_eval.csv` có `q_refund_window` với `hits_forbidden=no`, và final grading 10/10 OK.
- Log final có `embed_prune_removed=1`, xác nhận vector stale inject đã bị xóa khỏi snapshot publish sạch.

---

## 5. Hạn chế & việc chưa làm

- Freshness chỉ đo theo manifest publish; production nên thêm ingest boundary.
- Quality suite là custom Python, chưa dùng Great Expectations.
- Eval hiện là retrieval + keyword, chưa có LLM-judge.
- Version cutoff đang được khai báo trong code và contract; nên gom về một nguồn cấu hình duy nhất ở bản production.
