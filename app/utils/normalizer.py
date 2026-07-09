import re
import logging
from vietnam_number import n2w

logger = logging.getLogger(__name__)

def normalize_number_input(text: str) -> str:
    """
    Chuyen so thanh chu, han che overlapping replace.
    Vi du: "60" -> "sau muoi", "606" -> "sau tram le sau"
    """
    numbers = re.findall(r'\d+', text)

    if not numbers:
        return text

    # Sắp xếp số dài nhất trước để tránh replace nhầm số con bên trong
    # Ví dụ: "606" replace trước "60" để "60" trong "606" không bị đụng
    unique_numbers = sorted(set(numbers), key=lambda x: len(x), reverse=True)
    mapping = {num: n2w(num) for num in unique_numbers}

    logger.debug("Normalizing numbers: %s", mapping)

    # Dùng regex để replace chính xác từng số (whole-word match)
    pattern = '|'.join(re.escape(num) for num in sorted(mapping, key=len, reverse=True))

    def replacer(match):
        return mapping[match.group(0)]

    result = re.sub(pattern, replacer, text)
    return result 