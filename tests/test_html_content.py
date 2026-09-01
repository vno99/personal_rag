from bs4 import BeautifulSoup

from extractors.html_content import extract_from_soup


def test_extract_from_article():
    html = "<article><h1>Titre</h1><p>Para 1</p><p>Para 2</p></article><nav>menu</nav>"
    soup = BeautifulSoup(html, "lxml")
    result = extract_from_soup(soup, "article")
    assert "Titre" in result
    assert "Para 1" in result
    assert "menu" not in result


def test_extract_from_role_main():
    html = '<div role="main"><p>Contenu Sphinx</p></div><footer>pied</footer>'
    soup = BeautifulSoup(html, "lxml")
    result = extract_from_soup(soup, "[role='main']")
    assert "Contenu Sphinx" in result
    assert "pied" not in result


def test_extract_empty_when_selector_missing():
    html = "<article></article>"
    soup = BeautifulSoup(html, "lxml")
    assert extract_from_soup(soup, "article") == ""


def test_extract_none_selector_falls_back_to_article():
    html = "<article><p>Fallback</p></article>"
    soup = BeautifulSoup(html, "lxml")
    assert "Fallback" in extract_from_soup(soup, None)
