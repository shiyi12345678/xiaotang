"""短信发送抽象。

SMS_DEBUG=True（演示默认）：
    验证码随 /sms 接口响应以 dev_code 字段返回，由客户端 toast 展示；
    本层为空操作，验证码不写入任何日志。

SMS_DEBUG=False：
    在此接入真实短信通道（如阿里云 Dysmsapi）。

⚠️ 接入注意事项：
    1. 发送失败应抛出异常，由路由层归一为 50000，不要静默吞掉；
    2. 真实短信模板通常为 6 位验证码，需同步调整 SMS_CODE_LEN
       与客户端输入框的 maxlength；
    3. 验证码绝不允许进入业务日志（日志泄露等于验证码泄露）。
"""
import logging

from app.config import SMS_DEBUG

logger = logging.getLogger(__name__)


def send_sms(phone: str, code: str) -> None:
    """发送验证码短信。

    参数：
        phone: 接收手机号
        code:  验证码内容

    ⚠️ 安全：本函数及调用链不得打印 code，日志中只记录手机号与事件。
    """
    if not SMS_DEBUG:
        # TODO(接入真实通道)：调用短信服务商 SDK 发送 code。
        # 演示环境 SMS_DEBUG=True 时不会进入此分支。
        logger.info("[sms] 真实通道占位（未配置 SDK），phone=%s", phone)
