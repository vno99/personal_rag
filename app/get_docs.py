import json
from pathlib import Path

import config.config as config
from bs4 import BeautifulSoup
from config.logger_config import setup_logging
from langchain_community.document_loaders.sitemap import SitemapLoader

logger = setup_logging(__name__)

SITEMAP_URL = config.SITEMAP_URL
FILTER_URLS = config.FILTER_URLS
DOCS_FILE_PATTERN = config.DOCS_FILE_PATTERN
JSONL_EXT = config.JSONL_EXT
OUTPUT_DIR = Path(config.RAW_DATA_DIR)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
BATCH_SIZE_DOCS = config.BATCH_SIZE_DOCS


def keep_article_element(content: BeautifulSoup):
    """Retrieves the content of the <article> tag from a BeautifulSoup object.

    This function extracts the text content from the first <article> element 
    found in the provided HTML soup.

    Args:
        content (BeautifulSoup): A BeautifulSoup object containing parsed HTML content.

    Returns:
        str: The extracted text content from the <article> element, with newlines 
             preserving paragraph structure and leading/trailing whitespace removed.
             Returns an empty string if no <article> element is found.
    """
    article_element = content.find("article")

    text = ""
    if article_element:
        text = article_element.get_text(separator='\n', strip=True)

    return text


def save_batch(docs, batch_num):
    """Save a batch of documents to a JSONL file.

    Args:
        docs (list): A list of document objects to save. Each document should have a 'metadata' attribute containing 'source', 'loc', and 'lastmod', and a 'page_content' attribute.
        batch_num (int): The batch number to use in the output filename (zero-padded to 3 digits).
    """
    out_file = OUTPUT_DIR / f"{DOCS_FILE_PATTERN}{batch_num:03d}.{JSONL_EXT}"

    with open(out_file, "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps({
                "source": doc.metadata.get("source"),
                "loc": doc.metadata.get("loc"),
                "lastmod": doc.metadata.get("lastmod"),
                "content": doc.page_content
            }, ensure_ascii=False) + "\n")

    logger.info(f"Batch {batch_num} sauvegardé: {len(docs)} documents")


def main():
    logger.info("Début du chargement...")

    blocknum = 0

    # Find all existing batch files and sort them
    existing_batches = sorted(OUTPUT_DIR.glob(f"{DOCS_FILE_PATTERN}*.{JSONL_EXT}"))
    if existing_batches:
        # Extract the batch number from the last file
        # Example: docs_batch_005.jsonl -> 5
        last_batch_str = existing_batches[-1].name.split('_')[-1].split('.')[0]
        blocknum = int(last_batch_str) + 1
        logger.info(f"Reprise détectée au batch {blocknum}")


    while True:
        try:
            logger.info(f"Chargement batch {blocknum}...")

            # Create SitemapLoader to extract documents from sitemap
            loader = SitemapLoader(
                web_path=SITEMAP_URL,
                filter_urls=FILTER_URLS,
                restrict_to_same_domain=True,
                continue_on_failure=True,
                requests_per_second=1,
                blocksize=BATCH_SIZE_DOCS,
                blocknum=blocknum,
                parsing_function=keep_article_element
            )

            # Set custom request headers and timeout
            loader.requests_kwargs = {
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36",
                },
                "timeout": 30,
            }

            # Load documents from the sitemap
            docs = loader.load()

            # If no documents found, break the loop
            if not docs:
                logger.info(f"Batch {blocknum:03d} vide, arrêt.")
                break

            # Save the current batch of documents
            save_batch(docs, blocknum)
            blocknum += 1

            logger.info(f"Batch {blocknum}: {len(docs)} docs")

        except ValueError as e:
            # Handle ValueError related to sitemap blocks
            if "does not contain enough blocks" in str(e):
                logger.info("Fin du sitemap atteinte.")
                break
            else:
                logger.error(f"ValueError inattendue sur batch {blocknum:03d}: {e}")
                break

        except Exception as e:
            # Catch any other unexpected errors
            logger.error(f"Erreur sur batch {blocknum:03d}: {e}")
            break

    logger.info("Terminé.")


if __name__ == "__main__":
    main()