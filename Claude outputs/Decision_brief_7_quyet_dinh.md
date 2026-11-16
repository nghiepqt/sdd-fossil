# Decision brief – 7 quyết định cần chốt (LOG6309E → MSR 2027)

Cập nhật 12/11/2026. Dành cho: Nghiệp, Trần, Dũng. Vì không họp được, mỗi mục có **đề xuất** và lý do. **Cách chốt:** trả lời "OK" hoặc phản đối kèm lý do ngay trong chat. **Hết tối thứ Sáu 13/11, mục nào không ai phản đối thì coi như chốt theo đề xuất**, vì việc bốc mẫu và pilot (9–15/11) phụ thuộc vào các mục này.

Số liệu lấy từ `results/numbers.json` (SpecMine v1.0, cohort 72.971 living spec trong 6.085 repo). Không số nào gõ tay.

---

## Tóm tắt một trang

| # | Quyết định | Đề xuất | Trạng thái |
|---|---|---|---|
| 1 | Taxonomy A / B / cả hai | **A là chính** (+ completeness của nhóm). B chỉ giữ trong pilot 30 spec, có luật dừng dựa trên dữ liệu | cần OK |
| 2 | Định nghĩa fossil cho headline | **Cờ `has_unfilled_placeholder` (14.294)** làm headline. Chuỗi archive-text (13.426) làm robustness. Mẫu fossil để code bốc từ phần giao của hai tập | cần OK |
| 3 | Kaplan–Meier | **Không vào bài thuyết trình 26/11.** Làm sau khi số đã đóng băng, nếu Dũng còn giờ. Là việc đầu tiên bị cắt | cần OK |
| 4 | Phạm vi 26/11 | RQ1 đầy đủ; RQ2–RQ4 trên 100+100 spec người code (κ trên tập double-code); LLM 375+375 chỉ khi sẵn sàng và κ ≥ 0,6 | cần OK |
| 5 | A1 – RQ4 so sánh nhóm nào | **"Maintained" = ≥ 1 chỉnh sửa thật (other edit)**. So sánh chính: *edited* (12.487) vs *fossil* (14.294). Báo cáo thêm *merge_only* như nhóm thứ ba | cần OK |
| 6 | A3 – bootstrap và "34%–67%" | **Bỏ "34%–67%"** (không có nguồn). **Làm bootstrap theo repo** bằng script mới `s07` (khoảng 1 giờ) | cần OK |
| 7 | A4 – DOI dataset | **ĐÃ CHỐT:** trích dẫn `10.5281/zenodo.22102779`, ghi "v1.0, July 2026 snapshot". Tải dữ liệu vẫn từ record `22102780`. Chưa kiểm tra được từ sandbox, có lệnh kiểm tra 10 giây ở mục 7 | chốt, cần 1 người chạy lệnh kiểm tra |

---

## 1. Taxonomy: A, B, hay cả hai

**Hai taxonomy là gì (SpecMine paper, Table III + Appendix F, LLM-judge gemini-2.5-pro, temp 0):**

- **A – nội dung spec** (hai chiều độc lập, mỗi chiều có mức *none / incidental / substantial / dominant*):
  - *requirements*: problem, behaviour, acceptance, constraints, stakeholders
  - *implementation*: architecture, plan, code, conventions
  - Luật judge quan trọng: acceptance criteria tính là requirements; chỉ chấm theo bằng chứng trong văn bản (phải trích nguyên văn ≤ 20 từ); tiêu đề rỗng không phải bằng chứng.
- **B – loại công việc** (nhiều nhãn, mượn từ Watanabe et al.): purpose = feat/fix/refactor/style/perf; object = docs/test/ci/build/chore.
- **Chiều của riêng nhóm**: *completeness* (đủ trừ Purpose / skeletal / gần rỗng). Phải ghi rõ là của nhóm tự thêm.

**Vì sao nghiêng về A:**

1. **B được thiết kế cho spec của *công việc cần làm*.** Prompt B quy định: tài liệu mô tả hệ thống *như hiện tại* thì đặt `is_spec_of_work=false` và trả `["none"]` cho cả hai chiều. Living spec của OpenSpec chính là loại tài liệu mô tả hành vi hiện tại. Nếu dùng B, nhiều living spec có thể ra "none". Pilot sẽ cho biết bao nhiêu.
2. **B ít phương sai trên dữ liệu của ta.** Fig. 4 của paper: 91% spec `OpenSpec capability` có nhãn `feat`. Một nhãn gần như hằng số thì không giúp phân biệt fossil với spec được sửa (RQ4).
3. **A trả lời đúng câu hỏi RQ3.** "Fossil có phải spec rỗng, hay là spec thật nhưng chưa ai điền Purpose?" Mức extent của A cùng completeness đo trực tiếp điều đó.
4. **Công sức.** B là đa nhãn kèm bằng chứng cho từng nhãn, tức thêm một lượt code cho 200 spec mà ít thông tin. Chi phí double-code đã ước 10–13 giờ/người cho 200 spec.
5. Yêu cầu của instructor ("dùng category có sẵn trong tài liệu, đừng tự đặt") vẫn được đáp ứng đầy đủ chỉ với A.

**Đề xuất cụ thể:**

- Người code (100+100) code: `requirements_extent`, `implementation_extent`, `completeness`, `is_spec` (4 trường). Loại con (behaviour/acceptance/…) chỉ để LLM gắn nếu kịp.
- **Pilot 30 spec (9–15/11)** vẫn code thêm B (khoảng 20 phút thêm) để kiểm chứng. **Luật dừng:** chỉ đưa B vào đợt code chính nếu có ≥ 2 nhãn xuất hiện ở ≥ 15% spec *và* đa số spec có `is_spec_of_work=true`. Nếu không, bỏ B và ghi một câu vào báo cáo.
- Pilot cũng kiểm tra A có khớp living spec không, và chiều nào cần mở rộng.

**Rủi ro nếu chọn "cả hai":** thời gian code tăng, κ khó đạt hơn trên chiều đa nhãn, mà lợi ích nhận được thấp. **Rủi ro nếu chỉ A:** reviewer hỏi sao không dùng Watanabe. Trả lời: Watanabe nhắm vào thay đổi mã, ta đã thử trong pilot và ghi lại kết quả.

---

## 2. Định nghĩa fossil cho headline: cờ 14.294 hay chuỗi archive-text 13.426

**Hiện tại:** fossil = living spec có `has_unfilled_placeholder = true` *và* 0 revision. Cờ này do SpecMine tính.

| | Số fossil | Tỉ lệ trong 72.971 |
|---|---|---|
| Cờ SpecMine | **14.294** | 19,6% (Wilson 19,3–19,9%) |
| Chuỗi archive-text ("…created by archiving change… Update Purpose after archive") | **13.426** | 18,4% |

Chênh 868 fossil, tức khoảng 1,2 điểm phần trăm.

**Điều đã đo (trên toàn bộ living spec có placeholder, không riêng fossil):**

- Cờ gồm 21.325 spec; chuỗi archive-text gồm 19.651. Cờ **bao trọn** tập archive-text (recall = 1,0, không bỏ sót), precision 92,2%. Tức cờ thêm 1.674 spec.
- Trong phần thêm có: 196 spec chỉ ghi "TBD" trơn; **127 spec không có mục Purpose** (không phải placeholder do tool ghi); một số "TBD (Added from definitive-2026-template)"; nhiều biến thể "created by *syncing* change…" (có vẻ do lệnh sync, hợp lý để tính); vài spec mà Purpose là câu mô tả thật.
- Nghĩa là phần thêm có hỗn hợp: một phần là biến thể của tool (hợp lệ), một phần là thứ không do tool ghi (không hợp lệ).

**Đề xuất:**

- **Headline = cờ SpecMine (14.294).** Lý do: đây là đặc trưng công bố của dataset, người khác tái lập được; mọi số trong repo, README, proposal đã dùng nó; không phải chạy lại gì. Chênh 1,2 điểm phần trăm không làm đổi kết luận.
- **Robustness = chuỗi archive-text (13.426)**, một dòng trong bảng, kèm câu giải thích 1,674 spec thêm.
- **Mẫu fossil để code (100 người + 375 LLM) bốc từ phần giao của hai tập.** Như vậy mọi spec được code chắc chắn là placeholder do tool ghi, nên không ai bắt lỗi được ở khâu này. Cần ghi rõ trong phương pháp.
- Nếu team thích "an toàn" hơn: đổi headline sang 13.426. Cái giá là phải sửa mọi nơi dùng 14.294 (README, proposal, `numbers.json`, macros). Không đề xuất, vì chênh quá nhỏ so với công sức và rủi ro lệch số.

---

## 3. Kaplan–Meier (tùy chọn)

**Nó giải quyết gì:** nhiều spec còn "trẻ". 46.084/72.971 (63%) tuổi dưới 90 ngày tại thời điểm chụp (11/07/2026), nên "chưa được sửa" có thể chỉ là "chưa kịp". KM xử lý đúng kiểu censoring: đường cong "xác suất được sửa lần đầu theo tuổi".

**Cái ta đã có:** lọc theo tuổi (30/60/90 ngày). Fossil rate giảm nhẹ từ 19,6% xuống 17,9% (≥ 30d), 17,0% (≥ 60d), 16,8% (≥ 90d). Tức kết luận ổn định, KM chỉ làm đẹp và chặt chẽ hơn.

**Đề xuất:**

- **Không đưa vào 26/11.** Lọc tuổi đã đủ cho phần robustness của bài thuyết trình.
- Làm cho bài MSR nếu còn giờ. Một script (~2 giờ với `lifelines`), một hình. Người làm: Dũng (hoặc ai rảnh sau khi số đóng băng 22/11).
- Là **việc đầu tiên bị cắt** nếu trễ tiến độ.
- Lưu ý khi làm: lịch sử commit không theo dõi rename (số revision là cận dưới), nên "thời gian tới lần sửa đầu" cũng có thể dài hơn thực tế.

---

## 4. Phạm vi bài thuyết trình 26/11

**Đề xuất (đúng như nhóm đã nêu):**

| RQ | Nội dung ở 26/11 |
|---|---|
| RQ1 | **Đầy đủ**: fossil 19,6%, chưa từng sửa 62,7%, lọc tuổi, tách revision ra archive merge / other edit (kết quả s06), độ lệch theo repo |
| RQ2–RQ4 | Trên **100+100 spec do người code** (100 spec *edited* + 100 *fossil*), có κ tính trên tập double-code. Ghi rõ là *sơ bộ* |
| LLM 375+375 | Chỉ khi pilot cho prompt ổn **và** κ ≥ 0,6 trên nhãn giữ riêng của người. Nếu không kịp, để cho bài báo MSR |

**Lịch cần giữ:** pilot 30 spec xong 15/11; double-code 16–18/11; LLM + phân tích 19–22/11; **đóng băng số 22/11**; thuyết trình 26/11.

**Rủi ro lớn nhất:** 200 spec × 3 người code mất 10–13 giờ/người. **Phương án dự phòng định sẵn:** nếu tới 17/11 chưa đủ, giảm còn 50+50 và nói rõ trong slide. Đừng chờ đến phút chót mới quyết.

---

## 5. A1 – RQ4 so sánh nhóm nào, và "maintained" tính thế nào

**Số liệu mới từ s06** (phân loại 71.407 revision; luật: commit của một revision là commit tạo ra ≥ 1 spec lưu trữ trong cùng repo ⇒ archive merge):

| Loại revision \ placeholder | Có placeholder | Không placeholder | Tổng |
|---|---|---|---|
| `none` (0 revision) | **14.294** = fossil (19,6%) | 31.493 (43,2%) | 45.787 (62,7%) |
| `merge_only` (chỉ do archive) | **4.582** (6,3%) | 10.115 (13,9%) | 14.697 (20,1%) |
| `edited` (≥ 1 chỉnh sửa thật) | 2.449 (3,4%) | 10.038 (13,8%) | **12.487 (17,1%)** |
| Tổng | 21.325 (29,2%) | 51.646 (70,8%) | 72.971 |

**Ba điều rút ra:**

1. 68,0% revision (Wilson 67,7–68,3%) là archive merge. Đa số "sự bảo trì" thấy được là do tool, không phải ai đó chủ ý sửa. Tỉ lệ này gần như không đổi theo cỡ repo (5+ spec: 68,2%; 2–4: 66,9%; 1 spec: 47,9%).
2. "Maintained" nếu tính mọi revision = 27.184 spec (37,3%); nếu chỉ tính chỉnh sửa thật = **12.487 (17,1%)**. Chênh gần 2,2 lần.
3. **4.582 spec "có placeholder + merge_only"** trông như được bảo trì nhưng chỉ bị tool chạm vào và vẫn giữ nguyên chữ TBD. Chúng nằm ngoài định nghĩa fossil hiện tại (vì có revision).

**Tùy chọn:**

- **(a)** Revised-any (27.184) vs fossil (14.294). Dễ giải thích, nhưng nhóm "revised" lẫn 14.697 spec chỉ bị tool chạm, nên mọi khác biệt bị loãng và có thể gây hiểu nhầm.
- **(b)** *Edited* (12.487) vs fossil (14.294). Tương phản sạch: "có người chủ ý sửa" vs "chưa ai chạm". Hai nhóm cỡ gần nhau nên cân bằng. **← đề xuất.**
- **(c)** Ba nhóm cùng so sánh (edited / merge_only / fossil) + nhóm tham chiếu "never revised, no placeholder" (31.493). Đầy đủ nhất, nhưng 4 nhóm làm RQ4 rối và tốn mẫu.

**Đề xuất:** (b) làm tương phản chính trong RQ4. Báo cáo `merge_only` như nhóm thứ ba *chỉ ở mức tỉ lệ* (không bốc mẫu code riêng), và nhắc rõ 4.582 spec nói trên như một phát hiện phụ. Định nghĩa trong văn bản: *maintained = có ít nhất một other edit*. **Không đổi định nghĩa fossil** (instructor đã nhận).

**Cần lưu ý khi chọn mẫu:** giới hạn số spec lấy từ mỗi repo (ví dụ ≤ 3) để một vài repo lớn không chi phối; 76% repo có tỉ lệ fossil cực đoan (≤ 10% hoặc ≥ 90%) nên nếu không giới hạn thì mẫu sẽ là mẫu của vài repo.

**Giới hạn của luật phân loại (nên ghi vào threats):** kiểm chứng bằng thông điệp commit cho thấy 53,2% archive merge có chữ "archive" trong message so với 18,1% ở other edit. Khoảng cách lớn, nhưng 18,1% cho thấy có phần other edit có thể vẫn là merge (hoặc người sửa tay khi archive). Tức "other edit" là *cận trên* của chỉnh sửa chủ ý. Ngoài ra 880 commit archive nằm ở repo không có living spec trong cohort, và 524 file lưu trữ không có lịch sử, có thể làm xếp nhầm một số merge thành other edit. Chi tiết ở `results/numbers.json` (`revision_split`).

---

## 6. A3 – bootstrap và con số "34%–67%"

**Hiện trạng:** bản proposal đã nộp có "34%–67% từ dữ liệu snapshot" và "bootstrap theo repo". Trong repo **không có script nào** tạo ra hai thứ đó; `numbers.json` cũng không có. Bản v2 đã đánh dấu phần này "(to be decided)".

**Đề xuất:**

- **Bỏ "34%–67%".** Không ai tái lập được con số này, mà báo cáo của ta có quy tắc "không số nào gõ tay". Đừng đoán nó từ đâu ra.
- **Làm bootstrap thật**, vì nó có ích: các spec trong cùng repo không độc lập (6.085 repo, tỉ lệ fossil theo repo phân cực, 59% repo không có fossil nào), nên Wilson CI trên spec hơi hẹp quá. Làm bootstrap **theo cụm repo** (resample repo có hoàn lại, B = 1.000, seed cố định), cho CI của: tỉ lệ fossil, tỉ lệ chưa từng sửa, tỉ lệ revision là archive merge.
  - Thêm `src/s07_bootstrap.py`, thêm mục `bootstrap` vào `numbers.json`, thêm macros, thêm vào `run_all.sh`. Ước tính ~1 giờ.
  - Báo cáo CI theo repo song song với Wilson; nếu hai cái khác nhiều, nói rõ.
- Nếu muốn ngắn: chỉ cần câu "CI bootstrap theo repo (B = 1.000)" và một cột trong bảng.

**Người làm:** Nghiệp (hoặc agent của Nghiệp, vì đã có sẵn khung `s06`).

---

## 7. A4 – DOI dataset: **ĐÃ CHỐT**

**Sự việc:**

- `fetch_data.sh` và `proposal.bib` đang dùng record `…22102780`.
- README của dataset và paper SpecMine (Appendix E, "Version 1.0 … citable DOI") đều nói DOI để trích dẫn là `10.5281/zenodo.22102779`. Paper còn nói các snapshot sau sẽ là *record Zenodo mới với DOI riêng*.
- Chỉ tồn tại v1.0 của full dataset; chữ "v1.1" trong docs là nhãn của bản mẫu 500 repo.

**Quyết định:**

1. **Trong bài báo và proposal, trích dẫn `10.5281/zenodo.22102779`** (đúng cách tác giả yêu cầu), ghi rõ **"SpecMine v1.0 (July 2026 snapshot)"**.
2. **Tải dữ liệu vẫn từ record `22102780`** như `fetch_data.sh` hiện có (đang chạy đúng, đã kiểm thử). Không đổi.
3. Thêm checksum (SHA-256) của `specmine.zip` và các file Parquet vào repo (`data/CHECKSUMS.txt`) để ai cũng chứng minh được đã dùng cùng bản.
4. Sửa `proposal/proposal.bib` (entry `specmine_dataset`) và tham chiếu [12] trong `proposal_v2.tex`: `…780` → `…779`; cập nhật dòng DOI trong `README.md` nếu có.

**Vì sao chốt được mà chưa mở trang Zenodo:** theo thực tế thường gặp, `…779` là DOI *khái niệm* (concept DOI, luôn trỏ đến bản mới nhất) và `…780` là DOI *phiên bản* của v1.0. Dù đúng hay sai, cách xử lý ở trên vẫn an toàn: ta làm theo yêu cầu trích dẫn của chính tác giả, và ghi rõ phiên bản.

**Kiểm tra 10 giây (một người chạy từ máy cá nhân, vì sandbox của tôi không truy cập được zenodo.org):**

```bash
curl -s https://zenodo.org/api/records/22102780 | jq '.conceptdoi, .doi, .metadata.version'
```

- Nếu ra `conceptdoi = 10.5281/zenodo.22102779`, `doi = 10.5281/zenodo.22102780`, `version = 1.0`: giữ quyết định như trên. Trong ghi chú của bib thêm "version 1.0, record 22102780" cho người đọc muốn bản cố định.
- Nếu ra kết quả khác (ví dụ 779 là một bản khác): báo lại vào nhóm, đừng tự sửa.

---

## Sau khi chốt, việc cần làm (và ai làm)

| Việc | Người | Hạn |
|---|---|---|
| Nhắn OK / phản đối cho 7 mục | Cả 3 | tối T6 13/11 |
| Chạy lệnh kiểm tra DOI, sửa `proposal.bib`, proposal_v2 [12], thêm `CHECKSUMS.txt` | Nghiệp | 13/11 |
| Nếu mục 5 chốt (b): đổi định nghĩa "maintained" trong proposal_v2 (RQ2/RQ4) và `open_issues.md` | Nghiệp | 13/11 |
| Thêm `s07_bootstrap.py` | Nghiệp | 14/11 |
| Bốc mẫu: 100 edited + 100 fossil (giới hạn ≤ 3 spec/repo, seed cố định, fossil lấy từ phần giao cờ ∩ archive-text) | Nghiệp | 14/11 |
| Pilot 30 spec (A + completeness + B để thử) | Cả 3 | 15/11 |
| Cập nhật tài liệu kế hoạch theo kết quả s06 và các quyết định trên | Nghiệp | 14/11 |
