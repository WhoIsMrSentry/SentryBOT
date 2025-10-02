from __future__ import annotations
import os
import shutil
from typing import List
import requests
import html2text
from bs4 import BeautifulSoup


def fetch_and_convert(urls: List[str], save_dir: str, cut_offs: List[str] | None = None) -> int:
    if os.path.exists(save_dir):
        shutil.rmtree(save_dir)
    os.makedirs(save_dir, exist_ok=True)

    count = 0
    for url in urls:
        url = url.strip()
        if not url:
            continue
        r = requests.get(url)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, 'html.parser')
        title = soup.find_all('title')[0].get_text().replace(" - Portal Wiki", "")
        content = soup.find_all("div", {"id": "mw-content-text"})[0]

        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.ignore_tables = True

        out_path = os.path.join(save_dir, f"{title}.md")
        with open(out_path, 'w', encoding='utf-8') as outFile:
            outFile.write(h.handle(content.prettify()))
        count += 1

    # apply cut-offs
    if cut_offs:
        for file in os.listdir(save_dir):
            path = os.path.join(save_dir, file)
            if not path.endswith('.md'):
                continue
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(path, 'w', encoding='utf-8') as f:
                for line in lines:
                    if line.strip() in cut_offs:
                        break
                    f.write(line)

    return count
