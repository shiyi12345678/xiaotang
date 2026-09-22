"""统一响应与业务异常。

成功响应：{"code": 0, "msg": "ok", "data": {...}}
失败响应：抛 BizError，由 main.py 的异常处理器统一转为 HTTP 响应
         （HTTP 状态语义化 + 业务码定位问题）

⚠️ 与客户端约定（必须保持一致，否则前端需全量改造）：
    - 成功码为 0（不是 200）
    - 消息字段名为 msg（不是 message）
    - 该约定与客户端 common/utils/format.js 中的 mockRequest 完全一致
"""


class BizError(Exception):
    """业务异常。

    参数：
        code: 业务错误码，用于前端精确定位问题
        msg:  面向用户的提示文案
        http: HTTP 状态码，默认 400；鉴权类错误传 401
    """

    def __init__(self, code: int, msg: str, http: int = 400):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.http = http


def ok(data=None) -> dict:
    """构造统一成功响应。

    参数：
        data: 业务数据；为 None 时返回空对象 {}（而非 null），
              便于前端统一按对象取值，无需额外判空。
    """
    return {"code": 0, "msg": "ok", "data": {} if data is None else data}
