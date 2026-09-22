"""邮件发送（SMTP）。

用途：向用户邮箱下发登录验证码。

设计说明：
    - 使用 Python 标准库 smtplib，不引入第三方 SDK（避免额外依赖与版本问题）；
    - 465 端口 SSL 直连（QQ / 163 / Gmail / 企业邮均支持）；
    - EMAIL_DEBUG=true 时为空操作，验证码由接口响应返回，便于本地联调。

⚠️ 安全约定：
    1. SMTP 授权码只从 .env 读取，绝不写死在代码里；
    2. 验证码绝不写入日志（日志泄露等于验证码泄露）。
"""
import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from app.config import (
    EMAIL_DEBUG,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


def send_email_code(to_email: str, code: str, ttl_minutes: int = 5) -> None:
    """发送验证码邮件。

    参数：
        to_email:    收件邮箱
        code:        验证码
        ttl_minutes: 有效期（分钟），仅用于邮件文案

    异常：
        RuntimeError —— SMTP 未配置或发送失败。
                        由路由层的兜底异常处理器统一归一为 50000，
                        不向客户端暴露 SMTP 内部细节。
    """
    # 调试模式：不发邮件，验证码改由接口响应返回
    if EMAIL_DEBUG:
        logger.info("[mail] 调试模式，未真实发送，to=%s", to_email)
        return

    # ⚠️ 配置检查：未填 SMTP 时给出明确原因，避免用户只看到"登录失败"
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP 未配置：请在 server/.env 中填写 SMTP_USER 与 SMTP_PASSWORD（授权码）"
        )

    body = (
        "您好！\n\n"
        "您正在登录「%s」，本次验证码为：\n\n"
        "    %s\n\n"
        "验证码 %d 分钟内有效，请勿泄露给他人。\n"
        "如非本人操作，请忽略本邮件。\n"
    ) % (SMTP_FROM_NAME, code, ttl_minutes)

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = formataddr((str(Header(SMTP_FROM_NAME, "utf-8")), SMTP_USER))
    msg["To"] = to_email
    msg["Subject"] = Header("【%s】登录验证码" % SMTP_FROM_NAME, "utf-8")

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
        # ⚠️ 只记录收件人与事件，绝不打印验证码
        logger.info("[mail] 验证码邮件已发送 to=%s", to_email)
    except smtplib.SMTPAuthenticationError as e:
        logger.error("[mail] SMTP 认证失败（多为授权码错误）: %s", e)
        raise RuntimeError("邮件服务认证失败，请检查 SMTP 授权码") from e
    except Exception as e:
        logger.error("[mail] 邮件发送失败: %r", e)
        raise RuntimeError("验证码邮件发送失败，请稍后重试") from e
