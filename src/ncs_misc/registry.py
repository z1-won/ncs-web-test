"""규칙 등록. 기타 ①~⑧ — ③ 제품명 사전, ④ 캡처 화면 픽셀, ⑤⑧ 실효 DPI(ncs_misc.images)."""

from ncs_core import Rule

from .rules.brand_names import check_brand_names
from .rules.form_images import check_form_images
from .rules.page_starts import check_page_starts
from .rules.pictures import check_pictures
from .rules.ratio import check_ratio
from .rules.references import check_references
from .rules.resolution import check_resolution
from .rules.screenshots import check_screenshots

DEFAULT_RULES = (
    Rule("page_starts", "F02-기타-①", check_page_starts),
    Rule("pictures", "F02-기타-②", check_pictures),
    Rule("brand_names", "F02-기타-③", check_brand_names),
    Rule("screenshots", "F02-기타-④", check_screenshots),
    Rule("resolution", "F02-기타-⑤", check_resolution),
    Rule("ratio", "F02-기타-⑥", check_ratio),
    Rule("references", "F02-기타-⑦", check_references),
    Rule("form_images", "F02-기타-⑧", check_form_images),
)

ALL_ITEM_IDS = tuple("F02-기타-" + n for n in "①②③④⑤⑥⑦⑧")
