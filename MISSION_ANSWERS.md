# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
Trong file `01-localhost-vs-production/develop/app.py`, có hơn 5 anti-patterns khiến code không thể đưa thẳng lên production:

1. **Hardcoded secrets trong source code** (Dòng 17–18):
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - *Rủi ro:* Khi push code lên GitHub, key và mật khẩu DB sẽ bị lộ ngay lập tức trong lịch sử Git.
2. **In secret ra log bằng `print()`** (Dòng 33–34, 38):
   - Dùng `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` thay vì structured logging (`logging` module + JSON format).
   - *Rủi ro:* Lộ API key trong hệ thống thu thập log tập trung (như Datadog, CloudWatch, Loki) và rất khó parse/filter log tự động.
3. **Không có quản lý cấu hình theo môi trường (Hardcoded Config & Debug Mode)** (Dòng 21–22, 53):
   - `DEBUG = True`, `MAX_TOKENS = 500`, và `reload=True` trong `uvicorn.run()`.
   - *Rủi ro:* Bật `reload=True` và debug mode trên production làm tốn tài nguyên theo dõi file, giảm hiệu năng và có thể làm lộ stack trace chi tiết khi xảy ra lỗi.
4. **Bind cứng vào `host="localhost"` và `port=8000`** (Dòng 51–52):
   - `uvicorn.run("app:app", host="localhost", port=8000, reload=True)`.
   - *Rủi ro:* Trong Docker container hoặc trên Cloud (Railway/Render/Cloud Run), `localhost` (`127.0.0.1`) chỉ nhận kết nối từ bên trong container, bên ngoài không gọi vào được (phải dùng `0.0.0.0`). Ngoài ra, các nền tảng Cloud cấp port động qua biến môi trường `PORT`, nếu fix cứng `8000` có thể khiến health check của platform thất bại.
5. **Không có Health Check và Readiness Probe endpoints (`/health`, `/ready`)** (Dòng 42–43):
   - *Rủi ro:* Container orchestrator (Docker, Kubernetes, Railway, Render) không biết process còn sống hay đã treo để tự động restart, hoặc chưa load xong dependency mà đã đẩy traffic vào.
6. **Không xử lý Graceful Shutdown (`SIGTERM`)**:
   - *Rủi ro:* Khi deploy bản mới hoặc scale down, hệ thống gửi tín hiệu `SIGTERM`. Nếu không có lifecycle/signal handler để hoàn tất các request đang xử lý dở (in-flight requests) và đóng kết nối DB/Redis an toàn, người dùng sẽ gặp lỗi `502 Bad Gateway` hoặc mất dữ liệu.

*(Đối chiếu sửa lỗi: Trong `01-localhost-vs-production/production/app.py` và `config.py`, các vấn đề trên đã được khắc phục bằng cách đọc biến môi trường qua `os.getenv` ở `config.py` dòng 17–35, dùng JSON logging ở `app.py` dòng 28–31, thêm `/health` và `/ready` ở dòng 135–161, quản lý `lifespan` + `signal.signal(signal.SIGTERM, handle_sigterm)` ở dòng 40–68 & 180–189, và bind `0.0.0.0` với `settings.port` ở dòng 194–199).*

---

### Exercise 1.2: Kết quả chạy bản Basic (`develop/app.py`)
Chạy server và kiểm thử bằng `curl -X POST "http://localhost:8000/ask?question=Hello"`:

```json
{"answer":"Hello! I'm your AI agent running in production. Ask me anything about deployment, Docker, cloud platforms, API security, or scaling!"}
```

**Quan sát:** Ứng dụng chạy được trên máy cá nhân nhưng hoàn toàn **không production-ready** vì vi phạm các nguyên tắc 12-Factor App đã nêu ở Exercise 1.1 (lộ key trên console log, chỉ bind `localhost`, không có `/health`, không đọc `PORT` từ env).

---

### Exercise 1.3: Comparison table (`develop` vs `production`)

| Feature | Develop (`develop/app.py`) | Production (`production/app.py` + `config.py`) | Why Important? (Tại sao quan trọng?) |
|---------|----------------------------|------------------------------------------------|--------------------------------------|
| **Config & Secrets** | Hardcode trực tiếp trong code (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG = True`) | Đọc từ biến môi trường (`os.getenv` trong `Settings` dataclass) kèm hàm `.validate()` fail-fast | Tuân thủ 12-Factor App: tách biệt code và config, đổi cấu hình giữa dev/staging/prod mà không cần sửa code, tránh lộ secret lên Git. |
| **Network Binding & Port** | Cố định `host="localhost"`, `port=8000`, `reload=True` | `host=os.getenv("HOST", "0.0.0.0")`, `port=int(os.getenv("PORT", "8000"))`, `reload=settings.debug` | `0.0.0.0` cho phép nhận kết nối từ ngoài Docker container; đọc `PORT` động giúp tương thích với Railway/Render/Cloud Run. |
| **Health & Readiness Check** | Không có (`❌`) | Có `GET /health` (liveness + uptime) và `GET /ready` (readiness trả `200` hoặc `503`) (`✅`) | Giúp Load Balancer / Orchestrator biết khi nào container bị treo cần restart (`/health`) và khi nào sẵn sàng nhận traffic (`/ready`). |
| **Logging** | Dùng `print()`, in cả `OPENAI_API_KEY` ra stdout | Dùng module `logging` định dạng **Structured JSON** (`time`, `level`, `msg`, `event`), không log secret | Log JSON dễ dàng được parse, index, tìm kiếm và tạo alert trên các hệ thống tập trung (ELK, Loki, Datadog) mà không làm rò rỉ thông tin nhạy cảm. |
| **Shutdown & Lifecycle** | Tắt đột ngột khi nhận tín hiệu dừng | Có `lifespan` context manager và bắt tín hiệu `signal.SIGTERM` (**Graceful Shutdown**) | Đảm bảo ngừng nhận request mới nhưng vẫn chờ các request đang chạy hoàn tất và đóng kết nối an toàn trước khi process thoát, tránh lỗi 502/mất dữ liệu. |
| **CORS & Validation** | Không kiểm soát CORS; nhận query param thô không kiểm tra rỗng | Cấu hình `CORSMiddleware` với `ALLOWED_ORIGINS`; kiểm tra JSON body và trả `HTTPException(422)` rõ ràng | Bảo vệ API khỏi các truy cập cross-origin trái phép từ trình duyệt và đảm bảo hợp đồng dữ liệu đầu vào rõ ràng. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. **Base image là gì?**
   - Trong `02-docker/develop/Dockerfile`, base image là `python:3.11` (bản đầy đủ dựa trên Debian, bao gồm hệ điều hành, trình biên dịch C/C++, build tools và Python runtime — dung lượng nặng ~1 GB).
   - Trong `02-docker/production/Dockerfile`, base image là `python:3.11-slim` (bản rút gọn chỉ chứa các gói tối thiểu để chạy Python, nhẹ hơn rất nhiều).
2. **Working directory là gì?**
   - Là `/app` (được đặt bằng lệnh `WORKDIR /app`). Mọi lệnh `COPY`, `RUN`, `CMD` phía sau sẽ thực thi tương đối tại thư mục `/app` bên trong container.
3. **Tại sao `COPY requirements.txt` trước khi `COPY` source code?**
   - Để tận dụng cơ chế **Docker Layer Caching**. Docker cache từng dòng lệnh (layer); nếu `COPY requirements.txt` và `RUN pip install` đặt trước `COPY app.py`, thì khi ta chỉ sửa code trong `app.py` mà không đổi `requirements.txt`, Docker sẽ tái sử dụng layer cài thư viện đã cache mà không phải chạy lại `pip install` (tiết kiệm hàng chục giây đến vài phút mỗi lần build).
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `CMD` định nghĩa lệnh và/hoặc tham số **mặc định** khi container khởi chạy, nhưng rất dễ bị **ghi đè hoàn toàn** nếu truyền lệnh khác ở cuối `docker run <image> <other-cmd>`.
   - `ENTRYPOINT` cố định binary thực thi chính của container (khó bị ghi đè trừ khi dùng cờ `--entrypoint`), và các đối số truyền thêm vào `docker run` (hoặc trong `CMD`) sẽ được nối vào làm tham số cho `ENTRYPOINT`.

### Exercise 2.2: Kết quả gọi container `my-agent:develop`
Chạy container từ image `my-agent:develop` và gọi `curl -X POST "http://localhost:8000/ask?question=What%20is%20Docker"`:

```json
{"answer":"Docker packages your app and all its dependencies into a portable container. Key benefits: consistent environment across dev/staging/prod, easy scaling, isolation. Always use multi-stage builds to keep images small (<500MB)!","container_id":"..."}
```

### Exercise 2.3: Multi-stage build & Image size comparison
- **Stage 1 (`builder`):** Dùng `python:3.11-slim AS builder`, cài đặt các gói biên dịch nặng (`gcc`, `libpq-dev`) qua `apt-get`, rồi chạy `pip install --no-cache-dir --user -r requirements.txt` để biên dịch và cài toàn bộ Python packages vào `/root/.local`.
- **Stage 2 (`runtime`):** Khởi tạo một image `python:3.11-slim AS runtime` mới hoàn toàn sạch (không có `gcc`, `libpq-dev` hay apt cache), tạo non-root user `appuser`, chỉ `COPY --from=builder /root/.local /home/appuser/.local` và source code cần thiết để chạy ứng dụng, kèm `HEALTHCHECK`.
- **Tại sao image nhỏ hơn?** Vì toàn bộ trình biên dịch (`gcc`), header files (`libpq-dev`), cache cài đặt ở Stage 1 và các công cụ thừa của image `python:3.11` đầy đủ đều bị loại bỏ ở Stage 2.

**So sánh dung lượng đo bằng `docker images`:**
- Develop (`my-agent:develop`): **1.67 GB** (1,670 MB disk usage / 426 MB content size)
- Production (`my-agent:advanced`): **240 MB** (57.4 MB content size)
- Difference (Giảm): **~85.6%** (giảm 1,430 MB nhờ dùng `python:3.11-slim` và multi-stage build)

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

**Sơ đồ kiến trúc (Architecture Diagram):**
```text
                        ┌──────────────────────────────────────────────────────┐
                        │               Docker Network: internal               │
┌──────────┐   :80/:443 │  ┌───────────────┐        ┌───────────────────────┐  │
│  Client  │ ─────────► │  │     nginx     │ ─────► │    agent (FastAPI)    │  │
└──────────┘            │  │ (nginx:alpine)│  :8000 │  (uvicorn 2 workers)  │  │
                        │  └───────────────┘        └──────┬─────────┬──────┘  │
                        │                                  │         │         │
                        │            REDIS_URL (:6379)     ▼         ▼ :6333   │
                        │                           ┌───────────┐ ┌──────────┐ │
                        │                           │   redis   │ │  qdrant  │ │
                        │                           │ (7-alpine)│ │ (v1.9.0) │ │
                        │                           └─────┬─────┘ └────┬─────┘ │
                        └─────────────────────────────────┼────────────┼───────┘
                                                          ▼            ▼
                                                     [redis_data] [qdrant_data]
```

**Các services được khởi tạo và cách giao tiếp:**
1. **`nginx` (`nginx:alpine`)**: Reverse proxy & Load balancer duy nhất mở port ra máy host (`80:80`, `443:443`). Áp dụng rate limit `10r/s` theo IP và forward request tới upstream `http://agent:8000`.
2. **`agent` (build từ `02-docker/production/Dockerfile`, stage `runtime`)**: Ứng dụng FastAPI chạy ở cổng nội bộ `8000` (không expose trực tiếp ra host), chỉ khởi động sau khi `redis` và `qdrant` đã `service_healthy`.
3. **`redis` (`redis:7-alpine`)**: Cache cho session và rate limiting ở cổng nội bộ `6379`, gắn volume `redis_data`.
4. **`qdrant` (`qdrant/qdrant:v1.9.0`)**: Vector database cho RAG ở cổng nội bộ `6333`, gắn volume `qdrant_data`.
- Cả 4 services giao tiếp qua bridge network nội bộ tên là `internal` bằng service name (DNS nội bộ của Docker Compose).

**Kết quả test qua Nginx (port 80):**
- `GET http://localhost/health`:
  ```json
  {"status":"ok","uptime_seconds":12.4,"version":"2.0.0","timestamp":"..."}
  ```
- `POST http://localhost/ask` (`{"question": "Explain microservices"}`):
  ```json
  {"answer":"..."}
  ```

---

## Part 4: API Security

### Exercise 4.1: API Key authentication (`04-api-gateway/develop/app.py`)
- **API key được check ở đâu?** Trong dependency `verify_api_key(api_key: str = Security(api_key_header))` (dòng 39–54), đọc header `X-API-Key` bằng `APIKeyHeader(name="X-API-Key", auto_error=False)` và tiêm vào endpoint `POST /ask` qua `Depends(verify_api_key)` (dòng 70).
- **Nếu thiếu hoặc sai key:** Thiếu header trả về `401 Unauthorized`; sai key trả về `403 Forbidden` (với message `Invalid API key.`).
- **Làm sao rotate key?** Vì `API_KEY` đọc từ biến môi trường `os.getenv("AGENT_API_KEY", ...)` (dòng 35), chỉ cần cập nhật biến môi trường trên nền tảng deploy (hoặc hỗ trợ danh sách key cũ + mới song song trong giai đoạn chuyển tiếp) rồi restart/redeploy mà không cần sửa code.

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)
- **Thuật toán Rate Limiting (`rate_limiter.py`):** Dùng **Sliding Window Counter** (dòng 7–11, 35–40): lưu timestamp các request của từng `user_id` trong `deque`, mỗi lần gọi sẽ xóa các timestamp cũ hơn `now - window_seconds` (60 giây).
- **Giới hạn & bypass theo role:** User thường (`rate_limiter_user`) giới hạn **10 requests/phút**; Admin (`rate_limiter_admin`, role `admin` như tài khoản `teacher`) giới hạn **100 requests/phút** (dòng 86–87).

**Kết quả test thực tế (`curl -i`, đã che token):**
```text
# 1. Không có token -> 401 Unauthorized
POST /ask (no Authorization header) -> HTTP/1.1 401 Unauthorized

# 2. Lấy JWT token (student / demo123) -> 200 OK
POST /auth/token -> HTTP/1.1 200 OK (access_token: <REDACTED>)

# 3. Gọi liên tiếp 12 request với Authorization: Bearer <REDACTED>
Req 1  -> HTTP/1.1 200 OK {"usage":{"requests_remaining":9,...}}
Req 2  -> HTTP/1.1 200 OK {"usage":{"requests_remaining":8,...}}
...
Req 10 -> HTTP/1.1 200 OK {"usage":{"requests_remaining":0,...}}
Req 11 -> HTTP/1.1 429 Too Many Requests {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
Req 12 -> HTTP/1.1 429 Too Many Requests {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cost Guard implementation (`cost_guard.py`)
- **Tại sao cần cả Rate Limit và Cost Guard?** Rate limit bảo vệ **tốc độ** (tránh spam/DDoS làm quá tải server trong ngắn hạn), còn Cost Guard bảo vệ **ngân sách (tiền)** — vì một request hợp lệ nhưng có prompt/output rất dài vẫn có thể tiêu tốn nhiều token và làm vượt ngân sách ngày/tháng.
- **Cách triển khai trong production:**
  1. Định giá token đầu vào/đầu ra (`PRICE_PER_1K_INPUT_TOKENS`, `PRICE_PER_1K_OUTPUT_TOKENS`).
  2. Trước khi gọi LLM (`check_budget`): kiểm tra tổng chi phí hiện tại trong Redis (key theo user và ngày/tháng, ví dụ `budget:{user_id}:{YYYY-MM-DD}` hoặc `{YYYY-MM}`). Nếu `>= budget`, chặn ngay bằng `HTTP 402 Payment Required`.
  3. Sau khi LLM trả lời (`record_usage` / `record_cost`): tính chi phí thực tế từ `input_tokens` và `output_tokens`, cộng dồn vào Redis bằng lệnh atomic `INCRBYFLOAT` và đặt `EXPIRE` tự động hết hạn khi qua chu kỳ mới.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health check (`/health`) vs Readiness check (`/ready`)
- **`GET /health` (Liveness Probe):** Kiểm tra xem **process của ứng dụng có còn sống không** (không bị deadlock hay crash). Endpoint này **không phụ thuộc vào Redis/DB** — chỉ cần process đang chạy thì trả `200 OK`. Nếu `/health` lỗi, platform (Docker/K8s/Railway) sẽ **restart container**.
- **`GET /ready` (Readiness Probe):** Kiểm tra xem **agent đã sẵn sàng nhận traffic chưa** (đã khởi tạo xong, kết nối được tới Redis/Database và chưa vào trạng thái shutdown). Nếu mất kết nối Redis hoặc đang shutdown, trả về `503 Service Unavailable` để Load Balancer tạm ngừng đẩy traffic mới vào instance này (thay vì restart oan).

### Exercise 5.2: Graceful Shutdown
- Khi container hoặc server nhận tín hiệu `SIGTERM` (lúc `docker stop` hoặc deploy bản mới):
  1. Đánh dấu trạng thái không còn ready (`_is_ready = False`) để ngừng nhận request mới từ Load Balancer.
  2. Chờ các request đang xử lý dở (in-flight requests) hoàn thành (trong `lifespan` shutdown, có timeout tối đa).
  3. Đóng các kết nối tài nguyên (Redis, DB) rồi mới thoát với exit code `0`.

### Exercise 5.3 – 5.5: Stateless Design & Load Balancing với 3 Instances
- **Tại sao không lưu state (conversation history, rate limit) trong RAM?** Khi scale lên 3 instances sau Nginx Load Balancer, mỗi instance có vùng nhớ RAM riêng. Nếu lưu `conversation_history` trong dict ở RAM, request 1 vào `agent-1` nhưng request 2 được Nginx chuyển sang `agent-2` sẽ bị mất toàn bộ lịch sử hội thoại.
- **Giải pháp Stateless:** Toàn bộ session history được lưu tập trung vào **Redis** (`redis://redis:6379/0`), giúp mọi instance đều đọc/ghi chung một nguồn dữ liệu.

**Kết quả chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và `python test_stateless.py`:**
```text
Session ID: 4a57c5fc-8940-4546-9a93-09ed8e61e1fa
Request 1: [instance-734710] -> Q: What is Docker?
Request 2: [instance-6d9f03] -> Q: Why do we need containers?
Request 3: [instance-6970bd] -> Q: What is Kubernetes?
Request 4: [instance-734710] -> Q: How does load balancing work?
Request 5: [instance-6d9f03] -> Q: What is Redis used for?

Total requests: 5
Instances used: {'instance-734710', 'instance-6d9f03', 'instance-6970bd'}
✅ All requests served despite different instances!
Total messages: 10
✅ Session history preserved across all instances via Redis!
```
- **Giải thích:** Nginx phân phối tuần tự (round-robin) 5 request qua các container ID khác nhau (`Instances used` có > 1 instance), nhưng khi gọi `GET /chat/{session_id}/history`, toàn bộ 10 tin nhắn (5 câu hỏi + 5 câu trả lời) vẫn được bảo toàn đầy đủ nhờ lưu trong Redis.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Public Deployment (`06-lab-complete/`)
- **Platform:** Render / Railway
- **Public URL:** `[PENDING_PUBLIC_URL]` (xem chi tiết lệnh kiểm thử trong [DEPLOYMENT.md](DEPLOYMENT.md))
- **Screenshots:**
  - Dashboard: `screenshots/dashboard.png`
  - Service running: `screenshots/running.png`
  - API test results: `screenshots/test.png`

### Exercise 3.2: So sánh `railway.toml` và `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) | Vì sao khác nhau? |
|---|---|---|---|
| **Định dạng & Triết lý** | TOML ngắn gọn, cấu hình cho **1 service đơn lẻ** trong thư mục hiện tại | YAML khai báo hạ tầng đầy đủ (**Infrastructure-as-Code**), quản lý **nhiều services** (web + Redis + DB) trong cùng 1 file | Railway hướng tới trải nghiệm deploy nhanh qua CLI/auto-detect; Render Blueprint hướng tới quản lý toàn bộ stack qua GitOps. |
| **Cách build & chạy** | `[build] builder = "DOCKERFILE"` (hoặc `"NIXPACKS"`), start command nằm trong `Dockerfile` hoặc `[deploy] startCommand` | Khai báo `type: web`, `runtime: docker` (hoặc `python` kèm `buildCommand` và `startCommand`), chọn `region` và `plan` rõ ràng | Render yêu cầu định nghĩa loại tài nguyên (`web`, `redis`, `worker`) và gói tài nguyên ngay trong spec. |
| **Quản lý biến môi trường & Secrets** | Không khai báo biến môi trường trong `railway.toml`; đặt ngoài qua CLI (`railway variables set`) hoặc Dashboard | Khai báo danh sách `envVars` ngay trong `render.yaml`; biến nhạy cảm dùng `sync: false` (nhập tay trên UI) hoặc `generateValue: true` (tự sinh ngẫu nhiên) | Giúp Render kiểm soát schema biến môi trường ngay trong Git mà vẫn không làm lộ giá trị secret thật. |
| **Health check & Restart** | `[deploy] healthcheckPath = "/health"`, `healthcheckTimeout`, `restartPolicyType = "ON_FAILURE"` | `healthCheckPath: /health` và `autoDeploy: true` theo nhánh Git | Cả hai đều gọi `GET /health` để xác nhận container mới khỏe mạnh trước khi chuyển đổi traffic (zero-downtime). |

### Exercise 3.3: Mô tả CI/CD Pipeline trên GCP Cloud Run (`cloudbuild.yaml` & `service.yaml`)
Pipeline trong `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` tự động hóa quy trình từ lúc push code lên nhánh `main` qua **4 bước tuần tự (`waitFor`)**:
1. **`test` (`python:3.11-slim`)**: Cài đặt `requirements.txt` + `pytest` và chạy toàn bộ unit test trong `tests/`; nếu test fail thì dừng pipeline ngay, không build image lỗi.
2. **`build` (`gcr.io/cloud-builders/docker`)**: Build Docker image gắn 2 tag (`$COMMIT_SHA` để truy vết phiên bản và `latest`), tận dụng `--cache-from` từ image `latest` trước đó để tăng tốc layer caching.
3. **`push`**: Đẩy tất cả tags của image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy` (`gcr.io/cloud-builders/gcloud`)**: Deploy image `:$COMMIT_SHA` lên **Cloud Run** (`asia-southeast1`), cấu hình kèm trong `service.yaml` (Knative spec): giữ `minScale: 1` (tránh cold start), `maxScale: 10`, `containerConcurrency: 80`, giới hạn `1 CPU / 512Mi RAM`, đọc secret an toàn từ **Secret Manager** (`secretKeyRef`), và kiểm tra sức khỏe bằng `startupProbe` (`/ready`) + `livenessProbe` (`/health`).

---

## Part 6: Final Project (`06-lab-complete/`)

Kết quả chạy `python check_production_ready.py` đầy đủ (43/43 checks):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Usage Log (Theo quy định tại `RULES.md`)

1. **Hỏi & hỗ trợ cấu trúc bài lab (Part 1 – Part 5):**
   - *Nội dung hỏi:* Nhờ AI đọc cấu trúc dự án, giải thích sự khác biệt giữa bản `develop` và `production` ở các phần 12-Factor, Multi-stage Docker, JWT/Rate Limiting/Cost Guard và Stateless Redis scaling, đồng thời hỗ trợ cú pháp lệnh `curl.exe` trên Windows PowerShell.
   - *Kết quả nhận được & Tự kiểm chứng:* Chạy trực tiếp từng container và server trên máy cá nhân, tự thu thập số đo thực tế (`my-agent:develop` = `1.67 GB` vs `my-agent:advanced` = `240 MB`, chuỗi mã `401 -> 200 -> 429`, và kết quả `test_stateless.py` qua 3 instance).
2. **Triển khai Part 6 (`06-lab-complete/`):**
   - *Nội dung hỏi:* Gợi ý hoàn thiện các `TODO` trong `app/config.py`, `app/redis_client.py`, `app/auth.py`, `app/rate_limiter.py` (Redis Sorted Set sliding window), `app/cost_guard.py` (`INCRBYFLOAT`), `app/main.py` (`JsonFormatter` + `lifespan` + `SIGTERM` forwarding), multi-stage `Dockerfile` và `docker-compose.yml` / `railway.toml` / `render.yaml`.
   - *Tự kiểm tra:* Chạy trực tiếp script `check_production_ready.py` trong môi trường Linux + Docker Engine, xác nhận vượt qua toàn bộ **43/43 checks (`PASS 12/12`)** (image nặng `238 MB`, `docker stop` tắt êm trong `0.9s`).
3. **Chạy & phân tích số liệu Part 7 (`benchmark-observability/`):**
   - *Nội dung hỏi:* Hỗ trợ bổ sung 2 mục thiếu (`jwt`/`api key` và `kubernetes`/`hpa`) vào `KNOWLEDGE_BASE` trong `mock_llm.py`, sửa biến `PYTHONUSERBASE=/home/agent/.local` trong `production/Dockerfile` để container agent khởi chạy đúng với user non-root, và viết workflow CI `.github/workflows/eval-quality-gate.yml`.
   - *Tự kiểm tra:* Mọi con số trong `BENCHMARK_REPORT.md` đều được lấy trực tiếp từ các file JSON (`reports/`), CSV (`benchmark-results/`) và log/trace thực tế trên máy, đảm bảo khớp 100% và `run_eval.py --min-accuracy 1.0` đạt `23/23 PASS`.
