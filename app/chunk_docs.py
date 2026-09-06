import argparse
import hashlib
import json
import os
from pathlib import Path

from config import config
from config.logger_config import setup_logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

logger = setup_logging(__name__)

os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

RAW_DIR = Path(config.RAW_DATA_DIR)
CHUNKS_DIR = Path(config.CHUNKS_DATA_DIR)

CHUNK_TOKENIZER = config.CHUNK_TOKENIZER
CHUNK_SIZE = config.CHUNK_SIZE
CHUNK_OVERLAP = config.CHUNK_OVERLAP
MAX_TOKEN_SIZE = config.MAX_TOKEN_SIZE

TOKENIZER = AutoTokenizer.from_pretrained(CHUNK_TOKENIZER, trust_remote_code=True)

SPLITTER = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
    TOKENIZER,
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", " ", ""],
)


def make_chunk_id(source, chunk_index, content):
    raw = f"{source}::{chunk_index}::{content}".encode()
    return hashlib.sha1(raw).hexdigest()


def chunk_one_record(record, splitter=SPLITTER, tokenizer=TOKENIZER):
    source = record.get("source")
    loc = record.get("loc")
    lastmod = record.get("lastmod")
    content = record.get("content", "")

    output = []

    if not content or not content.strip():
        return output

    text_chunks = splitter.split_text(content)

    for chunk_index, chunk_text in enumerate(text_chunks):
        chunk_text = chunk_text.strip()

        if not chunk_text:
            continue

        n_tokens = len(tokenizer.encode(chunk_text, add_special_tokens=True))
        if n_tokens > MAX_TOKEN_SIZE:
            logger.warning(f"chunk trop long: {n_tokens} tokens (source={source}, index={chunk_index})")

        chunk_id = make_chunk_id(source or "unknown", chunk_index, chunk_text)

        output.append(
            {
                "chunk_id": chunk_id,
                "source": source,
                "loc": loc,
                "lastmod": lastmod,
                "chunk_index": chunk_index,
                "chunk_size": n_tokens,
                "content": chunk_text,
            }
        )

    return output


def run(source_name: str, status=None) -> None:
    docs_pattern = config.docs_pattern(source_name)
    chunks_pattern = config.chunks_pattern(source_name)

    input_files = sorted(RAW_DIR.glob(f"{docs_pattern}*.{config.JSONL_EXT}"))
    logger.info(f"input_files : {input_files}")

    if not input_files:
        logger.info(f"Aucun fichier {docs_pattern}*.{config.JSONL_EXT} trouvé dans {RAW_DIR}")
        if status is not None:
            raise RuntimeError(f"aucun fichier {docs_pattern}*.{config.JSONL_EXT} pour la source '{source_name}'")
        return

    total_files = len(input_files)
    total_chunks = 0
    done_files = 0

    for input_file in input_files:
        output_file = CHUNKS_DIR / input_file.name.replace(docs_pattern, chunks_pattern)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        file_chunks = 0
        with input_file.open("r", encoding="utf-8") as fin:
            with output_file.open("w", encoding="utf-8") as fout:
                for line_num, line in enumerate(fin, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON invalide dans {input_file.name}, ligne {line_num}: {e}")
                        continue

                    chunks = chunk_one_record(record)
                    for chunk in chunks:
                        fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    file_chunks += len(chunks)

        done_files += 1
        total_chunks += file_chunks
        logger.info(f"Terminé {input_file.name} : {file_chunks} chunks")
        if status is not None:
            status.progress(done_files, total_files)
            status.message(f"Terminé {input_file.name}: {file_chunks} chunks ({total_chunks} au total)")

    logger.info(f"Terminé. {total_chunks} chunks au total")


def main():
    parser = argparse.ArgumentParser(description="Découpe les docs brutes en chunks")
    parser.add_argument(
        "--source",
        required=True,
        choices=[source["name"] for source in config.SOURCES],
        help="Nom de la source à chunker",
    )
    args = parser.parse_args()
    run(args.source)


if __name__ == "__main__":
    main()
