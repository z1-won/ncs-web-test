"""모듈 코드 검증과 파일명 추출. input()을 호출하지 않는다."""

import re
from pathlib import Path

CODE_PATTERN = r"LM[0-9]{10}_[0-9]+v[0-9]+"
CODE_IN_NAME = re.compile(r"(?<![A-Za-z0-9])" + CODE_PATTERN + r"(?![A-Za-z0-9])")


def validate_module_code(code: str) -> str:
    code = (code or "").strip()
    if not re.fullmatch(CODE_PATTERN, code):
        raise ValueError("모듈 코드는 LM + 숫자 10자리 + _ + 숫자 + v + 숫자 형식이어야 합니다")
    if int(code[8:10]) < 1 or int(code[10:12]) < 1:
        raise ValueError("세분류 번호와 능력단위 번호는 01 이상이어야 합니다")
    return code


def resolve_module_code(manuscript_path, override: str | None = "") -> str:
    """override가 있으면 검증해 쓰고, 없으면 원고 파일명에서 하나뿐인 코드를 찾는다."""
    if override and override.strip():
        return validate_module_code(override)
    candidates = list(dict.fromkeys(CODE_IN_NAME.findall(Path(manuscript_path).name)))
    if len(candidates) != 1:
        raise ValueError("원고 파일명의 모듈 코드가 없거나 여러 개입니다. module_code를 지정하세요")
    return validate_module_code(candidates[0])
