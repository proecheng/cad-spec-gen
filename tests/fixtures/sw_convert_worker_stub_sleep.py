"""测试桩：模拟 worker 进入无限 sleep；父进程应在 timeout 时 kill。

使用方式：python -m tests.fixtures.sw_convert_worker_stub_sleep <sldprt> <tmp>
"""

from __future__ import annotations

import sys
import time


def main() -> int:
    if len(sys.argv) != 3:
        return 64
    time.sleep(120)  # 父进程应在 SINGLE_CONVERT_TIMEOUT_SEC 秒内 kill 我们
    return 0


if __name__ == "__main__":
    sys.exit(main())
