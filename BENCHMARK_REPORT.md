# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được trích xuất trực tiếp từ các file report JSON (`reports/`), CSV (`benchmark-results/`) và log/trace thực tế.

**Họ tên:** Ngo Duy Khanh (2A202603870)  
**Ngày chạy:** 2026-11-26  
**Môi trường:** Windows 11 + Docker Desktop (Linux containers / WSL2 backend), Python 3.11 / 3.14

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Latency cơ bản của mock LLM (~120–180ms) + bước retrieval (~20ms) tốn ~200–250ms ở tải bình thường; ngưỡng 500ms đảm bảo trải nghiệm phản hồi tức thì cho 95% request mà vẫn dung thứ dao động mạng nhẹ. |
| Error rate `/ask` | `< 2.0 %` | Upstream LLM có tỉ lệ lỗi ngẫu nhiên ~1% (`MOCK_ERROR_RATE=0.01`); đặt ngưỡng `< 2%` cho phép hấp thụ nhiễu tự nhiên nhưng bắt được sự cố suy giảm hệ thống thực sự. |
| Accuracy trên golden dataset | `≥ 85 %` (mục tiêu `100 %` sau khi vá KB) | Đảm bảo pipeline RAG (agent v2) trả lời đúng đại đa số câu hỏi kỹ thuật cốt lõi và không bị regression sau mỗi lần thay đổi prompt/knowledge base. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, 300 requests/mức)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---:|---:|---:|---:|---:|---|
| 1 | 4.20 | 202.7 | 235.2 | 1707.7 | 0.67% | ✅ PASS |
| 10 | 38.39 | 203.1 | 237.3 | 1700.8 | 1.33% | ✅ PASS |
| 50 | 104.85 | 223.5 | 323.5 | 1702.4 | 2.00% | ✅ PASS |
| 100 | 46.59 | 633.8 | 4198.0 | 4645.6 | 1.00% | ❌ FAIL (p95 > 500ms) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?
- Từ `concurrency=1 → 10`, RPS tăng gần tuyến tính (`4.20 → 38.39 req/s`, gấp ~9.1 lần) vì ứng dụng dùng `async/await` (`asyncio.sleep`) nên event loop xử lý song song tốt các tác vụ chờ I/O mà p95 hầu như không tăng (`235.2 → 237.3 ms`).
- Tới `concurrency=50`, RPS đạt đỉnh `104.85 req/s` nhưng tốc độ tăng đã chậm lại (chỉ gấp ~2.7 lần so với `c=10`) và `p95` bắt đầu tăng lên `323.5 ms` do chi phí context-switching trên 1 worker process.
- Tới `concurrency=100`, hệ thống rơi vào vùng bão hòa hàng đợi (queueing saturation trên 1 uvicorn worker + socket backlog): RPS sụt giảm mạnh xuống `46.59 req/s` trong khi `p95` vọt lên `4198.0 ms`, vi phạm SLO.

### 2.2 Tail latency (`concurrency=20`, 300 requests)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|
| 0 | 202.8 | 233.5 | 245.3 |
| 0.03 (mặc định) | 262.7 | 245.4 | 1727.6 |
| 0.1 | 375.1 | 1718.7 | 1731.1 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?
- **`p99`** nhạy nhất ngay khi chỉ có 3% request chậm (`MOCK_SLOW_RATE=0.03`): `p99` nhảy vọt gấp **7 lần** (`245.3 ms → 1727.6 ms`), trong khi `avg` chỉ nhích nhẹ từ `202.8 ms → 262.7 ms` (+60ms) và `p95` vẫn thấp (`245.4 ms`). Khi tỉ lệ chậm tăng lên 10% (`0.1` > 5%), cả **`p95`** cũng nhảy vọt lên `1718.7 ms`, trong khi `avg` vẫn chỉ là `375.1 ms` (nhỏ hơn ngưỡng 500ms!).
- Không nên đặt SLO theo `average` vì giá trị trung bình làm phẳng và **che giấu nhóm khách hàng gặp trải nghiệm tệ nhất (tail latency)**. Đặt SLO theo `p95` / `p99` mới bảo vệ được phần đuôi phân phối khi chạy thực tế.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 (`eval_v1.json`) | Agent v2 (`eval_v2.json`) | Agent v2 (sau khi sửa KB — `eval_v2_fixed.json`) |
|---|---:|---:|---:|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | **100.00% (23/23)** |
| Avg tokens / câu | 56.4 | 109.1 | 114.7 |
| Tổng cost (USD) | $0.000394 | $0.000762 | $0.000799 |
| Cost / câu đúng (USD) | $0.00039435 | $0.00003627 | **$0.00003475** |
| Quality gate | ❌ FAIL (< 80%) | ✅ PASS (≥ 80%, 0 regression) | ✅ PASS (100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Bổ sung entry `(["jwt", "api key", "xác thực"], ...)` vào `KNOWLEDGE_BASE` giải thích sự khác biệt giữa JWT (token tự chứa thông tin, có hạn ngắn, chữ ký số) và API key tĩnh. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Bổ sung entry `(["kubernetes", "hpa"], ...)` vào `KNOWLEDGE_BASE` giải thích cơ chế scale pod của Kubernetes HPA theo CPU, memory và custom metrics. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2 (+ CI Quality Gate):**
- Agent v2 có thêm bước retrieval nên `p95 latency` tăng nhẹ (~`188.7 ms → 231.9 ms`) và lượng token trung bình mỗi câu tăng gấp ~1.93 lần (`56.4 → 109.1 tokens` do nối context vào prompt), khiến tổng cost 23 câu tăng gần gấp đôi (`$0.000394 → $0.000762`).
- Tuy nhiên, độ chính xác nhảy vọt từ `4.35%` lên `91.30%` (và `100%` sau khi bổ sung KB), giúp **chi phí trên mỗi câu trả lời đúng (`cost / câu đúng`) rẻ hơn hơn 11 lần** (`$0.00039435` xuống `$0.00003475`).
- **Cách chặn merge trong CI:** Đã cấu hình workflow [`.github/workflows/eval-quality-gate.yml`](.github/workflows/eval-quality-gate.yml) chạy `python eval/run_eval.py --min-accuracy 1.0 --baseline reports/eval_v2.json`. Nếu accuracy tụt dưới ngưỡng hoặc bất kỳ câu nào đang đúng ở baseline bị sai đi (regression), script trả về **exit code `1`**, làm job GitHub Actions fail và tự động chặn merge Pull Request.

---

## 4. Observability stack (production)

### 4.1 Screenshot & Phân tích Dashboard (Exercise 7.4)

- [x] Dashboard Grafana khi đang có tải: [`screenshots/grafana-dashboard.png`](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger: [`screenshots/jaeger-slow-trace.png`](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger: [`screenshots/jaeger-error-trace.png`](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với cả 4 alert đang **firing**: [`screenshots/prometheus-alert-firing.png`](screenshots/prometheus-alert-firing.png)

**Giải thích các câu hỏi quan sát trên Dashboard (Exercise 7.4):**
1. **Khoảng cách giữa `avg` và `p95` / `p99`:** Trên panel *Latency & Traffic*, đường `avg` (~220–240ms) và `p95` (~280–290ms) nằm khá thấp, nhưng đường `p99` tách hẳn lên vùng `~1.7s` do 3% request rơi vào đuôi chậm (`MOCK_SLOW_RATE=0.03`). Nhìn biểu đồ theo thời gian giúp thấy ngay sự phân kỳ của tail latency mà con số trung bình bỏ sót.
2. **Tại sao `input tokens/s` luôn cao hơn `output tokens/s`?** Vì Agent v2 (RAG) ghép cả `SYSTEM_PROMPT` + đoạn tài liệu truy xuất từ `KNOWLEDGE_BASE` + câu hỏi của người dùng vào đầu vào (`~74–85 input tokens`), trong khi câu trả lời sinh ra ngắn gọn hơn (`~35–46 output tokens`).
3. **Tại sao gọi `http://localhost:8080/metrics` từ bên ngoài lại nhận `404`?** Trong `nginx/nginx.conf` có rule `location = /metrics { return 404; }`. Endpoint `/metrics` phơi bày chi tiết cấu trúc route, lưu lượng, phiên bản model, chi phí USD và lỗi nội bộ nên chỉ cho phép Prometheus scrape trực tiếp qua mạng Docker nội bộ (`obs_net`), tuyệt đối không public ra Internet.
4. **Chia tải trên 3 instances:** Panel *Requests/s theo instance* cho thấy cả 3 container (`172.18.0.4:8000`, `172.18.0.8:8000`, `172.18.0.9:8000`) nhận lượng request/s đồng đều (~20 req/s mỗi instance ở đỉnh tải ~60 req/s) nhờ Nginx DNS resolver (`resolve valid=10s`) và Prometheus DNS service discovery (`dns_sd_configs`).

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.25` | `AgentHighErrorRate` (`for: 1m`, ngưỡng `> 5%`) | **~70.2 giây** (`PENDING` ở `10.1s`, `FIRING` ở `70.2s` với error rate `26.64%`) | *Error rate* (chuyển đỏ) & *Requests/s theo status* (`503` tăng vọt) |
| B | `MOCK_SLOW_RATE=0.35` | `AgentHighLatencyP95` (`for: 2m`, ngưỡng `p95 > 1s`) | **~130.4 giây** (`PENDING` ở `10.1s`, `FIRING` ở `130.4s` với `p95 = 1.953s`) | *Latency p95* & *HTTP Request Latency (p50/p95/p99/avg)* |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`, ngưỡng `> $2/giờ`) | **~160.2 giây** (`PENDING` ở `40.2s` khi `rate[5m]` vượt `$2/h`, `FIRING` sau thêm `2m` ở mức `~$16.31/giờ`) | *LLM Cost (1h)* & *LLM Burn Rate ($/hour)* |
| D | `docker pause` 1 instance (`agent-2`) | `AgentInstanceDown` (`for: 30s`, `up == 0`) | **~40.2 giây** (`PENDING` ngay chu kỳ scrape đầu, `FIRING` ở `40.2s` trên `172.18.0.8:8000`) | *Instances Up* (giảm 1) & *Requests/s theo instance* (1 đường về 0) |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** | Không bao giờ firing | *Retrieval Hit Ratio* (rơi về 0%), *LLM Tokens/s* giảm, bảng *Agent Info* đổi sang `v1` |

**Phân tích chuyên sâu (Thí nghiệm D & E):**
- **Vì sao ở Thí nghiệm D dùng `docker pause` thay vì `docker stop`, và lỗi `504` ở Nginx không làm tăng Error rate của Agent?**
  - Nếu `docker stop`, container biến mất khỏi Docker DNS nên Prometheus `dns_sd_configs` xóa luôn target đó khỏi danh sách scrape (không còn metric `up == 0`). Khi `docker pause`, container vẫn nằm trong DNS nhưng bị đóng băng không phản hồi scrape → `up{job="agent"} == 0` kích hoạt `AgentInstanceDown`.
  - Đồng thời, các request bị Nginx gửi vào instance đang pause sẽ treo tới `proxy_read_timeout` rồi do chính Nginx trả `504 Gateway Timeout` (hoặc retry sang upstream khác) — process Python của agent không hề xử lý xong request đó nên counter `http_requests_total{status=~"5.."}` bên trong agent không tăng. Vì vậy trong production bắt buộc phải giám sát thêm metric ở tầng **Load Balancer / Ingress** và **Synthetic blackbox probing** từ bên ngoài.
- **Thí nghiệm E (`AGENT_VERSION=v1`) không làm alert hạ tầng nào firing — phát hiện trong production bằng cách nào?**
  - `v1` vẫn trả HTTP `200 OK` cực nhanh và rẻ, nên cả 4 Golden Signals hạ tầng đều "xanh", dù chất lượng câu trả lời tụt từ `100%` xuống `4.35%` ("silent quality failure").
  - Cách phát hiện: (1) Chặn ngay từ CI/CD bằng **Offline Eval Quality Gate** trên Golden Dataset (`run_eval.py`); (2) Trong runtime production, bổ sung **Online LLM-as-a-Judge** chấm mẫu ngẫu nhiên 5–10% hội thoại thật đẩy thành custom metric (vd `agent_answer_quality_score`), đặt alert trên **Retrieval Hit Ratio** (đột ngột tụt về 0 khi RAG hỏng) và theo dõi tỉ lệ thumbs-down của người dùng.

### 4.3 Debug bằng trace

Trace chậm nhất tìm được trên Jaeger (`screenshots/jaeger-slow-trace.png`):
- `trace_id`: `3bdaeea993f8d0f7489e8b688e6b9dc6`
- Tổng thời gian (`POST /ask`): **`1676.53 ms`** (`agent.run`: `1673.18 ms`, `agent.retrieve_context`: `22.33 ms`)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**`1650.38 ms`**, chiếm **`98.44%`** tổng thời gian request — chứng tỏ độ trễ nằm ở bước gọi LLM upstream chứ không phải ở code FastAPI hay bước retrieval)
- Dòng log JSON tương ứng trích xuất từ `docker compose -p k5-day14-observability logs agent` (khớp chính xác `trace_id` và `span_id`):

```json
{"ts": "2026-11-26T10:01:18.850046+00:00", "level": "INFO", "service": "observable-agent", "instance": "d4ced2f606a0", "event": "llm_call", "trace_id": "3bdaeea993f8d0f7489e8b688e6b9dc6", "span_id": "47988ab6c3e7a2b8", "request_id": "445734add22e", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 74, "output_tokens": 37, "cost_usd": 3.3e-05, "llm_ms": 1649.5}
{"ts": "2026-11-26T10:01:18.851254+00:00", "level": "INFO", "service": "observable-agent", "instance": "d4ced2f606a0", "event": "http_request", "trace_id": "3bdaeea993f8d0f7489e8b688e6b9dc6", "span_id": "47988ab6c3e7a2b8", "request_id": "445734add22e", "method": "POST", "route": "/ask", "status": 200, "ms": 1675.6}
```

*(Ngoài ra, trace lỗi `screenshots/jaeger-error-trace.png` có `trace_id = 99c98a190d1b1154cba2265c12db00fa`, tổng thời gian `127 ms`, ghi nhận rõ event `exception` loại `utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)` trên span `chat mock-llm-small`).*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu khớp chính xác với [`benchmark-results/scale_1_stats.csv`](benchmark-results/scale_1_stats.csv) và [`benchmark-results/scale_3_stats.csv`](benchmark-results/scale_3_stats.csv):

| Số instance | Endpoint / Dòng CSV | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---:|---:|---:|---:|---|
| **1** (`scale_1`) | `POST /ask` | 58.92 | 210 | 440 | 1700 | 82 / 7053 (1.16%) |
| **1** (`scale_1`) | `Aggregated` | 64.63 | 200 | 410 | 1700 | 82 / 7737 (1.06%) |
| **3** (`scale_3`) | `POST /ask` | 59.70 | 200 | **250** | 1700 | 63 / 7114 (0.89%) |
| **3** (`scale_3`) | `Aggregated` | 65.81 | 190 | **240** | 1700 | 63 / 7842 (0.80%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?
- **Có cải thiện rõ rệt ở `p95`:** Khi tăng từ 1 lên 3 instance, `p95` của `POST /ask` giảm mạnh **~43%** (từ `440 ms` xuống `250 ms`, và `GET /health` p95 giảm từ `59 ms` xuống `19 ms`). Lý do là ở `scale=1`, một container duy nhất bị giới hạn `cpus: "0.5"` trong `docker-compose.yml` nên khi chịu 100 concurrent users (kèm overhead serialize JSON + OpenTelemetry spans + Prometheus metrics), CPU/event-loop bắt đầu nghẽn nhẹ; chia tải ra 3 container giúp giải tỏa hoàn toàn độ trễ hàng đợi nội bộ.
- **Tuy nhiên `p99` (`1700 ms`) không giảm và `RPS` giữ quanh mức `~65 req/s`:**
  1. Nút thắt của `p99` nằm ở **độ trễ của dịch vụ LLM bên ngoài (`chat mock-llm-small` tail latency ~1.5s–1.7s)** — việc tăng thêm web container của agent không làm API của OpenAI/Anthropic phản hồi nhanh hơn.
  2. Tổng `RPS` dừng quanh `~65 req/s` vì workload là *closed-loop* với 100 Locust users có thời gian nghỉ `wait_time = between(0.5, 2.0)` (trung bình nghỉ `1.25s` + `~0.24s` xử lý ≈ `1.49s`/vòng → trần lý thuyết của 100 user là `100 / 1.49 ≈ 67 req/s`).

---

## 6. Kết luận

- **3 điều rút ra về Benchmark & Observability:**
  1. **Không bao giờ đánh giá latency qua số trung bình (`avg`):** Chỉ 3% request bị tail latency đã đẩy `p99` lên `1.7s` dù `avg` vẫn đẹp (`~260ms`); bắt buộc đặt SLO và giám sát theo `p95` / `p99`.
  2. **Hạ tầng "xanh" không đồng nghĩa AI trả lời đúng:** Metrics hạ tầng không phát hiện được lỗi suy giảm chất lượng prompt/RAG (như khi tụt về `v1`); phải kết hợp **Offline Eval Quality Gate** trên Golden Dataset (tính cả chỉ số `cost / câu đúng`) với giám sát chất lượng online.
  3. **Liên kết 3 trụ cột Metrics – Traces – Logs qua `trace_id` giúp rút ngắn thời gian debug:** Từ cảnh báo trên Prometheus/Grafana → mở Jaeger cô lập chính xác span gây chậm (`chat mock-llm-small` chiếm 98.4% thời gian) → tra ngược dòng log JSON chứa ngữ cảnh chi tiết bằng `trace_id`.
- **Nếu đưa agent này lên production thật, cần bổ sung thêm metric / alert:**
  1. **Metric & Alert tầng Nginx / Ingress:** Tỉ lệ lỗi `502/504` và latency đo từ phía ngoài Load Balancer để bắt các lỗi mạng/container treo mà app metric không nhìn thấy.
  2. **Metric chất lượng ngữ nghĩa & RAG:** `retrieval_empty_rate` (tỉ lệ câu hỏi không tìm thấy tài liệu trong vector DB), điểm đánh giá online từ LLM-as-judge (`faithfulness` / `relevance`), và tỉ lệ người dùng phản hồi tiêu cực.
  3. **Metric Token Quota & Rate Limit:** Tỉ lệ request bị chặn bởi `429` (Rate Limiter) và `402` (Cost Guard) để phân biệt lỗi hệ thống với giới hạn bảo vệ chủ động.
