import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import requests
from pydantic import BaseModel

SCRIPT_PATH = Path(__file__).parents[0]
POOL_LIST_PATH = SCRIPT_PATH / "data" / "pool.json"
COMPRESSED_POOL_LIST_PATH = SCRIPT_PATH / "data" / "compressed_pool.json"


class Character(BaseModel):
    char_id: str
    char_name: str
    star: int


class Weapon(BaseModel):
    weapon_id: str
    weapon_name: str
    star: int


"""
获取角色和武器数据
"""


def fetch_character_data():
    res = requests.get("https://api.hakush.in/ww/data/character.json")
    res.raise_for_status()
    value = res.json()
    return value


def fetch_weapon_data():
    res = requests.get("https://api.hakush.in/ww/data/weapon.json")
    res.raise_for_status()
    value = res.json()
    return value


raw_character_data = fetch_character_data()
char_list: list[Character] = [
    Character.model_validate(
        {
            "char_id": char_id,
            "char_name": char_data["zh-Hans"],
            "star": char_data["element"],
        }
    )
    for char_id, char_data in raw_character_data.items()
]
id2char_name = {c.char_id: c.char_name for c in char_list}
name2char_id = {c.char_name: c.char_id for c in char_list}

raw_weapon_data = fetch_weapon_data()
weapon_list: list[Weapon] = [
    Weapon.model_validate(
        {
            "weapon_id": weapon_id,
            "weapon_name": weapon_data["zh-Hans"],
            "star": weapon_data["rank"],
        }
    )
    for weapon_id, weapon_data in raw_weapon_data.items()
]
id2weapon_name = {w.weapon_id: w.weapon_name for w in weapon_list}
name2weapon_id = {w.weapon_name: w.weapon_id for w in weapon_list}

id2name = {**id2char_name, **id2weapon_name}
name2id = {**name2char_id, **name2weapon_id}


def extract_and_convert_time(text):
    # 匹配中文格式的日期时间
    pattern = r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2}):(\d{1,2})"

    # 查找所有匹配项
    matches = re.findall(pattern, text)

    result = {}

    # 如果找到至少两个匹配项（开始和结束时间）
    if len(matches) >= 2:
        # 提取第一个匹配项作为开始时间
        start = matches[0]
        # 提取第二个匹配项作为结束时间
        end = matches[1]

        # 格式化为ISO格式
        result["start_at"] = (
            f"{start[0]}-{start[1].zfill(2)}-{start[2].zfill(2)} {start[3].zfill(2)}:{start[4].zfill(2)}:00"
        )
        result["end_at"] = (
            f"{end[0]}-{end[1].zfill(2)}-{end[2].zfill(2)} {end[3].zfill(2)}:{end[4].zfill(2)}:59"
        )
    elif len(matches) == 1:
        result["start_at"] = "版本更新时间"
        result["end_at"] = (
            f"{matches[0][0]}-{matches[0][1].zfill(2)}-{matches[0][2].zfill(2)} {matches[0][3].zfill(2)}:{matches[0][4].zfill(2)}:59"
        )
    else:
        raise ValueError(f"没有找到时间: {text}")

    return result


"""
开始获取卡池数据
"""
name_pattern = r"「(.*?)」"
title_pattern_1 = r"&lt;(.*?)&gt;"
title_pattern_2 = r"\[(.*?)\]"
title_pattern_3 = r"<(.*?)>"

GAME_ID = 3
MAIN_URL = "https://api.kurobbs.com"
ANN_CONTENT_URL = f"{MAIN_URL}/forum/getPostDetail"
SEARCH_URL = f"{MAIN_URL}/forum/search/v2/join"
POST_PAGE_URL = "https://www.kurobbs.com/mc/post/"

headers = {
    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0",
    "Accept": "application/json, text/plain, */*",
    "Source": "h5",
    "Token": "",
    "devcode": "IvYsrF21ls8CMFfxo1CTGQsv8neo0t6x",
}


def get_post_detail(post_id: str):
    _headers = copy.deepcopy(headers)
    _headers.update({"devcode": "", "token": "", "version": ""})
    data = {
        "isOnlyPublisher": 1,
        "postId": post_id,
        "showOrderType": 2,
    }
    res = requests.post(
        ANN_CONTENT_URL,
        headers=_headers,
        data=data,
        timeout=10,
    )
    return res.json()


def search_pool_list(
    pageIndex: int,
    pageSize: int,
    keyword: Literal["角色活动唤取", "武器活动唤取"],
    gameId: int = GAME_ID,
    search_type: int = 3,
):
    data: dict[str, Any] = {
        "gameId": gameId,
        "keyword": keyword,
        "pageIndex": pageIndex,
        "pageSize": pageSize,
        "searchType": search_type,
    }
    _headers = copy.deepcopy(headers)
    res = requests.post(
        SEARCH_URL,
        headers=_headers,
        data=data,
        timeout=10,
    )
    return res.json()


def get_pool_list(
    keyword: Literal["角色活动唤取", "武器活动唤取"],
    end_page: int = 3,
):
    pool_list = []
    for page in range(1, end_page + 1):
        res = search_pool_list(page, 20, keyword)
        print(f"当前第{page}页")
        postList = res["data"]["post"]["postList"]
        for post in postList:
            post_id = post["postId"]
            post_title = post["postTitle"]
            user_id = post["userId"]
            if user_id != "10012001":
                continue

            if keyword not in post_title:
                continue
            if "周年" in post_title:
                continue
            if not post["imgContent"]:
                print(f"没有图片: {post_id} {post_title}")
                continue
            post_title = post_title.replace("<em>", "").replace("</em>", "")

            find_all = re.findall(name_pattern, post_title)
            if find_all:
                name = find_all[-1]
            else:
                name = ""
            find_all = re.findall(title_pattern_1, post_title)
            if find_all:
                title = find_all[0]
            else:
                find_all = re.findall(title_pattern_2, post_title)
                if find_all:
                    title = find_all[0]
                else:
                    find_all = re.findall(title_pattern_3, post_title)
                    if find_all:
                        title = find_all[0]
                    else:
                        find_all = re.findall(name_pattern, post_title)
                        if find_all:
                            title = find_all[0]
                        else:
                            title = ""

            url = post["imgContent"][0]["url"]

            post_detail = get_post_detail(post_id)
            post_content = post_detail["data"]["postDetail"]["postContent"]

            # 提取5星角色和4星角色
            five_star_names = []
            four_star_names = []
            five_star_ids = []
            four_star_ids = []
            pool_type = ""
            start_time = ""
            end_time = ""
            for content in post_content:
                if content["contentType"] != 1:
                    continue
                if "5星角色" in content["content"] and "4星角色" in content["content"]:
                    # 提取5星角色
                    five_star_pattern = r"5星角色「(.*?)」"
                    five_star_matches = re.findall(
                        five_star_pattern, content["content"]
                    )
                    five_star_names.extend(five_star_matches)
                    five_star_ids.extend([name2id[name] for name in five_star_matches])
                    # 提取4星角色 - 匹配"4星角色"后面的所有引号内容
                    four_star_text = re.search(
                        r"4星角色(.*?)(?=唤取|$)", content["content"]
                    )
                    if four_star_text:
                        four_star_text = four_star_text.group(1)
                        four_star_names = re.findall(r"「(.*?)」", four_star_text)
                        four_star_ids.extend(
                            [name2id[name] for name in four_star_names]
                        )
                    pool_type = "角色活动唤取"

                if "5星武器" in content["content"] and "4星武器" in content["content"]:
                    # 提取5星角色
                    five_star_pattern = r"5星武器「(.*?)」"
                    five_star_matches = re.findall(
                        five_star_pattern, content["content"]
                    )
                    five_star_names.extend(five_star_matches)
                    five_star_ids.extend([name2id[name] for name in five_star_matches])
                    # 提取4星角色 - 匹配"4星角色"后面的所有引号内容
                    four_star_text = re.search(
                        r"4星武器(.*?)(?=唤取|$)", content["content"]
                    )
                    if four_star_text:
                        four_star_text = four_star_text.group(1)
                        four_star_names = re.findall(r"「(.*?)」", four_star_text)
                        four_star_ids.extend(
                            [name2id[name] for name in four_star_names]
                        )
                    pool_type = "武器活动唤取"
                if "服务器时间" in content["content"] or " ~ " in content["content"]:
                    # 2025年3月6日10:00 ~ 2025年3月26日11:59（服务器时间）
                    # 1.4版本更新后 ~ 2024年12月12日09:59（服务器时间）
                    # 2024年6月6日10:00 ~ 2024年6月26日11:59
                    result = extract_and_convert_time(content["content"])
                    start_time = result["start_at"]
                    end_time = result["end_at"]

            pool = {
                "bbs": POST_PAGE_URL + post_id,
                "name": name,
                "title": title,
                "pic": url,
                "five_star_ids": five_star_ids,
                "five_star_names": five_star_names,
                "four_star_ids": four_star_ids,
                "four_star_names": four_star_names,
                "pool_type": pool_type,
                "start_time": start_time,
                "end_time": end_time,
            }

            pool_list.append(pool)
    return pool_list


character_pool_list = get_pool_list("角色活动唤取")
weapon_pool_list = get_pool_list("武器活动唤取")


fixed = [
    {
        "bbs": "",
        "name": "忌炎",
        "title": "夜将寒色去",
        "pic": "",
        "five_star_ids": ["1404"],
        "five_star_names": ["忌炎"],
        "four_star_ids": ["1602", "1202", "1204"],
        "four_star_names": ["丹瑾", "炽霞", "莫特斐"],
        "pool_type": "角色活动唤取",
        "start_time": "2024-05-23 10:00:00",
        "end_time": "2024-06-13 09:59:59",
    },
    {
        "bbs": "",
        "name": "苍鳞千嶂",
        "title": "浮声沉兵",
        "pic": "",
        "five_star_ids": ["21010016"],
        "five_star_names": ["苍鳞千嶂"],
        "four_star_ids": ["21010044", "21050024", "21040064"],
        "four_star_names": ["永夜长明", "奇幻变奏", "骇行"],
        "pool_type": "武器活动唤取",
        "start_time": "2024-05-23 10:00:00",
        "end_time": "2024-06-13 09:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1366076768541614080",
        "name": "忌炎",
        "title": "夜将寒色去",
        "pic": "",
        "five_star_ids": ["1404"],
        "five_star_names": ["忌炎"],
        "four_star_ids": ["1504", "1601", "1303"],
        "four_star_names": ["灯灯", "桃祈", "渊武"],
        "pool_type": "角色活动唤取",
        "start_time": "版本更新时间",
        "end_time": "2025-05-22 09:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1366076768541614080",
        "name": "苍鳞千嶂",
        "title": "浮声沉兵",
        "pic": "",
        "five_star_ids": ["21010016"],
        "five_star_names": ["苍鳞千嶂"],
        "four_star_ids": ["21010044", "21020024", "21040064"],
        "four_star_names": ["永夜长明", "行进序曲", "骇行"],
        "pool_type": "武器活动唤取",
        "start_time": "版本更新时间",
        "end_time": "2025-05-22 09:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1366076768541614080",
        "name": "吟霖",
        "title": "惊霆雨时节",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/a8332d4349a94bb6a908b972fb7561ff20240605.jpg",
        "five_star_ids": ["1302"],
        "five_star_names": ["吟霖"],
        "four_star_ids": ["1504", "1601", "1303"],
        "four_star_names": ["灯灯", "桃祈", "渊武"],
        "pool_type": "角色活动唤取",
        "start_time": "版本更新时间",
        "end_time": "2025-05-22 09:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1366076768541614080",
        "name": "掣傀之手",
        "title": "浮声沉兵",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/45eb3783e4db4a02960287f71052f84a20240605.jpg",
        "five_star_ids": ["21050016"],
        "five_star_names": ["掣傀之手"],
        "four_star_ids": ["21010044", "21020024", "21040064"],
        "four_star_names": ["永夜长明", "行进序曲", "骇行"],
        "pool_type": "武器活动唤取",
        "start_time": "版本更新时间",
        "end_time": "2025-05-22 09:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1366076768541614080",
        "name": "折枝",
        "title": "赋彩作长吟",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/e99d94b4cae44f96bb9bb5fc07ca614420240814.jpg",
        "five_star_ids": ["1105"],
        "five_star_names": ["折枝"],
        "four_star_ids": ["1504", "1601", "1303"],
        "four_star_names": ["灯灯", "桃祈", "渊武"],
        "pool_type": "角色活动唤取",
        "start_time": "版本更新时间",
        "end_time": "2025-05-22 09:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1366076768541614080",
        "name": "琼枝冰绡",
        "title": "浮声沉兵",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/b5db920911c64bbd854da0e7eeb0971820240814.jpg",
        "five_star_ids": ["21050026"],
        "five_star_names": ["琼枝冰绡"],
        "four_star_ids": ["21010044", "21020024", "21040064"],
        "four_star_names": ["永夜长明", "行进序曲", "骇行"],
        "pool_type": "武器活动唤取",
        "start_time": "版本更新时间",
        "end_time": "2025-05-22 09:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1366076768541614080",
        "name": "相里要",
        "title": "千机逐星野",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/2db86470f9314a569650e9fff0433e1f20240905.jpg",
        "five_star_ids": ["1305"],
        "five_star_names": ["相里要"],
        "four_star_ids": ["1504", "1601", "1303"],
        "four_star_names": ["灯灯", "桃祈", "渊武"],
        "pool_type": "角色活动唤取",
        "start_time": "版本更新时间",
        "end_time": "2025-05-22 09:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1366076768541614080",
        "name": "诸方玄枢",
        "title": "浮声沉兵",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/ec625fec55314e52a5948e9f6641f76220240905.jpg",
        "five_star_ids": ["21040016"],
        "five_star_names": ["诸方玄枢"],
        "four_star_ids": ["21010044", "21020024", "21040064"],
        "four_star_names": ["永夜长明", "行进序曲", "骇行"],
        "pool_type": "武器活动唤取",
        "start_time": "版本更新时间",
        "end_time": "2025-05-22 09:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1366076768541614080",
        "name": "菲比",
        "title": "于静谧呢喃",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/fa562ac0802746dd8028a0959762740b20250211.jpg",
        "five_star_ids": ["1506"],
        "five_star_names": ["菲比"],
        "four_star_ids": ["1504", "1601", "1303"],
        "four_star_names": ["灯灯", "桃祈", "渊武"],
        "pool_type": "角色活动唤取",
        "start_time": "版本更新时间",
        "end_time": "2025-05-22 09:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1366076768541614080",
        "name": "和光回唱",
        "title": "浮声沉兵",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/c41e43ff812340ca9a8134528c00d3c820250211.jpg",
        "five_star_ids": ["21050046"],
        "five_star_names": ["和光回唱"],
        "four_star_ids": ["21010044", "21020024", "21040064"],
        "four_star_names": ["永夜长明", "行进序曲", "骇行"],
        "pool_type": "武器活动唤取",
        "start_time": "版本更新时间",
        "end_time": "2025-05-22 09:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1374001519726297088",
        "title": "寒尽觉春生",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/02bca2fb7f5640ac96eb9490ab71683020240626.jpg",
        "five_star_ids": ["1304"],
        "five_star_names": ["今汐"],
        "four_star_ids": ["1602", "1402", "1204"],
        "four_star_names": ["丹瑾", "秧秧", "莫特斐"],
        "pool_type": "角色活动唤取",
        "start_time": "2025-05-22 10:00:00",
        "end_time": "2025-06-11 11:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1374001519726297088",
        "name": "时和岁稔",
        "title": "浮声沉兵",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/fb2df4dc9f234cf0a9a1bc867d218b4920240626.jpg",
        "five_star_ids": ["21010026"],
        "five_star_names": ["时和岁稔"],
        "four_star_ids": ["21030044", "21050024", "21030084"],
        "four_star_names": ["无眠烈火", "奇幻变奏", "悖论喷流"],
        "pool_type": "武器活动唤取",
        "start_time": "2025-05-22 10:00:00",
        "end_time": "2025-06-11 11:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1374001519726297088",
        "name": "长离",
        "title": "炽羽策阵星",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/c4bd99020c3a4c52982ad301e514690220240719.jpg",
        "five_star_ids": ["1205"],
        "five_star_names": ["长离"],
        "four_star_ids": ["1602", "1402", "1204"],
        "four_star_names": ["丹瑾", "秧秧", "莫特斐"],
        "pool_type": "角色活动唤取",
        "start_time": "2025-05-22 10:00:00",
        "end_time": "2025-06-11 11:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1374001519726297088",
        "name": "赫奕流明",
        "title": "浮声沉兵",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/a082d6c12f8543219c6b85a69366ce5320240719.jpg",
        "five_star_ids": ["21020016"],
        "five_star_names": ["赫奕流明"],
        "four_star_ids": ["21030044", "21050024", "21030084"],
        "four_star_names": ["无眠烈火", "奇幻变奏", "悖论喷流"],
        "pool_type": "武器活动唤取",
        "start_time": "2025-05-22 10:00:00",
        "end_time": "2025-06-11 11:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1374001519726297088",
        "name": "珂莱塔",
        "title": "另一种喧嚣",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/69f3c4ea4fbd4c939524a25a13e0975f20241231.jpg",
        "five_star_ids": ["1107"],
        "five_star_names": ["珂莱塔"],
        "four_star_ids": ["1602", "1402", "1204"],
        "four_star_names": ["丹瑾", "秧秧", "莫特斐"],
        "pool_type": "角色活动唤取",
        "start_time": "2025-05-22 10:00:00",
        "end_time": "2025-06-11 11:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1374001519726297088",
        "name": "死与舞",
        "title": "浮声沉兵",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/8ec64b37bbb74da38d21054de2ae30b420241231.jpg",
        "five_star_ids": ["21030016"],
        "five_star_names": ["死与舞"],
        "four_star_ids": ["21030044", "21050024", "21030084"],
        "four_star_names": ["无眠烈火", "奇幻变奏", "悖论喷流"],
        "pool_type": "武器活动唤取",
        "start_time": "2025-05-22 10:00:00",
        "end_time": "2025-06-11 11:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1374001519726297088",
        "name": "洛可可",
        "title": "箱中舞台",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/0dc5a2a1b5d748a7800ce306164f98ee20250121.jpg",
        "five_star_ids": ["1606"],
        "five_star_names": ["洛可可"],
        "four_star_ids": ["1602", "1402", "1204"],
        "four_star_names": ["丹瑾", "秧秧", "莫特斐"],
        "pool_type": "角色活动唤取",
        "start_time": "2025-05-22 10:00:00",
        "end_time": "2025-06-11 11:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1374001519726297088",
        "name": "悲喜剧",
        "title": "浮声沉兵",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/2ebb015eace4456c814248fc0093d88720250121.jpg",
        "five_star_ids": ["21040026"],
        "five_star_names": ["悲喜剧"],
        "four_star_ids": ["21030044", "21050024", "21030084"],
        "four_star_names": ["无眠烈火", "奇幻变奏", "悖论喷流"],
        "pool_type": "武器活动唤取",
        "start_time": "2025-05-22 10:00:00",
        "end_time": "2025-06-11 11:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1374001519726297088",
        "name": "布兰特",
        "title": "燃焰于海",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/726fc80c40194adca0d314a27b4620ed20250304.jpeg",
        "five_star_ids": ["1206"],
        "five_star_names": ["布兰特"],
        "four_star_ids": ["1602", "1402", "1204"],
        "four_star_names": ["丹瑾", "秧秧", "莫特斐"],
        "pool_type": "角色活动唤取",
        "start_time": "2025-05-22 10:00:00",
        "end_time": "2025-06-11 11:59:59",
    },
    {
        "bbs": "https://www.kurobbs.com/mc/post/1374001519726297088",
        "name": "不灭航路",
        "title": "浮声沉兵",
        "pic": "https://prod-alicdn-community.kurobbs.com/forum/6d868f660f224f168d5c020c77d5a11020250304.jpeg",
        "five_star_ids": ["21020036"],
        "five_star_names": ["不灭航路"],
        "four_star_ids": ["21030044", "21050024", "21030084"],
        "four_star_names": ["无眠烈火", "奇幻变奏", "悖论喷流"],
        "pool_type": "武器活动唤取",
        "start_time": "2025-05-22 10:00:00",
        "end_time": "2025-06-11 11:59:59",
    },
]

pool_list = fixed + character_pool_list + weapon_pool_list
try:
    pool_list = sorted(
        pool_list,
        key=lambda x: datetime.strptime(x["end_time"], "%Y-%m-%d %H:%M:%S"),
    )
except Exception as e:
    print(e)
    print(pool_list)


with open(POOL_LIST_PATH, "w") as f:
    json.dump(pool_list, f, indent=4, ensure_ascii=False)

with open(COMPRESSED_POOL_LIST_PATH, "w") as f:
    json.dump(pool_list, f, ensure_ascii=False, separators=(",", ":"))
