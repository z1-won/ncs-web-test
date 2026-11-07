"""규칙 등록. 기타 ①②⑥⑦. ③④⑤⑧은 이미지·사전 기반이라 미구현."""

from ncs_core import Rule

from .rules.page_starts import check_page_starts
from .rules.pictures import check_pictures
from .rules.ratio import check_ratio
from .rules.references import check_references
from .rules.resolution import check_resolution

DEFAULT_RULES = (
    Rule("page_starts", "F02-기타-①", check_page_starts),
    Rule("pictures", "F02-기타-②", check_pictures),
    Rule("resolution", "F02-기타-⑤", check_resolution),
    Rule("ratio", "F02-기타-⑥", check_ratio),
    Rule("references", "F02-기타-⑦", check_references),
)

ALL_ITEM_IDS = tuple("F02-기타-" + n for n in "①②③④⑤⑥⑦⑧")
