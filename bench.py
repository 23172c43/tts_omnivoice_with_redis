#!/usr/bin/env python3
"""Benchmark full pipeline: FastAPI -> Celery -> Redis -> GPU -> response."""

import asyncio
import statistics
import sys
import time

import httpx
import psutil

BASE_URL = "http://localhost:8100/api/v1/tts"
TEXT = (
    "Xin chào, tôi là trợ lý ảo, có thể giúp gì cho bạn hôm nay? "
    "Tôi có thể đọc văn bản tiếng Việt rất tự nhiên."
)
POLL_INTERVAL = 1
POLL_TIMEOUT = 600


async def poll_task(client, task_id: str) -> dict:
    t0 = time.perf_counter()
    while True:
        r = await client.get(f"{BASE_URL}/status/{task_id}")
        data = r.json()
        status = data["status"]
        if status in ("success", "error"):
            data["_poll_time"] = time.perf_counter() - t0
            return data
        if time.perf_counter() - t0 > POLL_TIMEOUT:
            return {"status": "timeout", "_poll_time": POLL_TIMEOUT, "message": None}
        await asyncio.sleep(POLL_INTERVAL)


async def single_run(client, sem: asyncio.Semaphore, i: int) -> dict:
    async with sem:
        t0 = time.perf_counter()

        # 1. Gửi request generate
        try:
            r = await client.post(
                f"{BASE_URL}/generate",
                json={"text": TEXT, "speed": 1.0},
                timeout=10,
            )
        except Exception as e:
            return {"ok": False, "i": i, "error": str(e)}

        if r.status_code != 200:
            return {"ok": False, "i": i, "error": f"HTTP {r.status_code}", "detail": r.text}

        task_id = r.json()["task_id"]

        # 2. Poll kết quả
        result = await poll_task(client, task_id)
        total_time = time.perf_counter() - t0

        ok = result["status"] == "success"
        rv = {
            "ok": ok,
            "i": i,
            "task_id": task_id,
            "status": result["status"],
            "total_time": total_time,
            "audio_url": result.get("audio_url"),
            "message": result.get("message"),
        }
        if not ok:
            rv["error"] = result.get("message", "unknown-error")
        return rv


async def bench(concurrency: int = 1, total: int = 3):
    proc = psutil.Process()
    ram_before = proc.memory_info().rss / 1024**3

    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=600) as client:
        # Warmup
        print("[warmup] Starting...")
        try:
            r = await client.post(
                f"{BASE_URL}/generate",
                json={"text": "warmup"},
                timeout=30,
            )
        except Exception as e:
            print(f"[warmup] LỖI: {e}")
            print("  → FastAPI server có đang chạy ở port 8100 ko?")
            return

        if r.status_code == 200:
            task_id = r.json()["task_id"]
            print(f"[warmup] Task {task_id}, đợi generate...")
            result = await poll_task(client, task_id)
            if result["status"] == "success":
                print(f"[warmup] Done ({result['_poll_time']:.1f}s)")
            else:
                print(f"[warmup] Thất bại: {result}")
                return
        else:
            print(f"[warmup] API trả {r.status_code}: {r.text}")
            return

        ram_after = proc.memory_info().rss / 1024**3

        # Benchmark
        print(f"\n[bench] {total} requests, concurrency={concurrency}\n")
        tasks = [single_run(client, sem, i) for i in range(total)]
        t_start = time.perf_counter()
        results = await asyncio.gather(*tasks)
        wall_time = time.perf_counter() - t_start

    # Phân tích
    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    times = [r["total_time"] for r in ok]

    print("=" * 55)
    print(f"  CONCURRENCY        {concurrency}")
    print(f"  TOTAL              {total}")
    print(f"  WALL CLOCK         {wall_time:.1f}s")
    print(f"  SUCCESS            {len(ok)}/{len(results)}")
    print("-" * 55)

    if fail:
        print(f"  FAILURES           {len(fail)}:")
        for f in fail:
            print(f"    [{f['i']}] task={f.get('task_id','?')} error={f.get('error','?')}")
        print("-" * 55)

    if times:
        # In từng request
        for t in sorted(times):
            print(f"    {t:.1f}s")
        print()
        print(f"  THROUGHPUT         {len(ok)/wall_time:.2f} req/s")
        print(f"  LATENCY (end-to-end):")
        print(f"    MIN     {min(times):.1f}s")
        print(f"    MAX     {max(times):.1f}s")
        print(f"    AVG     {statistics.mean(times):.1f}s")
        txt = TEXT[:40]
        print(f"    TEXT    '{txt}...' ({len(TEXT)} chars)")
    else:
        print("  → Ko có request nào thành công để tính latency")
    print("-" * 55)

    ram_current = proc.memory_info().rss / 1024**3
    print(f"  RAM process:")
    print(f"    before: {ram_before:.2f} GB")
    print(f"    warmup: {ram_after:.2f} GB (+{ram_after-ram_before:.2f} GB)")
    print(f"    after:  {ram_current:.2f} GB")
    print("=" * 55)
    print()


if __name__ == "__main__":
    c = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    asyncio.run(bench(c, n))
