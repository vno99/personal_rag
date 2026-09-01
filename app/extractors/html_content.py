from bs4 import BeautifulSoup


def extract_from_soup(soup: BeautifulSoup, selector: str | None) -> str:
    """Extrait le texte du conteneur principal d'un HTML.

    Args:
        soup (BeautifulSoup): Le document parsé.
        selector (str | None): Sélecteur CSS (ex: "article", "[role='main']").
            Si None, retombe sur la balise <article>.

    Returns:
        str: Le texte avec un retour à la ligne par paragraphe, ou "".
    """
    if selector:
        element = soup.select_one(selector)
    else:
        element = soup.find("article")

    if not element:
        return ""

    return element.get_text(separator="\n", strip=True)
