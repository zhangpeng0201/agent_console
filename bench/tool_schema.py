'''
工具说明书
'''

TOOLS_SCHEMA = [
    {"type": "function",
     "function": {
         "name": "add_memo",
         "description": "把用户要求记的内容存入备忘录",
         "parameters": {
             "type": "object",
             "properties": {"text": {"type": "string", "description": "参数 text 是要记的具体内容"}},
             "required": ["text"]}}},
    {"type": "function",
     "function": {
         "name": "add_todo",
         "description": "把用户将来要做的事情存入待办清单",
         "parameters": {
             "type": "object",
             "properties": {"text": {"type": "string", "description": "参数 text 是将来要做的具体事情"}},
             "required": ["text"]}}},
    {"type": "function",
     "function": {
         "name": "list_memos",
         "description": "查询用户存入备忘录的内容",
         "parameters": {
             "type": "object",
             "properties": {},
             "required": []}}},
    {"type": "function",
     "function": {
         "name": "list_todos",
         "description": "查询用户存入待办的内容",
         "parameters": {
             "type": "object",
             "properties": {},
             "required": []}}},
    {"type": "function",
     "function": {
         "name": "delete_memo",
         "description": "删除用户存入备忘录的内容，两个参数填其中一个即可",
         "parameters": {
             "type": "object",
             "properties": {"lineno": {"type": "integer", "description": "参数 lineno 是内容在文档中的序号"}, "keyword": {"type": "string", "description": "参数 keyword 是关键字"}},
             "required": []}}},
    {"type": "function",
     "function": {
         "name": "delete_todo",
         "description": "删除用户存入待办清单的内容，两个参数填其中一个即可",
         "parameters": {
             "type": "object",
             "properties": {"lineno": {"type": "integer", "description": "参数 lineno 是内容在文档中的序号"},
                            "keyword": {"type": "string", "description": "参数 keyword 是关键字"}},
             "required": []}}},
    {"type": "function",
     "function": {
         "name": "complete_todo",
         "description": "将待办清单中的待办标记为已完成",
         "parameters": {
             "type": "object",
             "properties": {"lineno": {"type": "integer", "description": "参数 lineno 是内容的序号"}},
             "required": ["lineno"]}}},
    {"type": "function",
     "function": {
         "name": "get_current_time",
         "description": "查询当前的日期和时间，当用户问现在几点、今天几号、今天星期几、现在是什么时候时使用",
         "parameters": {
             "type": "object",
             "properties": {},
             "required": []}}},
    {"type": "function",
     "function": {
         "name": "get_weather",
         "description": "查询指定城市的天气情况",
         "parameters": {
             "type": "object",
             "properties": {"city": {"type": "string",
                                     "description": "参数 city 是要查询的城市名称"}},
             "required": []}}},
    {"type": "function",
     "function": {
         "name": "web_search",
         "description": "在网上搜索外部信息，当用户要查新闻、最新消息，或问某个具体事物的资料（发布时间、价格、近况等）时使用",
         "parameters": {
             "type": "object",
             "properties": {
                 "query": {"type": "string",
                          "description": "参数 query 是搜索关键词，要把问题提炼成简短的关键词，不要照抄整句话"}},
             "required": ["query"]}}}

]
