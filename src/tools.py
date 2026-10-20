'''
工具
'''

import json
import os
import sys
from datetime import datetime
from json import JSONDecodeError
from zoneinfo import ZoneInfo
from schemas import ToolResult
from pathlib import Path
from utils import num_to_cn, digits_to_cn, text_clean
import re
import requests
from dotenv import load_dotenv
from contextvars import ContextVar

X = ContextVar('session_id', default='default')
U = ContextVar('user_id', default='')

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR.joinpath('output')
OUTPUT_DIR.mkdir(exist_ok=True)


IDENTIFIER = {
    'memo': {'file_name': 'memos.json', 'name': '备忘录'},
    'todo': {'file_name': 'todos.json', 'name': '待办事项'}
}

# session_id 清洗
def clean_session_id(session_id: str | None) -> str:
    if  not isinstance(session_id,str) or not session_id:
        return 'default'
    if re.search(r'[^a-zA-Z0-9_-]', session_id):
        return 'default'
    if len(session_id) > 64:
        return 'default'
    return session_id.lower()

def get_file_path() -> Path:
    cleaned_session_id = clean_session_id(X.get())
    cleaned_user_id = clean_session_id(U.get())
    if cleaned_user_id == 'default':
        file_path = OUTPUT_DIR.joinpath(cleaned_session_id)
    else:
        file_path = OUTPUT_DIR.joinpath(cleaned_user_id)
    return file_path

# 保存文件
def save_file(file_name: str, content: list) -> None:
    JSON_PATH = get_file_path()
    JSON_PATH.mkdir(exist_ok=True)
    file = JSON_PATH.joinpath(file_name)
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False)


# 加载文件
def load_file(file_name: str) -> list:
    JSON_PATH = get_file_path()
    JSON_PATH.mkdir(exist_ok=True)
    file = JSON_PATH.joinpath(file_name)
    try:
        with open(file, encoding='utf-8') as f:
            content = json.load(f)
            return content
    except (FileNotFoundError, JSONDecodeError):
        return []

def get_count(kind: str) -> int:
    # kind 只认 IDENTIFIER 里的键；传错了返回 0 而不是抛 KeyError
    # （/state 是前端切身份就请求的接口，这里炸掉会让整个侧栏 500）
    if kind not in IDENTIFIER:
        return 0
    file_path = IDENTIFIER[kind]['file_name']
    contents = load_file(file_path)
    return len(contents)

# 获取当前时间
def _get_current_time() -> str:
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    return now.strftime("%Y-%m-%d %H:%M:%S")


# 添加信息
def _add(kind: str, text: str) -> ToolResult:
    file_path = IDENTIFIER[kind]['file_name']
    contents = load_file(file_path)
    content_id = max(item['id'] for item in contents) + 1 if contents else 1
    contents.append({
        'id': content_id,
        'text': text,
        'created_at': _get_current_time()
    })
    if kind == 'todo':
        contents[-1]['done'] = False
    save_file(file_path, contents)
    return ToolResult(
        ok=True,
        reply=f'已加入{IDENTIFIER[kind]["name"]}！\n{text}',
        id=content_id
    )


# 查询信息
def _list(kind: str) -> ToolResult:
    file_path = IDENTIFIER[kind]['file_name']
    contents = load_file(file_path)
    if kind == 'todo':
        contents_new = '\n'.join(['第' + str(index + 1) + '条' + '，' + item['text'] + '[已完成]' if item[
            'done'] else '第' + str(index + 1) + '条' + '，' + item['text'] for index, item in enumerate(contents)])
    else:
        contents_new = '\n'.join(
            ['第' + str(index + 1) + '条' + '，' + item['text'] for index, item in enumerate(contents)])
    return ToolResult(
        ok=True,
        reply=f'共{len(contents)}条{IDENTIFIER[kind]["name"]}:\n{contents_new}',
        id=None
    )


# 删除信息
def _delete(kind: str, lineno: int | None = None, keyword: str | None = None) -> ToolResult:
    file_path = IDENTIFIER[kind]['file_name']
    contents = load_file(file_path)
    if lineno is None and keyword is None:
        return ToolResult(
            ok=False,
            reply='请提供要删除内容的条号或者关键字',
            id=None
        )
    if lineno is not None:
        if lineno > len(contents) or lineno <= 0:
            return ToolResult(
                ok=False,
                reply=f'删除失败，{IDENTIFIER[kind]["name"]}中没有该记录',
                id=None
            )
        contents = [item for index, item in enumerate(contents) if index + 1 != lineno]
        save_file(file_path, contents)
        return ToolResult(
            ok=True,
            reply=f'已删除该条{IDENTIFIER[kind]["name"]}',
            id=None
        )
    if keyword is not None:
        hit_lineno = []
        for index, item in enumerate(contents):
            if keyword in item['text']:
                hit_lineno.append(index + 1)
        if len(hit_lineno) == 0:
            return ToolResult(
                ok=False,
                reply=f'未找到关于“{keyword}”的记录',
                id=None
            )
        elif len(hit_lineno) == 1:
            contents = [item for index, item in enumerate(contents) if keyword not in item['text']]
            save_file(file_path, contents)
            return ToolResult(
                ok=True,
                reply=f'已删除该条{IDENTIFIER[kind]["name"]}',
                id=None
            )
        else:
            # 用户看到的是「候选」而不是整份列表 → 这里按候选内序号编号（第1条、第2条…）
            hits = [item for item in contents if keyword in item['text']]
            reply = f'共{len(hits)}条记录，请确认是哪一条：\n' + '\n'.join(
                '第' + str(index + 1) + '条' + '，' + item['text'] for index, item in enumerate(hits))
            return ToolResult(
                ok=False,
                reply=reply,
                id=None,
                candidate=hit_lineno
            )


# 完成待办
def complete_todo(lineno: int) -> ToolResult:
    file_path = IDENTIFIER['todo']['file_name']
    todos = load_file(file_path)
    if lineno > len(todos) or lineno <= 0:
        return ToolResult(
            ok=False,
            reply='抱歉待办中没有该事项',
            id=None
        )
    for index, item in enumerate(todos):
        if index + 1 == lineno:
            if item['done']:
                return ToolResult(
                    ok=True,
                    reply="该事项已为完成状态",
                    id=None
                )
            item['done'] = True
    save_file(file_path, todos)
    return ToolResult(
        ok=True,
        reply="待办标记已完成",
        id=None
    )


# 查询天气
def _get_weather(city: str, type: str) -> dict:
    response = requests.get(
        url=os.getenv('GDMAP_API_URL'),
        params={'key': os.getenv('GDMAP_API_KEY'), 'city': city, 'extensions': type},
        timeout=3
    )
    return response.json()

def _web_search(query: str) -> dict:
    url = os.getenv('BOCHA_API_URL')
    payload = json.dumps({
        "query": query,
        "summary": True,
        "count": 3
    })
    headers = {
        'Authorization': 'Bearer ' + os.getenv('BOCHA_API_KEY'),
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", url, headers=headers, data=payload, timeout=3).json()
    return response


def add_memo(text: str) -> ToolResult:
    return _add(kind='memo', text=text)


def add_todo(text: str) -> ToolResult:
    return _add(kind='todo', text=text)


def list_memos() -> ToolResult:
    return _list(kind='memo')


def list_todos() -> ToolResult:
    return _list(kind='todo')


def delete_memo(lineno: int | None = None, keyword: str | None = None) -> ToolResult:
    return _delete(kind='memo', lineno=lineno, keyword=keyword)


def delete_todo(lineno: int | None = None, keyword: str | None = None) -> ToolResult:
    return _delete(kind='todo', lineno=lineno, keyword=keyword)


def get_current_time() -> ToolResult:
    time = _get_current_time()
    time_datetime = datetime.strptime(time, '%Y-%m-%d %H:%M:%S')  # 2026-10-13 16:28:01
    time_str = re.sub(r'[-:]', ' ', time)
    time_list = [int(item) for item in time_str.split(' ')]  # ['2026', '10', '13', '16', '46', '34']
    result = digits_to_cn(str(time_list[0])) + '年'
    time2list = ['月', '日', '时', '分', '秒']
    for index, item in enumerate(time_list[1:]):
        if item < 9:
            result = result + digits_to_cn(str(item)) + time2list[index]
        else:
            result = result + num_to_cn(item) + time2list[index]
    pos = result.rfind('日')
    final = result[:pos + 1] + '星期' + num_to_cn(time_datetime.isoweekday()) + '，' + result[pos + 1:]
    return ToolResult(
        ok=True,
        reply=final,
        id=None
    )


def get_weather(city: str = '') -> ToolResult:
    try:
        if city is None or city.strip() == '':
            return ToolResult(
                ok=False,
                reply='没识别到城市，请问你要查哪个城市的天气？',
                id=None
            )
        base = _get_weather(city, 'base')
        all = _get_weather(city, 'all')
        if int(base['count']) < 1 or int(all['count']) < 1:
            return ToolResult(
                ok=False,
                reply=f'没查到{city}的天气，换个城市名试试',
                id=None
            )
        base_weather = base['lives'][0]
        all_weather = all['forecasts'][0]['casts'][:3]
        day_map = ['今天', '明天', '后天']
        weather = (base_weather['city'] + '：' + base_weather['weather'] + '，' + num_to_cn(int(base_weather['temperature'])) + '度，' + \
                   base_weather['winddirection'] + '风' + num_to_cn(int(base_weather['windpower'][-1])) + '级以内，' + \
                   '湿度百分之' + num_to_cn(int(base_weather['humidity'])) + '\n')
        for index, item in enumerate(all_weather):
            date = item['date'].split('-')[1:]
            weather = weather + day_map[
                index] + f' {num_to_cn(int(date[0]))}月{num_to_cn(int(date[1]))}日' + f' 星期{num_to_cn(int(item["week"]))}：白天' + \
                      item['dayweather'] + f'，夜间{item["nightweather"]}，' + f'{num_to_cn(int(item["daytemp"]))}度到{num_to_cn(int(item["nighttemp"]))}度\n'
        return ToolResult(
            ok=True,
            reply=weather,
            id=None
        )
    except Exception as e:
        print(f'[警告]：{str(e)}', file=sys.stderr)
        return ToolResult(
            ok=False,
            reply='天气服务暂时不可用，稍后再试',
            id=None
        )

def web_search(query: str) -> ToolResult:
    try:
        if query is None or query.strip() == '':
            return ToolResult(
                ok=False,
                reply='没识别到查询信息',
                id=None
            )
        result = ''
        response = _web_search(query)
        if response['code'] != 200 and response['code'] != '200':
            return ToolResult(
                ok=False,
                reply='搜索服务暂时不可用，稍后再试',
                id=None
            )
        if not response['data']['webPages']['value']:
            return ToolResult(
                ok=False,
                reply="没搜到相关内容，换个说法试试",
                id=None
            )
        res = [(text_clean(item.get('name') or ''), text_clean(item.get('snippet') if item.get('snippet') and len(item.get('snippet')) > 5 else item.get('summary') or '')) for item in response['data']['webPages']['value']]
        if sum([1 if len(item[1]) < 20 else 0 for item in res]) == len(res):
            return ToolResult(
                ok=False,
                reply="没搜到相关内容，换个说法试试",
                id=None
            )
        for index, item in enumerate(res):
            result = result + str(index + 1) + '.' + item[0] + '：' + item[1][:200] + '\n'
        return ToolResult(
            ok=True,
            reply=result,
            id=None
        )

    except Exception as e:
        print(f'[警告]：{str(e)}{type(e).__name__}', file=sys.stderr)
        return ToolResult(
            ok=False,
            reply='搜索服务暂时不可用，稍后再试',
            id=None
        )
