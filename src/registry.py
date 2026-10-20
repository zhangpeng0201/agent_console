'''
定义工具表
'''

from tools import add_memo, add_todo, list_memos, list_todos, delete_memo, delete_todo, complete_todo, get_current_time, get_weather, web_search

TOOLS_LIST = [
    {'name': 'add_memo',
     'desc': '把用户要求记的内容存入备忘录，参数 text 是要记的具体内容',
     'func': add_memo,
     'args': ['text']},
    {'name': 'add_todo',
     'desc': '把用户将来要做的事情存入待办清单，参数 text 是将来要做的具体事情',
     'func': add_todo,
     'args': ['text']},
    {'name': 'list_memos',
     'desc': '查询用户存入备忘录的内容，无参数',
     'func': list_memos,
     'args': []},
    {'name': 'list_todos',
     'desc': '查询用户存入待办的内容，无参数',
     'func': list_todos,
     'args': []},
    {'name': 'delete_memo',
     'desc': '删除用户存入备忘录的内容，参数 lineno 是内容在文档中的序号，参数 keyword 是关键字，两者取其一即可',
     'func': delete_memo,
     'args': ['lineno', 'keyword']},
    {'name': 'delete_todo',
     'desc': '删除用户存入待办清单的内容，参数 lineno 是内容在文档中的序号，参数 keyword 是关键字，两者取其一即可',
     'func': delete_todo,
     'args': ['lineno', 'keyword']},
    {'name': 'complete_todo',
     'desc': '将待办清单中的待办标记为已完成，参数 lineno 是内容的序号',
     'func': complete_todo,
     'args': ['lineno']},
    {'name': 'get_current_time',
     'desc': '查询当前的日期和时间，当用户问现在几点、今天几号、今天星期几、现在是什么时候时使用',
     'func': get_current_time,
     'args': []},
    {'name': 'get_weather',
     'desc': '查询指定城市的天气情况，参数 city 是要查询的城市名称；当用户问天气、气温、冷不冷、要不要带伞，但没有说城市时，不要自己猜，把 city 留空',
     'func': get_weather,
     'args': ['city'],
     'options': ['city']},
    {'name': 'web_search',
     'desc': '在网上搜索外部信息，当用户要查新闻、最新消息，或问某个具体事物的资料（发布时间、价格、近况等）时使用；参数 query 是搜索关键词，要把问题提炼成简短的关键词，不要照抄整句话',
     'func': web_search,
     'args': ['query']}
]
