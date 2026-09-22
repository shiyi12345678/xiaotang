"""打印本机局域网 IP。

用途：
    供 server/start_server.bat 在启动前探测局域网地址，
    方便手机真机调试时把前端 common/config.js 里的 BASE_URL 改对。

为什么单独放一个脚本而不是在 .bat 里写 PowerShell：
    .bat 里嵌套 PowerShell 需要多层转义（^|、^>、$ 等），
    稍有出入就会静默失败；用 Python 单行实现更稳、更易读。

异常处理：
    任何异常都不向外抛出，统一打印 127.0.0.1 兜底，
    避免因探测失败导致启动脚本中断。
"""
import socket


def main() -> None:
    """探测并打印局域网 IP。

    原理：
        创建一个 UDP socket 并 connect 到外部地址。
        该操作不会真正发包，只是让操作系统按路由表选出一条出口网卡，
        从而拿到本机在该网段的 IP —— 比解析 ipconfig 输出更可靠，
        也不受系统语言（中文/英文）影响。
    """
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 只用于选路，不发送任何数据；这里用公共 DNS 地址作占位
        s.connect(("8.8.8.8", 80))
        print(s.getsockname()[0])
    except Exception:
        # 无网络、被防火墙拦截等情况下兜底，保证脚本能继续执行
        print("127.0.0.1")
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
