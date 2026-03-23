"""测试飞书 API 发消息能力
用法：
  python test_feishu_send.py list        -- 列出 bot 所在的所有会话
  python test_feishu_send.py send <chat_id> <message>  -- 发送消息到指定会话
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
import yaml


def load_config():
    # 脚本移至 scripts/ 目录后，config.yml 位于上一级（项目根目录）
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yml")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    feishu = cfg.get("plugins", {}).get("feishu", {})
    return feishu["app_id"], feishu["app_secret"]


def get_tenant_token(app_id: str, app_secret: str) -> str:
    resp = httpx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 token 失败: {data}")
    print(f"[OK] tenant_access_token 获取成功 (expires in {data['expire']}s)")
    return data["tenant_access_token"]


def list_chats(token: str):
    """列出 bot 所在的群聊/会话"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(
        "https://open.feishu.cn/open-apis/im/v1/chats",
        headers=headers,
        params={"page_size": 20},
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[ERROR] 获取会话列表失败: {data}")
        return

    items = data.get("data", {}).get("items", [])
    if not items:
        print("[INFO] bot 当前没有加入任何会话")
        print("[HINT] 请先在飞书中给 bot 发一条消息（私聊），或将 bot 拉入群组")
        return

    print(f"\n{'='*60}")
    print(f"Bot 所在的会话列表 (共 {len(items)} 个):")
    print(f"{'='*60}")
    for item in items:
        chat_id = item.get("chat_id", "N/A")
        name = item.get("name", "(私聊)")
        chat_type = item.get("chat_type", "N/A")
        owner_id = item.get("owner_id", "N/A")
        desc = item.get("description", "")
        print(f"\n  chat_id:  {chat_id}")
        print(f"  name:     {name}")
        print(f"  type:     {chat_type}")
        print(f"  owner_id: {owner_id}")
        if desc:
            print(f"  desc:     {desc}")
    print(f"\n{'='*60}")
    print("使用以下命令发送测试消息:")
    if items:
        print(f'  python {sys.argv[0]} send {items[0]["chat_id"]} "Hello from Sensenova-Claw!"')


def send_message(token: str, chat_id: str, text: str):
    """发送文本消息到指定 chat_id"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    body = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}),
    }
    resp = httpx.post(
        "https://open.feishu.cn/open-apis/im/v1/messages",
        headers=headers,
        params={"receive_id_type": "chat_id"},
        json=body,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[ERROR] 发送失败: code={data.get('code')} msg={data.get('msg')}")
        print(f"  详情: {json.dumps(data, ensure_ascii=False, indent=2)}")
    else:
        msg_id = data.get("data", {}).get("message_id", "N/A")
        print(f"[OK] 消息发送成功! message_id={msg_id}")
        print(f"  内容: {text}")
        print(f"  目标: {chat_id}")


def get_bot_info(token: str):
    """获取 bot 自身信息"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(
        "https://open.feishu.cn/open-apis/bot/v3/info",
        headers=headers,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[ERROR] 获取 bot 信息失败: code={data.get('code')} msg={data.get('msg')}")
        return
    bot = data.get("bot", {})
    print(f"\n[Bot 信息]")
    print(f"  app_name:   {bot.get('app_name', 'N/A')}")
    print(f"  open_id:    {bot.get('open_id', 'N/A')}")
    print(f"  bot_name:   {bot.get('bot_name', 'N/A')}")


def send_by_open_id(token: str, open_id: str, text: str):
    """通过 open_id 发送消息给用户"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    body = {
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}),
    }
    resp = httpx.post(
        "https://open.feishu.cn/open-apis/im/v1/messages",
        headers=headers,
        params={"receive_id_type": "open_id"},
        json=body,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[ERROR] 发送失败: code={data.get('code')} msg={data.get('msg')}")
        print(f"  详情: {json.dumps(data, ensure_ascii=False, indent=2)}")
    else:
        msg_id = data.get("data", {}).get("message_id", "N/A")
        print(f"[OK] 消息发送成功! message_id={msg_id}")
        print(f"  内容: {text}")
        print(f"  目标 open_id: {open_id}")


def find_user_by_id(token: str, user_id_type: str, user_ids: list[str]):
    """通过 email/mobile/user_id 查找用户的 open_id"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    body = {}
    if user_id_type == "email":
        body["emails"] = user_ids
    elif user_id_type == "mobile":
        body["mobiles"] = user_ids
    resp = httpx.post(
        "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id",
        headers=headers,
        params={"user_id_type": "open_id"},
        json=body,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[ERROR] 查找用户失败: code={data.get('code')} msg={data.get('msg')}")
        return
    user_list = data.get("data", {}).get("user_list", [])
    for u in user_list:
        print(f"  {u}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    app_id, app_secret = load_config()
    print(f"[INFO] app_id={app_id}")

    token = get_tenant_token(app_id, app_secret)

    cmd = sys.argv[1]
    if cmd == "list":
        list_chats(token)
    elif cmd == "bot":
        get_bot_info(token)
    elif cmd == "send":
        if len(sys.argv) < 4:
            print("用法: python test_feishu_send.py send <chat_id> <message>")
            sys.exit(1)
        chat_id = sys.argv[2]
        message = sys.argv[3]
        send_message(token, chat_id, message)
    elif cmd == "send_user":
        if len(sys.argv) < 4:
            print("用法: python test_feishu_send.py send_user <open_id> <message>")
            sys.exit(1)
        open_id = sys.argv[2]
        message = sys.argv[3]
        send_by_open_id(token, open_id, message)
    elif cmd == "find":
        if len(sys.argv) < 4:
            print("用法: python test_feishu_send.py find email|mobile <value>")
            sys.exit(1)
        id_type = sys.argv[2]
        value = sys.argv[3]
        find_user_by_id(token, id_type, [value])
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
