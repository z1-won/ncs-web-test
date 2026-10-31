"""HWPX 한 섹션 트리에서 이미지 이름과 평가 표를 추출한다."""
import re
from .loader import HP, _hwpx_para_text


def extract_features(root):
    parents = {child: parent for parent in root.iter() for child in parent}
    paragraphs = list(root.iter(HP + "p"))
    positions = {p: i for i, p in enumerate(paragraphs)}

    def owner(element):
        current = parents.get(element)
        while current is not None and current.tag != HP + "p":
            current = parents.get(current)
        return current

    banners = []
    for comment in root.iter(HP + "shapeComment"):
        match = re.search(r"원본 그림의 이름:\s*([^\n]+)", comment.text or "")
        paragraph = owner(comment)
        if match and paragraph in positions:
            banners.append((positions[paragraph], match.group(1).strip()))

    tables = []
    # 각 표를 한 번만 방문하며 가장 가까운 문단의 좌표를 사용한다.
    for table in root.iter(HP + "tbl"):
        paragraph = owner(table)
        if paragraph not in positions:
            continue
        cells = {}
        for row in table.findall(HP + "tr"):
            for cell in row.findall(HP + "tc"):
                address = cell.find(HP + "cellAddr")
                if address is None:
                    raise ValueError("HWPX 표 셀에 cellAddr가 없습니다")
                # 중첩 표는 자체 표로 처리하므로 바깥 셀에 합치지 않는다.
                own_paragraphs = []
                for p in cell.iter(HP + "p"):
                    ancestor = parents.get(p)
                    while ancestor is not None and ancestor.tag != HP + "tc":
                        ancestor = parents.get(ancestor)
                    if ancestor is cell:
                        own_paragraphs.append(_hwpx_para_text(p))
                text = re.sub(r"\s+", " ", " ".join(own_paragraphs)).strip()
                cells[(int(address.get("rowAddr")), int(address.get("colAddr")))] = text
        headers = {}
        for (row, col), value in cells.items():
            key = next((k for k in ("학습내용", "학습목표", "평가항목")
                        if value.replace(" ", "").startswith(k)), None)
            if key and key not in headers:
                headers[key] = row, col
        if "학습내용" not in headers or not ({"학습목표", "평가항목"} & headers.keys()):
            continue
        kind = "평가 준거" if "학습목표" in headers else "평가 방법"
        header_row, content_col = headers["학습내용"]
        values = [v for (r, c), v in sorted(cells.items())
                  if c == content_col and r > header_row and v]
        tables.append((positions[paragraph], kind, values))
    return banners, tables
