"""한 번 읽은 HWPX 트리에서 문단과 구조 정보를 함께 추출한다."""
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from .loader import HP, detect_format, _load_hwp, _hwpx_para_text
from .models import Document
from .xml_features import extract_features


def load_document(path):
    path = Path(path)
    fmt = detect_format(path)
    clean = lambda text: re.sub(r"\s+", " ", text).strip()
    if fmt == "hwp":
        return Document(path, fmt, [[clean(p) for p in s] for s in _load_hwp(path)])
    sections, banners, tables = [], [], {}
    with zipfile.ZipFile(path) as archive:
        names = sorted((n for n in archive.namelist()
                        if re.fullmatch(r"Contents/section\d+\.xml", n)),
                       key=lambda n: int(re.search(r"\d+", n).group()))
        for index, name in enumerate(names):
            root = ET.fromstring(archive.read(name))
            sections.append([clean(_hwpx_para_text(p)) for p in root.iter(HP + "p")])
            images, evaluation = extract_features(root)
            banners.extend((index, paragraph, name) for paragraph, name in images)
            tables[index] = evaluation
    return Document(path, fmt, sections, banners, tables)
