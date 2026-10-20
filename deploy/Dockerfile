# 构建上下文必须是 deploy/ 目录本身（下面的 COPY 路径都相对于它）
FROM python:3.11-slim

# PYTHONUNBUFFERED：print 立刻刷出去，崩溃时日志不会被吞在缓冲区
# PYTHONDONTWRITEBYTECODE：不生成 .pyc，镜像干净
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 后面所有相对路径的基准；也是 tools.py 里 BASE_DIR 的落点
WORKDIR /app

# 先依赖后代码：只改 src/ 时这两层命中缓存，不必重装
# 注意是 requirements.txt，不是 deploy/requirements.txt —— 上下文就是 deploy/
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再复制代码（src/static/index.html 一起进来）；第二个参数是容器内目标路径
COPY src/ ./src/

# 数据落点：/app/output/<user_id>/todos.json
RUN mkdir -p /app/output

# 平台固定端口，不可改
EXPOSE 7860

# --app-dir src：把 src/ 插进 sys.path，裸 import 才成立
# 关键：它不改变 cwd（仍是 /app），所以 output/ 落在 /app/output 而不是 /app/src/output
# exec 形式（数组）：uvicorn 直接是 PID 1，docker stop 的 SIGTERM 能收到
CMD ["uvicorn", "api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "7860"]
