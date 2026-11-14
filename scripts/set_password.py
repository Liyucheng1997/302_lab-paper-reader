# -*- coding: utf-8 -*-
"""设置站长密码（只保存加盐哈希到 config.local.json，不保存明文）。

用法: python scripts/set_password.py          （交互输入）
      python scripts/set_password.py 新密码
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import auth  # noqa: E402


def main():
    pw = sys.argv[1] if len(sys.argv) > 1 else getpass.getpass("新的站长密码: ")
    if len(sys.argv) <= 1 and getpass.getpass("再输一次: ") != pw:
        sys.exit("两次输入不一致")
    auth.set_password(pw)
    print("站长密码已设置（重启不需要，立即生效）")


if __name__ == "__main__":
    main()
