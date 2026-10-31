"""코드 선택은 UI에서, 검증은 여기서 수행한다. input()을 호출하지 않는다."""

import re
from pathlib import Path

CODE_PATTERN = r"LM[0-9]{10}_[0-9]+v[0-9]+"


def validate_module_code(code: str) -> str:
    code = code.strip()
    if not re.fullmatch(CODE_PATTERN, code):
        raise ValueError(
            "모듈 코드는 LM + 숫자 10자리 + _ + 숫자 + v + 숫자 형식이어야 합니다."
        )
    if int(code[8:10]) < 1 or int(code[10:12]) < 1:
        raise ValueError("세분류 번호와 능력단위 번호는 01 이상이어야 합니다.")
    return code


def resolve_module_code(manuscript_path: str | Path, override: str = "") -> str:
    if override.strip():
        return validate_module_code(override)
    candidates = list(
        dict.fromkeys(
            re.findall(
                r"(?<![A-Za-z0-9])" + CODE_PATTERN + r"(?![A-Za-z0-9])",
                Path(manuscript_path).name,
            )
        )
    )
    if len(candidates) != 1:
        raise ValueError(
            "원고 파일명의 모듈 코드가 없거나 여러 개입니다. module_code를 지정하세요."
        )
    return validate_module_code(candidates[0])
