#!/usr/bin/env python3
"""
Benchmark TTS pipeline: FastAPI -> Celery -> Redis -> GPU -> LipSync

Cach dung:
    python bench.py [concurrency] [total] [stream]

Vi du:
    python bench.py              # concurrency=1, total=3, non-streaming
    python bench.py 4 5          # concurrency=4, total=5
    python bench.py 1 3 true     # streaming mode
"""

import asyncio
import statistics
import sys
import time

import httpx
import psutil

BASE_URL = "http://localhost:8100/api/v1/tts"

# Van ban ngan de test nhanh
TEXT_SHORT = [
    "Xin chào các bạn. Đây là bài test TTS.",
    "Hôm nay thời tiết rất đẹp. Tôi rất vui.",
    "Đây là văn bản thứ ba trong bài test.",
]

# Van ban dai (Tuong vuong lich su)
TEXT_LONG = ["Ta thường nghe: Kỷ Tín lấy thân chết thay, cứu thoát được vua Cao-đế; Do Vu chìa lưng chịu giáo che chở được vua Chiêu-vương; Dự Nhượng nuốt than để trả thù cho thầy; Thân Khoái chặt tay để gánh nạn cho nước; Uất Trì Cung một viên tướng nhỏ, còn biết che đỡ Đường-chủ, ra khỏi vòng vây của Thế Sung; Nhan Cảo-Khanh là bầy tôi xa, còn biết mắng chửi Lộc Sơn, không nghe lời dụ của nghịch-tặc. Từ xưa, những bậc trung-thần nghĩa-sĩ, lấy thân theo nước, đời nào là không có đâu? Nếu mấy người kia, chăm chăm học thói dút-dát của con gái trẻ con, chẳng qua cũng đến chết dũ ở dưới cửa sổ, đâu được ghi tên vào trong thẻ tre lụa trắng, danh tiếng cùng trời đất cùng lâu bền? Các người đời đời là con nhà võ, không biết chữ nghĩa, nghe những chuyện ấy, thảy đều nửa tin nửa ngờ. Thôi thì những việc cổ xưa, hãy để đó không nói đến nữa. Nay ta hãy đem chuyện nước Tống, giống Thát(là chuyện gần đây) kể cho các người cùng nghe: Vương công Kiên là người gì? Nguyễn văn Lập tỳ-tướng của y lại là người gì, chỉ có vòng thành Điếu-ngư nhỏ bằng cái đấu hai người ấy chống nổi toán quân trăm vạn của Mông-kha, khiến cho con dân nước Tống, đến nay hãy còn nhớ ơn. Đường ngột Ngại là người gì? Xích tu Tư tỳ-tướng của y lại là người gì? xông pha lam-chướng trên đuờng muôn dặm, hai người ấy đánh được quân Nam-chiếu trong vài tuần, khiến cho vua chúa giòng Thát nay còn để tiếng! Huống chi ta với các ngươi, sinh ở buổi rối ren, lớn lên nhằm khi khó nhọc, chính mắt ngó thấy sứ ngụy đi lại, đường xá nghẽn-ngang, chúng múa cái lưỡi cú quạ làm nhục chốn triều-đình, chúng giơ cái thân chó dê, kiêu ngạo với quan tể-phụ; chúng nhờ mệnh lệnh của chúa Mông-Cổ, mà đòi nào ngọc nào lụa, sự vòi vĩnh thật vô cùng; chúng mượn danh hiệu của vua Vân-nam mà hạch nào bạc nào vàng; của kho đụn đã hồ hết Cung-đốn cho chúng giống như đem thịt mà liệng cho cọp đói, sao cho khỏi lo về sau?",
        "Ta thường thì tới bữa quên ăn, giữa đêm vỗ gối, nước mắt tràn xuống đầy mép, tấm lòng đau như bị đâm, vẫn lấy cái sự chưa thể ăn thịt nằm da, nuốt gan uống máu của chúng làm tức. Dẫu cho một trăm cái thân của ta phải đem đốt ở đồng cỏ, một nghìn cái thân của ta phải đem bọc vào da ngựa, ta cũng vui lòng. Các ngươi lâu nay ở dưới cửa ta cầm giữ binh-quyền, thiếu áo thì mặc áo cho, thiếu ăn thì sẻ cơm đỡ, quan nhỏ thì cho lên chức, bổng ít cho thêm lương, đi thủy cấp thuyền, đi bộ cấp ngựa, những khi trận mạc, sự sống thác thầy chung với trò, những lúc mừng khao, tiếng vui cười ai cũng như nấy. So với Công Kiên làm chức thiên-lý, Ngột Ngại ở ngôi phó nhị, có khác gì đâu. Thế mà các ngươi thấy chủ bị nhục chẳng lấy làm lo, gặp nước bị dơ chẳng lấy làm thẹn, làm tướng nhà nước phải hầu mấy đứa chum mường, mà không có lòng căm hờn, nghe khúc nhạc thờ đem thết một tên ngụy sứ, mà không có vẻ tức giận; kẻ thì chọi gà cho thích, kẻ thì đánh bạc mua vui, có người chỉ chăm vườn ruộng, cốt nuôi được nhà; có người chỉ mến vợ con, lấy mình làm trọng; cũng có kẻ chỉ lo làm giàu làm có, việc quân quốc chẳng thèm đoái hoài, cũng có người chỉ ham về săn-bắn mà quên việc binh, hoặc là đam mùi rượu ngọt, hoặc là mê tiếng hát hay. Một khi giặc Mông đến nơi, thì cựa con gà nòi không thể đâm thủng áo-giáp của giặc; thuật ở bàn bạc không thể đem làm mưu mẹo ở trong quân; vườn ruộng tuy giàu, tấm thân ấy nghìn vàng khôn chuộc; vợ con tuy sẳn, trong đám ba quân khó dùng, của cải tuy nhiều, không thể mua được đầu giặc; chó săn tuy khỏe, không thể đuổi được quân thù, rượu ngon không đủ để cho giặc phải mê; hát hay không đủ làm cho giặc phải điếc; lúc đó thầy trò ta sẽ cùng bị trói, đáng đau đớn biết chừng nào! Nếu thế, chẳng những là thái-ấp của ta không còn, mà bổng-lộc của các ngươi cũng bị kẻ khác chiếm mất; chẳng những là gia- quyến của ta phải đuổi, mà vợ con của các ngươi cũng bị kẻ khác bắt đi; chẳng những xã tắc của tổ tông ta sẽ bị dày xéo, mà đến mồ mả của cha mẹ ngươi cũng sẽ bị kẻ khác đào lên, chẳng những thân ta kiếp này chịu nhục, và trăm kiếp khác tiếng nhơ khôn rửa, tên xấu vẫn còn, mà gia thanh của các ngươi cũng chẵng khỏi mang tiếng là nhà bại tướng. Đã đến khi đó các ngươi muốn chơi bời cho thỏa, được chăng?,",
        "Nay ta bảo rõ các ngươi: cái chuyện dấm lửa đống củi phải lo, mà câu sợ canh thổi rau nên nhớ. Các ngươi hãy nên huấn luyện quân-sĩ, rèn-tập cung tên, khiến cho người người giỏi như Bàng Mông, nhà nhà đều là Hậu Nghệ, bêu đầu Tất-Liệt dưới cửa khuyết, ướp thịt Thoát-Hoan trong trại rơm. Như thế chẳng những là thái-ấp của ta mãi mãi là của gia truyền, mà bổng-lộc các ngươi cũng được suốt đời hưởng thụ; chẳng những gia- quyến của ta được yên giường nệm, mà vợ con các ngươi cũng được sum họp đến già; chẳng những là tông-miếu ta sẽ được muôn đời tế lễ, mà tổ tông các ngươi cũng được thờ cúng quanh năm; chẳng những thân ta kiếp này đắc chí, mà đến các người dưới trăm đời nữa tiếng thơm vẫn lưu truyền; chẳng những tên tuổi ta không bị mai một, mà đến tên họ các người cũng để tiêng thơm trong sử xanh. Khi ấy các ngươi không muốn vui chơi, được chăng? Nay ta lựa chọn binh pháp các nhà, làm một quyển sách, đặt tên là sách Binh-thư yếu-lược. Nếu các ngươi biết chuyên-tập sách ấy, nghe lời dạy-bảo của ta, ấy là duyên thầy trò kiếp xưa; Nếu các ngươi bỏ bê sách ấy, trái lời dạy-bảo của ta, ấy là mối cựu thù kiếp xưa, Sao vậy? Bởi vì như vậy tức là kẻ thù không đội chung trời, thế mà các ngươi không nghĩ tới, điềm nhiên không lo đến sự rửa thẹn, không tinh; đến việc trừ hung, không nhớ đến chuyện dạy-tập quân-sĩ. Thế là giở giáo hàng giặc, nắm tay chống giặc. Rồi đây, sau khi dẹp yên quân giặc, các ngươi sẽ phải thẹn muôn đời, còn mặt-mũi nào đứng giữa khoảng trời đất che chở? Ta muốn các ngươi biết rõ bụng ta, nhân viết mấy lời đó làm hịch.",
        "Trong chuyến xe đi Lào Cai, bác lái xe, nhà họa sĩ lão thành, cô kỹ sư trẻ trò chuyện với nhau về Sa Pa, hội họa, hạnh phúc và tình yêu. Khi chuyến xe dừng lại cho hành khách nghỉ ngơi, bác lái xe giới thiệu với ông họa sĩ và cô kỹ sư về một người cô độc nhất thế gian. Đó là anh thanh niên 27 tuổi làm công tác khí tượng kiêm vật lý địa cầu trên đỉnh Yên Sơn cao 2600 mét. Anh thanh niên biếu vợ bác lái xe một củ tam thất và mời ông họa sĩ cùng cô gái trẻ lên nhà chơi. Cả hai ngỡ ngàng thấy vườn hoa thật đẹp. Nơi ở của anh gọn gàng ngăn nắp. Anh mời mọi người vào nhà chơi, uống trà và nói chuyện. Anh sống và làm việc tại đây, nhiệm vụ của anh là đo gió, đo mưa, dự báo thời tiết hàng ngày phục vụ sản xuất và chiến đấu. Tuy công việc của anh gian khổ nhưng anh rất yêu nó và luôn hoàn thành nhiệm vụ. Ngoài ra anh cũng thích đọc sách, trồng cây thuốc, hoa, nuôi gà. Nghe anh kể chuyện ông họa sĩ đã phác họa chân dung anh nhưng anh cho rằng mình không xứng đáng, rồi giới thiệu ông họa sĩ về ông kỹ sư vườn rau và đồng chí cán bộ nghiên cứu bản đồ sét, những người cũng làm việc ở Sa Pa. Sau ba mươi phút nói chuyện, đến lúc chia tay, anh tặng hai người giỏ trứng để đi đường. Cô kỹ sư từ cuộc nói chuyện với anh thanh niên đã yên tâm, quyết định lên vùng cao công tác, còn ông họa sĩ tìm được nguồn cảm hứng nghệ thuật.",
        "Anh thanh niên: 27 tuổi, làm công tác khí tượng kiêm vật lý địa cầu trên đỉnh Yên Sơn cao 2600 mét. Anh là một con người có tinh thần trách nhiệm với công việc và luôn hết mình vì công việc. Vì công việc nên anh phải sống một mình ở trên đỉnh núi cao bốn bề chỉ có cây cỏ. Luôn hoàn thành xuất sắc nhiệm vụ của mình: góp phần phát hiện đám mây khô giúp không quân ta hạ máy bay Mỹ. Lạc quan, yêu đời: anh tự tạo cho mình những thú vui nhỏ như trồng hoa, đọc sách, nuôi gà, ...Sống ngăn nắp, gọn gàng. Anh thanh niên là một người cởi mở, chân thành và hiếu khách. Anh còn là một người rất khiêm tốn: Khi ông hoạ sĩ muốn vẽ anh, anh đã đề nghị giới thiệu người khác vì cảm thấy họ xứng đáng hơn. Người hoạ sĩ: Là một người hoạ sĩ tâm huyết với nghề, người nghệ sĩ chân chính. Cả đời tìm kiếm cái đẹp, khao khát truyền tải tấm lòng của người hoạ sĩ vào sáng tác của mình. Là một người yêu nghề, đã sống với nghề được ba mươi hai năm, từ trước cách mạng tháng Tám. Khi bắt gặp anh thanh niên, ông biết đó là cơ hội, thử thách của mình. Cô kĩ sư trẻ: Vừa mới đỗ kĩ sư, đi nhận việc ở Ti nông nghiệp Lai Châu. Băn khoăn về cuộc đời, chưa tìm được hướng đi cho mình. Sau khi gặp anh thanh niên, cô thấy mình bàng hoàng: hiểu về cuộc sống, thế giới của anh thanh niên, cũng như con đường cô đang đi tới."
        ]

# Chon TEXT theo muc dich
TEXT = TEXT_SHORT  # Dung SHORT cho test nhanh, doi thanh LONG de benchmark that su

POLL_INTERVAL = 1   # Giay giua moi lan poll
POLL_TIMEOUT = 600  # Timeout toi da (10 phut)


def get_text(i: int) -> str:
    """Lay text theo index, quay vo (wrap-around) neu het."""
    return TEXT[i % len(TEXT)]


async def poll_task(client, task_id: str) -> dict:
    """
    Poll trang thai task cho den khi thanh cong/that bai/timeout.

    Returns:
        dict voi status, message, lipsync_response, _poll_time
    """
    t0 = time.perf_counter()
    while True:
        r = await client.get(f"{BASE_URL}/status/{task_id}")
        data = r.json()
        status = data["status"]

        if status in ("success", "error"):
            data["_poll_time"] = time.perf_counter() - t0
            return data

        if time.perf_counter() - t0 > POLL_TIMEOUT:
            return {"status": "timeout", "_poll_time": POLL_TIMEOUT, "message": "Poll timeout"}

        await asyncio.sleep(POLL_INTERVAL)


async def single_run(client, sem: asyncio.Semaphore, i: int, stream: bool = False) -> dict:
    """
    Chay 1 request TTS: generate -> poll -> get result.

    Args:
        client: httpx async client
        sem: Semaphore de gioi han concurrency
        i: Index cua request
        stream: Streaming mode hay khong

    Returns:
        dict voi ket qua
    """
    async with sem:
        t0 = time.perf_counter()
        text = get_text(i)

        # Gui request generate
        payload = {
            "text": text,
            "voice_id": "001",
            "speed": 1.0,
            "stream": stream,
        }

        try:
            r = await client.post(
                f"{BASE_URL}/generate",
                json=payload,
                timeout=30,
            )
        except Exception as e:
            return {"ok": False, "i": i, "error": str(e), "text_len": len(text)}

        if r.status_code != 200:
            return {
                "ok": False,
                "i": i,
                "error": f"HTTP {r.status_code}",
                "detail": r.text[:200],
                "text_len": len(text),
            }

        task_id = r.json()["task_id"]

        # Poll ket qua
        result = await poll_task(client, task_id)
        total_time = time.perf_counter() - t0

        ok = result["status"] == "success"
        return {
            "ok": ok,
            "i": i,
            "task_id": task_id,
            "status": result["status"],
            "total_time": total_time,
            "poll_time": result.get("_poll_time", 0),
            "lipsync_response": result.get("lipsync_response"),
            "message": result.get("message"),
            "text_len": len(text),
            **({} if ok else {"error": result.get("message", "unknown-error")}),
        }


async def bench(concurrency: int = 1, total: int = 3, stream: bool = False):
    """
    Chay benchmark voi so luong request va concurrency cho truoc.

    Args:
        concurrency: So request chay dong thoi
        total: Tong so request
        stream: Streaming mode hay khong
    """
    proc = psutil.Process()
    ram_before = proc.memory_info().rss / 1024**3

    sem = asyncio.Semaphore(concurrency)
    mode = "streaming" if stream else "non-streaming"

    print(f"MODE: {mode}")
    print(f"TEXT: {len(TEXT)} xau, {len(TEXT[0])} chars/xau")
    print()

    async with httpx.AsyncClient(timeout=600) as client:
        # === WARMUP ===
        print("[warmup] Dang warmup...")
        try:
            r = await client.post(
                f"{BASE_URL}/generate",
                json={"text": "Xin chào. Đây là bài test.", "voice_id": "001"},
                timeout=30,
            )
        except Exception as e:
            print(f"[warmup] LOI: {e}")
            print("  → FastAPI server co dang chay o port 8100 khong?")
            return

        if r.status_code == 200:
            task_id = r.json()["task_id"]
            result = await poll_task(client, task_id)
            if result["status"] == "success":
                print(f"[warmup] Done ({result['_poll_time']:.1f}s)")
            else:
                print(f"[warmup] That bai: {result}")
                return
        else:
            print(f"[warmup] API tra {r.status_code}: {r.text[:200]}")
            return

        ram_after = proc.memory_info().rss / 1024**3

        # === BENCHMARK ===
        print(f"\n[bench] {total} requests, concurrency={concurrency}, mode={mode}\n")

        tasks = [single_run(client, sem, i, stream) for i in range(total)]
        t_start = time.perf_counter()
        results = await asyncio.gather(*tasks)
        wall_time = time.perf_counter() - t_start

    # === PHAN TICH ===
    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    times = [r["total_time"] for r in ok]

    print("=" * 60)
    print(f"  MODE              {mode}")
    print(f"  CONCURRENCY       {concurrency}")
    print(f"  TOTAL             {total}")
    print(f"  WALL CLOCK        {wall_time:.1f}s")
    print(f"  SUCCESS           {len(ok)}/{len(results)}")
    print("-" * 60)

    if fail:
        print(f"  FAILURES          {len(fail)}:")
        for f in fail:
            print(f"    [{f['i']}] text_len={f.get('text_len','?')} error={f.get('error','?')[:80]}")
        print("-" * 60)

    if times:
        # In tung request
        print("  PER REQUEST:")
        for idx, t in enumerate(sorted(times)):
            text_len = [r["text_len"] for r in ok if r["total_time"] == t][0]
            print(f"    {t:6.1f}s  ({text_len} chars)")

        print()
        print(f"  THROUGHPUT        {len(ok)/wall_time:.2f} req/s")
        print(f"  LATENCY (end-to-end):")
        print(f"    MIN    {min(times):.1f}s")
        print(f"    MAX    {max(times):.1f}s")
        print(f"    AVG    {statistics.mean(times):.1f}s")
        if len(times) > 1:
            print(f"    STDEV  {statistics.stdev(times):.1f}s")
        print(f"    MEDIAN {statistics.median(times):.1f}s")
    else:
        print("  → Khong request nao thanh cong de tinh latency")
    print("-" * 60)

    ram_current = proc.memory_info().rss / 1024**3
    print(f"  RAM process:")
    print(f"    before:  {ram_before:.2f} GB")
    print(f"    warmup:  {ram_after:.2f} GB (+{ram_after-ram_before:.2f} GB)")
    print(f"    after:   {ram_current:.2f} GB")
    print("=" * 60)


if __name__ == "__main__":
    c = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    s = sys.argv[3].lower() in ("true", "1", "yes") if len(sys.argv) > 3 else False
    asyncio.run(bench(c, n, s))
