"""F02 차례 ①·③·⑤·⑥ 검수 API (Python 3.10+)."""
from .config import CheckConfig
from .pipeline import inspect_files, inspect_documents
from .reporting import save_results

__all__ = ["CheckConfig", "inspect_files", "inspect_documents", "save_results"]
__version__ = "2.0.0"
