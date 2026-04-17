"""Sphinx configuration for the P2P file-sharing project."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

project = "Code Documentation"
author = "Project Group"
release = "1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "rst2pdf.pdfbuilder",
]

exclude_patterns = ["_build"]

html_theme = "alabaster"

autodoc_member_order = "bysource"
add_module_names = False

pdf_stylesheets = ["sphinx"]
pdf_use_toc = True
pdf_use_index = True
pdf_break_level = 1

pdf_documents = [
    (
        "index",
        "p2p_file_sharing_documentation",
        "Code Documentation",
        "Project Group",
    ),
]