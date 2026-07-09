#!/usr/bin/env python3
"""Benchmark full pipeline: FastAPI -> Celery -> Redis -> GPU -> response."""

import asyncio
import statistics
import sys
import time

import httpx
import psutil

BASE_URL = "http://localhost:8000/api/v1/tts"
TEXT = (
    "Xin chào, tôi là trợ lý ảo, có thể giúp gì cho bạn hôm nay? "
    "Tôi có thể đọc văn bản tiếng Việt rất tự nhiên."
)
POLL_INTERVAL = 0.5
POLL_TIMEOUT = 300  # 5 phút tối đa cho 1 task


async def poll_task(client, task_id: str) -> dict:
    """Poll /status cho đên khi success/error hoặc timeout."""
    t0 = time.perf_counter()
    while True:
        r = await client.get(f"{BASE_URL}/status/{task_id}")
        data = r.json()
        status = data["status"]
        if status in ("success", "error"):
            data["_poll_time"] = time.perf_counter() - t0
            return data
        if time.perf_counter() - t0 > POLL_TIMEOUT:
            return {"status": "timeout", "_poll_time": POLL_TIMEOUT}
        await asyncio.sleep(POLL_INTERVAL)


async def single_run(client, sem: asyncio.Semaphore, i: int) -> dict:
    """Một request hoàn chỉnh: generate -> poll -> kết quả."""
    async with sem:
        t0 = time.perf_counter()

        # 1. Gửi request
        try:
            r = await client.post(
                f"{BASE_URL}/generate",
                json={"text": TEXT, "speed": 1.0},
                timeout=10,
            )
        except Exception as e:
            return {"ok": False, "i": i, "phase": "post", "error": str(e)}

        if r.status_code != 200:
            return {"ok": False, "i": i, "phase": "post", "error": f"HTTP {r.status_code}", "detail": r.text}

        task_id = r.json()["task_id"]

        # 2. Poll kết quả
        result = await poll_task(client, task_id)
        total_time = time.perf_counter() - t0

        ok = result["status"] == "success"
        return {
            "ok": ok,
            "i": i,
            "task_id": task_id,
            "status": result["status"],
            "total_time": total_time,
            "poll_time": result.get("_poll_time"),
            "audio_url": result.get("audio_url"),
            "message": result.get("message"),
        }


async def bench(concurrency: int = 2, total: int = 5):
    proc = psutil.Process()
    ram_before = proc.memory_info().rss / 1024**3

    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=300) as client:
        # Warmup
        print("[warmup] Starting...")
        r = await client.post(
            f"{BASE_URL}/generate",
            json={"text": "warmup"},
            timeout=10,
        )
        if r.status_code == 200:
            task_id = r.json()["task_id"]
            await poll_task(client, task_id)
            print("[warmup] Done (model loaded)")
        else:
            print(f"[warmup] Bỏ qua — API trả {r.status_code}, có thể Redis chưa chạy?")
            print(f"  {r.text}")
            return

        ram_after = proc.memory_info().rss / 1024**3

        # Benchmark
        print(f"\n[bench] Chạy {total} request, concurrency={concurrency}...\n")
        tasks = [single_run(client, sem, i) for i in range(total)]
        t_start = time.perf_counter()
        results = await asyncio.gather(*tasks)
        wall_time = time.perf_counter() - t_start

    # Xử lý kết quả
    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    times = [r["total_time"] for r in ok]

    # divider
    print("=" * 55)
    print(f"  CONCURRENCY        {concurrency}")
    print(f"  TOTAL REQUESTS     {total}")
    print(f"  WALL CLOCK         {wall_time:.1f}s")
    print(f"  SUCCESS            {len(ok)}/{len(results)}")
    print("-" * 55)

    if fail:
        print(f"  FAILURES           {len(fail)}:")
        for f in fail[:5]:
            print(f"    [{f['i']}] {f.get('phase')}: {f.get('error')}")
        print("-" * 55)

    if times:
        print(f"  THROUGHPUT         {len(ok)/wall_time:.2f} req/s  ({len(ok)*60/wall_time:.0f} req/min)")
        print(f"  LATENCY (end-to-end, gồm queue + generate):")
        print(f"    MIN              {min(times):.1f}s")
        print(f"    MAX              {max(times):.1f}s")
        print(f"    AVG              {statistics.mean(times):.1f}s")
        print(f"    MEDIAN           {statistics.median(times):.1f}s")
        if len(times) >= 2:
            print(f"    P95              {sorted(times)[int(len(times)*0.95)]:.1f}s")
            print(f"    STDEV            {statistics.stdev(times):.1f}s")
        print("-" * 55)

    ram_current = proc.memory_info().rss / 1024**3
    print(f"  RAM (process only):")
    print(f"    TRƯỚC WARMUP      {ram_before:.2f} GB")
    print(f"    SAU WARMUP        {ram_after:.2f} GB  (+{ram_after-ram_before:.2f} GB)")
    print(f"    AFTER BENCH       {ram_current:.2f} GB")
    print("=" * 55)

    print("\n📌 NHẮC: đo VRAM riêng bằng: watch -n 1 nvidia-smi")
    print()


if __name__ == "__main__":
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    total = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    asyncio.run(bench(concurrency, total))
