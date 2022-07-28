# -*- coding: utf-8 -*-
""" utils
放置一些小工具
- 處理 github action 參數
- 處理訊息顯示

@init 2022/07/23
- 處理不同文件的名稱
"""
import logging
import os
from configparser import ConfigParser


def github_action_env(key):
    """取得 github action 輸入參數"""
    return f"INPUT_{key}".upper()


def get_platform():
    return os.getenv(github_action_env("PLATFORM"), "no-github")


def get_github_action_arg():
    platform = get_platform()
    if platform == "github":
        notion_token =\
            os.environ[github_action_env("NOTION_TOKEN")]
        notion_database_id =\
            os.environ[github_action_env("NOTION_DATABASE_ID")]
        
        im_store_type =\
            os.getenv(github_action_env("IMG_STORE_TYPE"), "local")
        im_store_path_prefix =\
            os.getenv(github_action_env("IMG_STORE_PATH_PREFIX"), "content/blogs")
        im_store_url_path_prefix =\
            os.getenv(github_action_env("IMG_STORE_URL_PATH_PREFIX"), "/content/blogs")
        im_store_github_token =\
            os.getenv(github_action_env("IMG_STORE_GITHUB_TOKEN"))
        im_store_github_repo =\
            os.getenv(github_action_env("IMG_STORE_GITHUB_REPO"))
        im_store_github_branch =\
            os.getenv(github_action_env("IMG_STORE_GITHUB_BRANCH"))
        
        md_store_path_prefix =\
            os.getenv(github_action_env("MD_STORE_PATH_PREFIX"), "content/blogs")
    
    else:
        cfg = ConfigParser()
        cfg.read("config.ini")

        notion_token =\
            cfg["notion"]["token"]
        notion_database_id =\
            cfg["notion"]["database_id"]
        
        im_store_type =\
            cfg["img_store"]["type"] # local, github
        im_store_path_prefix =\
            cfg["img_store"]["path_prefix"]
        im_store_url_path_prefix =\
            cfg["img_store"]["url_path_prefix"]
        im_store_github_token =\
            cfg["img_store"]["github_token"]
        im_store_github_repo =\
            cfg["img_store"]["github_repo"]
        im_store_github_branch =\
            cfg["img_store"]["github_branch"]
        
        md_store_path_prefix =\
            cfg["md_store"]["path_prefix"] # save dir of markdown

    argv = (
        platform,
        notion_token,
        notion_database_id,
        im_store_type,
        im_store_path_prefix,
        im_store_url_path_prefix,
        im_store_github_token,
        im_store_github_repo,
        im_store_github_branch,
        md_store_path_prefix
    )
    
    return argv


def get_logger(name, level:str="INFO"):
    platform = get_platform()
    debug_mode = True if platform == "no-github" else False
    level = "DEBUG" if debug_mode else level.upper()

    log_level_dict = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARN": logging.WARN,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET
    }    

    ## 格式化訊息
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    ## 設定logger名稱
    logger = logging.getLogger(f"{name}")

    ## 轉換對應log等級
    logger.setLevel(log_level_dict.get(level, logging.NOTSET))

    ## 設定顯示訊息
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    ## 在本機使用可以保存console資訊
    if debug_mode:
        fh = logging.FileHandler("debug.log")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    logger.debug(f"get logger, level: {level}, platform: {platform}, debug_mode: {debug_mode}")

    return logger
