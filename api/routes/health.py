# 第 1 阶段 · 顺序 3
# 本阶段最后一个文件。写在 api/main.py 之后。main.py 再用 include_router 把它挂上。

# 从 FastAPI 框架里导入 APIRouter。
# APIRouter 是「一组接口」的容器，本文件只用它登记健康检查这一个接口。
from fastapi import APIRouter

# 创建一个本文件专用的路由器实例，变量名必须叫 router。
# api/main.py 会用 include_router 把它挂到整个应用上，外部才能访问。
router = APIRouter()


# 装饰器：把下面的 health 函数登记成 HTTP GET /health。
# 浏览器、负载均衡、启动测试都会用 GET 来探这个地址。
@router.get("/health")
# 定义处理函数。用普通 def 而不是 async def，因为这里没有任何等待操作。
def health():
    # 返回一个字典。FastAPI 会把它自动转成 JSON：{"status": "healthy"}。
    # 只要进程还能执行到这一行，就说明服务还活着。这里不查数据库、不调模型。
    return {"status": "healthy"}
