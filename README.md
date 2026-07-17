# OmniVoice TTS API

Dịch vụ chuyển văn bản thành giọng nói tiếng Việt bằng OmniVoice. Project sử dụng:

- FastAPI để cung cấp REST API và Swagger.
- Redis làm broker và result backend.
- Celery worker để xử lý TTS bất đồng bộ.
- PyTorch/CUDA để chạy OmniVoice trên GPU.
- Docker Compose để chạy toàn bộ hệ thống.

## Luồng hoạt động

```text
Client
  │
  │ POST /api/v1/tts/generate
  ▼
FastAPI :8989
  │
  │ Gửi task vào tts_queue
  ▼
Redis ◄──────────────► Celery worker + GPU
                           │
                           ├── Chuẩn hóa văn bản
                           ├── Chạy OmniVoice
                           └── Lưu WAV vào /dev/shm/audio

Client polling GET /api/v1/tts/status/{task_id}
```

API hoạt động bất đồng bộ: endpoint `/generate` trả về `task_id`, sau đó client dùng `task_id` để kiểm tra kết quả.

## API hiện có

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| GET | `/` | Thông tin service |
| GET | `/api/v1/health/` | Kiểm tra FastAPI đang chạy |
| GET | `/api/v1/health/ready` | Kiểm tra Redis và model |
| POST | `/api/v1/tts/generate` | Tạo task TTS |
| GET | `/api/v1/tts/status/{task_id}` | Kiểm tra trạng thái task |
| POST | `/api/v1/tts/test` | Chạy model trực tiếp, không qua Celery |

Tài liệu tự động:

- Swagger UI: <http://localhost:8989/docs>
- ReDoc: <http://localhost:8989/redoc>
- OpenAPI JSON: <http://localhost:8989/openapi.json>

## Yêu cầu hệ thống

Để chạy đầy đủ API và sinh âm thanh:

- Linux/Ubuntu.
- Docker Engine.
- Docker Compose V2.
- GPU NVIDIA tương thích CUDA.
- NVIDIA driver.
- NVIDIA Container Toolkit.
- Đủ dung lượng ổ đĩa cho image PyTorch CUDA và model OmniVoice.

Kiểm tra Docker:

```bash
docker --version
docker compose version
```

Kiểm tra Docker đã nhận NVIDIA runtime:

```bash
docker info | grep -i nvidia
```

Nếu không thấy `nvidia`, Celery worker GPU sẽ không khởi động.

## Chạy đầy đủ bằng Docker

### 1. Chuẩn bị thư mục

Từ thư mục gốc của project:

```bash
mkdir -p local_models
sudo mkdir -p /dev/shm/audio
sudo chmod 777 /dev/shm/audio
```

`local_models/` chứa model được tải từ Hugging Face. Thư mục `/dev/shm/audio` là vùng nhớ dùng chung để worker lưu file WAV.

### 2. Build image

```bash
docker compose build
```

Image được tạo với tên:

```text
omnivoice-tts:latest
```

### 3. Khởi động hệ thống

```bash
docker compose up -d
```

Compose sẽ chạy ba service:

- `redis`: hàng đợi và nơi lưu kết quả task.
- `tts_api`: FastAPI trên cổng `8989`.
- `tts_worker`: Celery worker sử dụng GPU.

### 4. Kiểm tra trạng thái

```bash
docker compose ps
docker compose logs --tail=100 tts_api
docker compose logs --tail=100 tts_worker
```

Mở Swagger:

```text
http://localhost:8989/docs
```

Kiểm tra health:

```bash
curl http://localhost:8989/api/v1/health/
curl http://localhost:8989/api/v1/health/ready
```

## Chạy Swagger khi chưa có NVIDIA runtime

Nếu máy chưa cài NVIDIA Container Toolkit, có thể chạy Redis và FastAPI riêng:

```bash
docker compose up -d redis tts_api
```

Sau đó mở:

```text
http://localhost:8989/docs
```

Ở chế độ này Swagger, health API và validation vẫn hoạt động. Tuy nhiên task TTS sẽ không hoàn thành vì không có `tts_worker` xử lý hàng đợi.

## Test tạo giọng nói

### Bước 1: Tạo task

```bash
curl -X POST "http://localhost:8989/api/v1/tts/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Xin chào các bạn, đây là bài kiểm tra OmniVoice.",
    "voice_id": "001",
    "speed": 1.0,
    "stream": false
  }'
```

Kết quả mẫu:

```json
{
  "task_id": "f0a9d159-1f99-4f06-8648-50e551c55d1f",
  "status": "processing",
  "audio_path": null,
  "message": "Task da duoc dua vao hang doi.",
  "mode": null,
  "duration": null
}
```

### Bước 2: Kiểm tra trạng thái

Thay `TASK_ID` bằng ID nhận được ở bước trên:

```bash
curl "http://localhost:8989/api/v1/tts/status/TASK_ID"
```

Khi hoàn thành:

```json
{
  "task_id": "f0a9d159-1f99-4f06-8648-50e551c55d1f",
  "status": "success",
  "audio_path": "/dev/shm/audio/f0a9d159-1f99-4f06-8648-50e551c55d1f.wav",
  "message": null,
  "mode": "non_streaming",
  "duration": 3.2
}
```

`audio_path` hiện là đường dẫn nội bộ dùng chung giữa các service, chưa phải URL tải file công khai.

## Cấu hình

Các cấu hình chính:

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Địa chỉ FastAPI lắng nghe |
| `PORT` | `8989` | Cổng FastAPI |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker/backend |
| `MODEL_DIR` | `local_models/k2-fsa/OmniVoice` | Thư mục model |
| `SAMPLE_RATE` | `24000` | Sample rate của WAV |
| `MAX_CHARS` | `400` | Số ký tự tối đa mỗi đoạn streaming |
| `DEFAULT_VOICE_ID` | `001` | Voice mặc định |

Trong Docker Compose, `REDIS_URL` được đổi thành `redis://redis:6379/0` để API và worker kết nối tới container Redis.

## Các lệnh Docker thường dùng

Xem log liên tục:

```bash
docker compose logs -f
```

Khởi động lại:

```bash
docker compose restart
```

Build lại sau khi sửa code:

```bash
docker compose up -d --build
```

Dừng và xóa container/network:

```bash
docker compose down
```

Dừng và xóa cả volume do Compose quản lý:

```bash
docker compose down -v
```

## Xử lý lỗi thường gặp

### `unknown or invalid runtime name: nvidia`

Máy chưa cài hoặc Docker chưa nhận NVIDIA Container Toolkit. API có thể chạy riêng bằng:

```bash
docker compose up -d redis tts_api
```

Muốn sinh giọng nói cần cài NVIDIA Container Toolkit và khởi động lại Docker daemon.

### Task ở trạng thái `pending` quá lâu

Kiểm tra worker:

```bash
docker compose ps
docker compose logs --tail=100 tts_worker
```

Nguyên nhân thường gặp:

- Worker chưa chạy.
- Redis không healthy.
- Máy không có NVIDIA runtime.
- Model đang được tải lần đầu.

### Readiness trả `degraded`

Kiểm tra:

- Redis đã healthy chưa.
- File `local_models/k2-fsa/OmniVoice/config.json` đã tồn tại chưa.
- Volume model đã được mount đúng chưa.

## Cấu trúc thư mục chính

```text
app/
├── api/v1/endpoints/     # FastAPI endpoints
├── core/config.py        # Cấu hình môi trường
├── schemas/tts.py        # Request/response schemas
├── services/             # OmniVoice và voice tham chiếu
├── utils/                # Chuẩn hóa văn bản
├── worker/               # Celery app và TTS tasks
└── main.py               # FastAPI entrypoint

Dockerfile                # Image dùng chung cho API và worker
docker-compose.yml        # Redis, FastAPI và Celery worker
requirements.txt          # Python dependencies
```

## Trạng thái hiện tại

- FastAPI chạy trên cổng `8989`.
- Swagger và OpenAPI đã được bật.
- API nhận request TTS theo cơ chế Celery bất đồng bộ.
- Docker image dùng chung cho API và worker đã được cấu hình.
- Worker yêu cầu NVIDIA Container Runtime.
- Kết quả âm thanh hiện được trả về dưới dạng đường dẫn nội bộ, chưa có endpoint download WAV.
