# README nộp bài — Lab Day 10: Data Pipeline & Data Observability

## 1. Mục tiêu của bài lab

Mục tiêu chính của Lab Day 10 là xây dựng một pipeline dữ liệu (quy trình tự động đọc, làm sạch, kiểm tra và xuất bản dữ liệu) để đảm bảo AI/RAG (hệ thống hỏi đáp dựa trên tài liệu) chỉ đọc dữ liệu sạch, đúng phiên bản và có bằng chứng kiểm tra.

Trong bài này, lỗi không nằm ở prompt (câu lệnh đưa cho AI) hay model (mô hình AI), mà nằm ở data layer (tầng dữ liệu). Nếu dữ liệu sai hoặc cũ được đưa vào vector database (cơ sở dữ liệu lưu văn bản dưới dạng số để tìm kiếm theo ý nghĩa), AI có thể trả lời sai dù model vẫn hoạt động bình thường.

Ví dụ quan trọng của bài:

- Chính sách refund hiện hành là `7 ngày làm việc`, nhưng raw data có lẫn thông tin cũ `14 ngày làm việc`.
- HR policy hiện hành là `12 ngày phép năm`, nhưng raw data có lẫn bản cũ `10 ngày phép năm`.
- Tài liệu `access_control_sop` là nguồn hợp lệ nhưng baseline chưa đưa vào allowlist (danh sách tài liệu được phép xử lý).

---

## 2. Luồng xử lý tổng thể

```text
Raw CSV bẩn
  -> Ingest
  -> Clean
  -> Quarantine dữ liệu lỗi
  -> Validate bằng expectations
  -> Embed vào Chroma
  -> Ghi log + manifest
  -> Eval / grading
  -> Inject dữ liệu xấu để chứng minh before/after
```

Giải thích thuật ngữ:

- Raw CSV: file dữ liệu gốc, chưa làm sạch.
- Ingest: đọc dữ liệu đầu vào vào chương trình.
- Clean: làm sạch dữ liệu.
- Quarantine: cách ly dữ liệu lỗi để kiểm tra, không xóa âm thầm.
- Validate: kiểm tra dữ liệu có đạt luật chất lượng không.
- Expectation: luật kỳ vọng dữ liệu phải đạt.
- Embed: chuyển văn bản thành vector (dãy số biểu diễn ý nghĩa của văn bản).
- Chroma: vector database được dùng trong lab.
- Eval: đánh giá kết quả truy xuất dữ liệu.
- Grading: bộ chấm chính thức của lab.
- Manifest: file tóm tắt một lần chạy pipeline.
- Log: file ghi lại từng bước pipeline đã làm gì.

---

## 3. Những file chính đã sử dụng

| File / thư mục | Vai trò |
|----------------|--------|
| `data/raw/policy_export_dirty.csv` | Dữ liệu thô có nhiều lỗi cố ý |
| `transform/cleaning_rules.py` | Nơi viết rule làm sạch dữ liệu |
| `quality/expectations.py` | Nơi viết luật kiểm tra chất lượng dữ liệu |
| `etl_pipeline.py` | Entry point chạy pipeline ingest -> clean -> validate -> embed |
| `eval_retrieval.py` | Tự kiểm retrieval bằng 21 câu hỏi |
| `grading_run.py` | Chạy 10 câu grading chính thức |
| `contracts/data_contract.yaml` | Data contract (hợp đồng mô tả schema, source, quality rule) |
| `docs/*.md` | Tài liệu kiến trúc, contract, runbook và quality report |
| `reports/group_report.md` | Báo cáo nhóm và bảng metric impact |
| `artifacts/` | Nơi lưu log, cleaned data, quarantine, manifest và eval result |

---

## 4. Setup môi trường

Đã tạo virtual environment (môi trường Python riêng cho project):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Trong `requirements.txt`, có thêm:

- `numpy<2`: để tránh lỗi tương thích giữa Chroma 0.4.x và NumPy 2.x.
- `grpcio==1.63.2`: để tránh kéo bản gRPC mới hơn gây warning/platform issue trên macOS Python 3.9.

Lý do chọn cách này:

- Giữ môi trường ổn định, chạy lại được.
- Tránh lỗi dependency (thư viện phụ thuộc) làm pipeline không chạy.
- Không thay đổi logic bài lab chỉ vì lỗi môi trường.

---

## 5. Phần cleaning đã làm

File chỉnh chính:

```text
transform/cleaning_rules.py
```

### 5.1. Thêm `access_control_sop` vào allowlist

Baseline chỉ cho phép 4 tài liệu:

- `policy_refund_v4`
- `sla_p1_2026`
- `it_helpdesk_faq`
- `hr_leave_policy`

Nhưng grading có câu `gq_d10_10` hỏi về Level 4 Admin Access, cần tài liệu:

```text
access_control_sop
```

Vì vậy đã thêm `access_control_sop` vào allowlist.

Lý do chọn:

- Đây là source hợp lệ.
- Nếu không thêm, pipeline sẽ quarantine nhầm tài liệu này.
- Câu grading về access control chắc chắn fail nếu thiếu tài liệu này.

### 5.2. Thêm cutoff `effective_date` theo từng tài liệu

Cutoff nghĩa là mốc ngày tối thiểu được chấp nhận.

Ví dụ:

| Doc ID | Min effective date |
|--------|--------------------|
| `policy_refund_v4` | `2026-02-01` |
| `sla_p1_2026` | `2026-01-15` |
| `it_helpdesk_faq` | `2026-01-20` |
| `hr_leave_policy` | `2026-01-01` |
| `access_control_sop` | `2026-01-01` |

Lý do chọn:

- Dữ liệu raw có nhiều dòng cũ.
- Chỉ dựa vào `doc_id` là chưa đủ, vì cùng một doc có thể có nhiều phiên bản.
- Cutoff giúp loại các record thuộc phiên bản cũ.

### 5.3. Kiểm tra `exported_at`

`exported_at` là thời điểm dữ liệu được export từ hệ thống nguồn.

Rule mới yêu cầu `exported_at` phải đúng ISO datetime (định dạng thời gian chuẩn như `2026-04-11T00:00:00`).

Lý do chọn:

- Freshness check (kiểm tra dữ liệu mới hay cũ) phụ thuộc vào timestamp này.
- Nếu timestamp sai format, pipeline không thể đánh giá độ mới dữ liệu đáng tin cậy.

### 5.4. Dọn parser noise

Parser noise nghĩa là ký tự hoặc cụm từ rác sinh ra khi đọc/chuyển đổi tài liệu.

Ví dụ:

```text
Nội dung không rõ ràng:
!!!
```

Lý do chọn:

- Những marker này không phải nội dung nghiệp vụ.
- Nếu đưa vào vector database, AI có thể lấy context xấu hoặc khó đọc.

### 5.5. Gộp lỗi lặp từ/cụm từ

Ví dụ raw có:

```text
7 ngày làm việc làm việc
```

Đã normalize thành:

```text
7 ngày làm việc
```

Lý do chọn:

- Đây là lỗi dữ liệu thường gặp khi export/parser.
- Làm sạch giúp retrieval dễ khớp với câu hỏi hơn.

### 5.6. Quarantine HR policy cũ

Raw có nhiều dòng:

```text
10 ngày phép năm
```

Trong khi HR policy 2026 đúng là:

```text
12 ngày phép năm
```

Đã thêm rule quarantine nếu `hr_leave_policy` còn text `10 ngày phép năm`.

Lý do chọn:

- Một số dòng HR cũ có effective date mới, nên chỉ check ngày là chưa đủ.
- Cần check cả nội dung để bắt conflict version.

### 5.7. Loại chunk P2 khỏi corpus SLA P1

Chunk nghĩa là một đoạn nhỏ của tài liệu.

Raw có chunk:

```text
Ticket P2: ... Escalation sau 90 phút ...
```

Trong khi câu grading hỏi P1 escalation:

```text
P1 auto escalate sau 10 phút
```

Đã quarantine chunk P2 khỏi corpus `sla_p1_2026`.

Lý do chọn:

- Chunk P2 làm nhiễu retrieval.
- Trước khi sửa, câu `gq_d10_06` không lấy được `10 phút` trong top-k.
- Sau khi loại P2, `gq_d10_06` pass.

---

## 6. Expectations đã thêm

File chỉnh chính:

```text
quality/expectations.py
```

Đã thêm 5 expectation mới:

| Expectation | Ý nghĩa | Vì sao cần |
|-------------|---------|------------|
| `required_doc_ids_present` | Kiểm tra cleaned data có đủ 5 tài liệu canonical | Tránh thiếu `access_control_sop` hoặc nguồn quan trọng |
| `unique_non_empty_chunk_id` | Kiểm tra `chunk_id` không rỗng và không trùng | Đảm bảo upsert vào Chroma không đè nhầm |
| `exported_at_iso_datetime` | Kiểm tra `exported_at` đúng format | Đảm bảo freshness check đáng tin cậy |
| `no_parser_noise_markers` | Không còn marker rác như `!!!` | Tránh đưa dữ liệu rác vào AI |
| `sla_p1_no_p2_chunk` | Không để chunk P2 trong corpus P1 | Tránh câu P1 escalation bị nhiễu bởi P2 |

Lý do chọn các expectation này:

- Chúng bắt đúng các lỗi có thật trong dữ liệu.
- Chúng có tác động đo được qua log/quarantine/grading.
- Chúng không phải rule hình thức.

---

## 7. Kết quả pipeline final

Run chính:

```bash
python etl_pipeline.py run --run-id final-submit
```

Kết quả trong log:

```text
run_id=final-submit
raw_records=247
cleaned_records=27
quarantine_records=220
embed_upsert count=27 collection=day10_kb
PIPELINE_OK
```

Ý nghĩa:

- Có 247 dòng raw ban đầu.
- Sau cleaning còn 27 dòng sạch.
- Có 220 dòng bị quarantine.
- 27 dòng sạch được embed vào Chroma.
- Pipeline chạy thành công.

Log nằm ở:

```text
artifacts/logs/run_final-submit.log
```

Cleaned data:

```text
artifacts/cleaned/cleaned_final-submit.csv
```

Quarantine data:

```text
artifacts/quarantine/quarantine_final-submit.csv
```

Manifest:

```text
artifacts/manifests/manifest_final-submit.json
```

---

## 8. Freshness check

Freshness nghĩa là độ mới của dữ liệu.

Kết quả:

```text
freshness_check=FAIL
```

Lý do:

```text
latest_exported_at=2026-04-11T00:00:00
sla_hours=24
reason=freshness_sla_exceeded
```

Giải thích:

- Dữ liệu mẫu mới nhất là ngày 2026-04-11.
- Ngày chạy lab là 2026-06-10.
- SLA yêu cầu dữ liệu không quá 24 giờ.
- Vì vậy freshness fail là đúng với dữ liệu mẫu.

Kết luận:

- Pipeline không sai.
- Dữ liệu mẫu intentionally stale (cố ý cũ để học cách giám sát freshness).

---

## 9. Eval và grading

Chạy eval:

```bash
python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
```

Chạy grading:

```bash
python grading_run.py --out artifacts/eval/grading_run.jsonl
```

Kết quả:

```text
grading_rows=10
bad=[]
```

Nghĩa là:

- Có đủ 10 câu grading.
- Không có câu nào fail.
- Các câu `gq_d10_01` đến `gq_d10_10` đều OK.

File grading chính thức:

```text
artifacts/eval/grading_run.jsonl
```

---

## 10. Inject corruption để chứng minh before/after

Inject corruption nghĩa là cố ý đưa dữ liệu xấu vào để chứng minh pipeline/evaluation phát hiện được lỗi.

Đã tạo file inject:

```text
artifacts/eval/policy_export_inject_stale_refund.csv
```

File này thêm một dòng refund sai:

```text
14 ngày làm việc
```

Sau đó chạy:

```bash
python etl_pipeline.py run --run-id inject-bad-refund14 --raw "$PWD/artifacts/eval/policy_export_inject_stale_refund.csv" --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
```

Giải thích option:

- `--no-refund-fix`: tắt rule sửa `14 ngày` thành `7 ngày`.
- `--skip-validate`: cho phép pipeline tiếp tục embed dù expectation fail, chỉ dùng để demo dữ liệu xấu.

Kết quả inject:

```text
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
```

Eval inject:

```text
after_inject_bad.csv
forbidden_yes = 1
q_refund_window: hits_forbidden=yes
```

Nghĩa là AI/retrieval đã thấy nội dung sai `14 ngày`.

Sau đó chạy lại pipeline sạch:

```bash
python etl_pipeline.py run --run-id final-submit
python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
```

Kết quả sau fix:

```text
after_fix_eval.csv
forbidden_yes = 0
q_refund_window: hits_forbidden=no
```

Trong log final có:

```text
embed_prune_removed=1
```

Nghĩa là vector xấu từ inject đã bị xóa khỏi Chroma.

---

## 11. Tại sao chọn các phương pháp này?

### 11.1. Chọn quarantine thay vì xóa

Quarantine giúp giữ lại bằng chứng dòng lỗi.

Nếu xóa luôn, nhóm không biết dữ liệu đã lỗi ở đâu và vì sao.

### 11.2. Chọn expectation để halt pipeline

Halt nghĩa là dừng pipeline.

Các lỗi nguy hiểm như refund `14 ngày` hoặc HR `10 ngày phép năm` không được phép embed vào vector database. Vì vậy expectation severity là `halt`.

### 11.3. Chọn allowlist doc_id

Allowlist giúp pipeline chỉ xử lý nguồn đã biết và đã được contract xác nhận.

Nếu không có allowlist, tài liệu lạ hoặc dữ liệu sai hệ thống có thể lọt vào AI.

### 11.4. Chọn effective date cutoff

Ngày hiệu lực giúp phân biệt version cũ và mới.

Điều này quan trọng vì cùng một chính sách có thể xuất hiện nhiều version trong raw export.

### 11.5. Chọn before/after evidence

Before/after giúp chứng minh thay đổi có tác dụng thật.

Không chỉ nói "đã sửa", mà có bằng chứng:

- trước fix: `hits_forbidden=yes`
- sau fix: `hits_forbidden=no`
- grading cuối: 10/10 OK

### 11.6. Chọn Chroma upsert + prune

Upsert nghĩa là thêm mới hoặc cập nhật vector theo `chunk_id`.

Prune nghĩa là xóa vector cũ không còn trong cleaned data.

Lý do chọn:

- Tránh duplicate.
- Tránh AI vẫn tìm thấy dữ liệu cũ.
- Đảm bảo index phản ánh đúng snapshot cleaned hiện tại.

---

## 12. Artifact quan trọng khi nộp bài

| Artifact | Đường dẫn |
|----------|-----------|
| Log final | `artifacts/logs/run_final-submit.log` |
| Manifest final | `artifacts/manifests/manifest_final-submit.json` |
| Cleaned CSV | `artifacts/cleaned/cleaned_final-submit.csv` |
| Quarantine CSV | `artifacts/quarantine/quarantine_final-submit.csv` |
| Grading chính thức | `artifacts/eval/grading_run.jsonl` |
| Eval sau fix | `artifacts/eval/after_fix_eval.csv` |
| Eval inject xấu | `artifacts/eval/after_inject_bad.csv` |
| Log inject | `artifacts/logs/run_inject-bad-refund14.log` |
| Raw inject | `artifacts/eval/policy_export_inject_stale_refund.csv` |
| Data contract | `contracts/data_contract.yaml` |
| Pipeline architecture | `docs/pipeline_architecture.md` |
| Runbook | `docs/runbook.md` |
| Group report | `reports/group_report.md` |

---

## 13. Cách chạy lại từ đầu

Kích hoạt môi trường:

```bash
source .venv/bin/activate
```

Chạy pipeline sạch:

```bash
python etl_pipeline.py run --run-id final-submit
```

Chạy eval:

```bash
python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
```

Chạy grading:

```bash
python grading_run.py --out artifacts/eval/grading_run.jsonl
```

Kiểm tra nhanh grading:

```bash
python instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl --manifest artifacts/manifests/manifest_final-submit.json
```

Kỳ vọng:

```text
PIPELINE_OK
10/10 grading questions OK
```

---

## 14. Kết luận

Lab này chứng minh rằng AI/RAG không chỉ phụ thuộc vào model. Nếu dữ liệu đầu vào bẩn, cũ hoặc sai version, AI có thể trả lời sai. Pipeline đã được sửa để:

- đọc raw data,
- làm sạch dữ liệu,
- cách ly dòng lỗi,
- kiểm tra bằng expectation,
- embed dữ liệu sạch vào Chroma,
- xóa vector cũ,
- ghi log/manifest,
- chứng minh bằng eval và grading.

Kết quả cuối cùng: pipeline `final-submit` chạy thành công, final grading 10/10 OK, và có evidence before/after cho lỗi refund stale.
