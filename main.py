# -*- coding: utf-8 -*-
""" Github Action: Notion 轉換成 Markdown
參考此處 https://github.com/akkuman/notion_to_github_blog

@change 2022/07/23
- 依建立日期來分類markdown
- 新增處理輸入參數的函式
- `and`判斷IsPublish, NeedUpdate

@change 2022/07/22
- 移除 Notion 類的 category
- 判斷執行平台來處理輸入參數

@docs 2022/07/21
- 新增註解

@change 2022/07/19
- markdown yaml header 不自動排序

@change 2022/07/18
- 使用 ini-file 在本機端測試
- 格式化訊息
- 加入 console 訊息保存

@change 2022/07/17
- Notion database 項目修改 (根據 hugo profile 主題)
"""

import hashlib
import os
import re
import time
from urllib.parse import urlparse

import requests
import yaml
from github import Github, GithubException
from notion_client import Client

from notion2md import NotionToMarkdown
from utils import get_logger, get_github_action_arg


logger = get_logger("main_flow")


class Notion:
    """
    連接 Notion API 服務

    Arguments
    - token - str
      Notion API token
      Request API from URL https://www.notion.so/my-integrations
    - database_id - str
      Notion database ID
        database item
        - Name (title): 標題
        - Article (text): "metion page" 連接
        - MDFilename (text): 建立 markdown 檔名
        - Tags (multi_select): 標籤
        - IsPublish (checkbox): 是否已經發布
        - NeedUpdate (checkbox): 是否需要更新
        - CreateAt (Created time): 建立時間
        - UpdateAt (Last edited time): 更新時間
    """
    def __init__(self, token, database_id):
        self.notion = Client(auth=token)
        self.database_id = database_id
    
    def get_page_id(self, page_node: dict) -> list:
        rich_text_node = page_node["properties"].get("Article", {})
        mentions = []
        if rich_text_node["type"] != "rich_text":
            raise TypeError("this field is not a rich text")
        for i in rich_text_node["rich_text"]:
            if i["type"] == "mention":
                mentions.append(i["mention"]["page"]["id"])
        return mentions[0] if len(mentions) > 0 else None
    
    def title(self, page_node: dict) -> str:
        title_node = page_node["properties"].get("Name", {})
        title = ""
        if title_node["type"] != "title":
            raise TypeError("this field is not a title")
        for i in title_node["title"]:
            title += i["plain_text"]
        return title
    
    def is_publish(self, page_node: dict) -> bool:
        return page_node["properties"].get("IsPublish", {}).get("checkbox", False)

    def need_update(self, page_node: dict) -> bool:
        return page_node["properties"].get("NeedUpdate", {}).get("checkbox", False)
    
    def md_filename(self, page_node: dict) -> str:
        rich_text_node = page_node["properties"].get("MDFilename", {})
        file_name = ""
        if rich_text_node["type"] != "rich_text":
            raise TypeError("this field is not a rich text")
        for i in rich_text_node["rich_text"]:
            file_name += i["plain_text"]
        return file_name
    
    def tags(self, page_node: dict) -> list:
        tags_ = []
        tags_node = page_node["properties"].get("Tags", {}).get("multi_select", [])
        for i in tags_node:
            tags_.append(i["name"])
        return tags_
    
    def create_at(self, page_node: dict) -> str:
        return page_node["properties"].get("CreateAt", {}).get("created_time", "")

    def update_at(self, page_node: dict) -> str:
        return page_node["properties"].get("UpdateAt", {}).get("last_edited_time", "")
    
    def publish(self, page_node: dict) -> bool:
        page_id = page_node["id"]
        self.notion.pages.update(page_id, properties={
            "IsPublish": { "checkbox": True },
            "NeedUpdate": { "checkbox": False }
        })

    def items_changed(self):
        """獲取需要更新的項目"""
        data = self.notion.databases.query(database_id=self.database_id, filter={
            "and": [
                {
                    "property": "IsPublish",
                    "checkbox": {
                        "equals": False,
                    },
                },
                {
                    "property": "NeedUpdate",
                    "checkbox": {
                        "equals": True,
                    },
                },
            ]
        })
        return data.get("results") or []


class ImgStore:
    def __init__(self, img_data, img_ext, **kwargs):
        self.img_ext = img_ext
        self.img_data = img_data
        self.kwargs = kwargs
    
    def get_md5(self) -> str:
        md5hash = hashlib.md5(self.img_data)
        return md5hash.hexdigest()

    def store(self):
        raise NotImplementedError


class ImgStoreRemoteGithub(ImgStore):
    """圖片保存在 github 圖床"""
    def get_store_path(self, path) -> str:
        md5str = self.get_md5()
        return os.path.join(path, f"{md5str[:2]}/{md5str[2:4]}/{md5str}{self.img_ext}").replace("\\", "/")

    def store(self):
        github_token = self.kwargs["github_token"]
        repo = self.kwargs["repo"]
        store_path_prefix = self.kwargs["store_path_prefix"]
        branch = self.kwargs["branch"]
        gh = Github(github_token)
        gh_repo = gh.get_repo(repo)
        store_path = self.get_store_path(store_path_prefix)
        try:
            gh_repo.create_file(
                path=store_path,
                message=f'notion img auto upload at {time.strftime("%Y-%m-%d %H:%M:%S")}',
                content=self.img_data,
                branch=branch
            )
        except GithubException as e:
            if e.status != 422:
                raise
            blob_sha = gh_repo.get_contents(path=store_path).sha
            gh_repo.update_file(
                path=store_path,
                message=f'notion img auto upload at {time.strftime("%Y-%m-%d %H:%M:%S")}',
                content=self.img_data,
                sha=blob_sha
            )
        return f"https://raw.githubusercontent.com/{repo}/{branch}/{store_path}"


class ImgStoreLocal(ImgStore):
    """直接存在存放庫"""
    def get_img_filename(self):
        md5str = self.get_md5()
        return f"{md5str}{self.img_ext}"

    def get_img_path(self, path) -> str:
        return os.path.join(path, self.get_img_filename())
    
    def store(self):
        store_path_prefix = self.kwargs["store_path_prefix"]
        url_path_prefix = self.kwargs["url_path_prefix"]
        if not os.path.exists(store_path_prefix):
            os.makedirs(store_path_prefix)
        store_path = self.get_img_path(store_path_prefix)
        with open(store_path, "wb+") as f:
            f.write(self.img_data)
        return self.get_img_path(url_path_prefix)


class ImgHandler:
    """圖片處理
    
    Attributes:
        markdown_text: markdown
        img_store_type: local, github
    """
    pattern = re.compile(r'^(!\[[^\]]*\]\((.*?)\s*("(?:.*[^"])")?\s*\))', re.MULTILINE)
    
    exclude_pattern = re.compile(r"^https://xxx.xx/")

    def __init__(self, markdown_text, img_store_type, **kwargs):
        self.markdown_text = markdown_text
        self.kwargs = kwargs
        self.img_handler_cls = None
        if img_store_type == "local":
            self.img_handler_cls = ImgStoreLocal
        elif img_store_type == "github":
            self.img_handler_cls = ImgStoreRemoteGithub
    
    def get_ext_from_imglink(self, imglink):
        url_path = urlparse(imglink).path
        return os.path.splitext(url_path)[1]
    
    def get_img_data_from_url(self, url):
        return requests.get(url).content
    
    def is_exclude(self, imglink):
        if self.exclude_pattern.search(imglink):
            return True
        return False

    def extract_n_replace_imglink(self) -> str:
        for item in self.pattern.findall(self.markdown_text):
            match_text = item[0]
            imglink = item[1]
            if self.is_exclude(imglink):
                continue
            img_ext = self.get_ext_from_imglink(imglink)
            img_data = self.get_img_data_from_url(imglink)
            new_imglink = self.img_handler_cls(img_data, img_ext, **self.kwargs).store()
            img_text = match_text.replace(imglink, new_imglink)
            self.markdown_text = self.markdown_text.replace(match_text, img_text)
        return self.markdown_text


def get_markdown_with_yaml_header(page_node: dict, article_content: str, notion: Notion):
    yaml_header = {
        "title": "\"" + notion.title(page_node) + "\"",
        "date": notion.create_at(page_node),
        "draft": False,
        "author": "Jacky",
        "tags": notion.tags(page_node),
        "image": None,
        "description": "notion-ci",
        "toc": None,
        "socialShare": False,
    }
    header_text = yaml.dump(yaml_header, allow_unicode=True, sort_keys=False)  #不要自動排序
    header_text = header_text.replace(" null", "")
    header_text = header_text.replace("\"", "")
    
    statement_zh = "<center>此內容由 Notion 編輯並經由 Notion API 自動轉成 Hugo 頁面</center>"
    statement_en = "<center>The content write by Notion, and use Notion API convert to Hugo page.</center>"

    full_content = f"---\n{header_text}---\n\n\n\n"
    full_content += f"-----\n{statement_zh}\n{statement_en}\n\n-----\n\n"
    full_content += f"{article_content}"
    return full_content


def store_path_prefix_by_date(page_node, md_store_path_prefix):
    create_time = page_node["properties"].get("CreateAt", {}).get("created_time", "")
    create_date = create_time[:create_time.find('T')].replace("-", "")
    return os.path.join(md_store_path_prefix, create_date)


def save_markdown_file(path_prefix: str, content: str, filename: str):
    filename = filename.strip()
    filename = filename if filename.endswith(".md") else f"{filename}.md"
    logger.info(f"save markdwon file to {os.path.join(os.getcwd(), path_prefix, filename)}")
    if not os.path.exists(path_prefix):
        os.makedirs(path_prefix)
    md_filepath = os.path.join(os.getcwd(), path_prefix, filename)
    with open(md_filepath, "w+", encoding="utf-8") as f:
        f.write(content)


def main():
    logger.info("parse github action arguments...")
    platform, \
    notion_token, \
    notion_database_id, \
    img_store_type, \
    img_store_path_prefix, \
    img_store_url_path_prefix, \
    img_store_github_token, \
    img_store_github_repo, \
    img_store_github_branch, \
    md_store_path_prefix = get_github_action_arg()

    logger.info("start parse notion for blog...")
    notion = Notion(notion_token, notion_database_id)
    page_nodes = notion.items_changed()
    logger.info(f"it will update {len(page_nodes)} article...")
    for page_node in page_nodes:
        # 檢查項目title是否為metion連結
        if not notion.title(page_node).strip():
            logger.warning("please check the article is a metion link...")
            continue

        # 取得 page id
        logger.info(f"get page content from notion...")
        page_id = notion.get_page_id(page_node)
        logger.info(f"parse <<{notion.title(page_node)}>>...")

        # notion page -> markdown
        markdown_text = NotionToMarkdown(notion_token, page_id).parse()

        # 添加日期目錄
        img_store_path = store_path_prefix_by_date(page_node, img_store_path_prefix)
        img_store_url_path = store_path_prefix_by_date(page_node, img_store_url_path_prefix)
        md_store_path = store_path_prefix_by_date(page_node, md_store_path_prefix)

        # markdown 圖片處理
        logger.info(f"replace img link in article")
        img_store_kwargs = {
            "github_token": img_store_github_token,
            "repo": img_store_github_repo,
            "store_path_prefix": img_store_path,
            "branch": img_store_github_branch,
            "url_path_prefix": img_store_url_path,
        }
        img_handler = ImgHandler(markdown_text, img_store_type, **img_store_kwargs)
        markdown_text = img_handler.extract_n_replace_imglink()

        # 產生yaml標頭的markdown供hugo生成
        logger.info(f"generate and save article <<{notion.title(page_node)}>>...")
        markdown_with_header = get_markdown_with_yaml_header(page_node, markdown_text, notion)

        # 保存markdown到指定目錄
        save_markdown_file(md_store_path, markdown_with_header, notion.md_filename(page_node))

        # 更新notion中的對應項
        if platform == "github":
            logger.info("update page property for article <<{notion.title(page_node)}>>")
            notion.publish(page_node)
    
    logger.info("all done!!!\n")


if __name__ == "__main__":
    main()
