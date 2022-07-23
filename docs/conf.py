import os
import sys
from datetime import date

import django

sys.path.insert(0, os.path.abspath(".."))
os.environ["DJANGO_SETTINGS_MODULE"] = "cobalt.settings"
django.setup()

from cobalt.version import COBALT_VERSION  # noqa: E402

release = COBALT_VERSION
project = "Cobalt"
current_year = date.today().year
copyright = f"{current_year}, ABF, v{release}"
author = "ABF"

extensions = [
    #     "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "*/*.migrations.rst"]

todo_include_todos = True
# html_theme = "sphinx_rtd_theme"
# html_theme = 'pydata_sphinx_theme'
html_theme = "sphinx_book_theme"

# Set the background to pure white to avoid slight differences with images
html_static_path = ["_static"]

html_logo = "images/cobalt.jpg"

html_theme_options = {
    "navigation_depth": 4,
}


def setup(app):
    app.add_css_file("css/cobalt.css")
