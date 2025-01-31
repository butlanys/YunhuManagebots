import os
import time
import json
import requests
from flask import Flask, request, jsonify
from threading import Thread
import base64
import re
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

# 环境变量
TOKEN = os.getenv("TOKEN")  # 可在官网后台获取
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")  # 管理员token
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")

app = Flask(__name__)

# 数据库操作函数
def get_db_connection():
    """获取数据库连接"""
    return mysql.connector.connect(
        host=MYSQL_HOST,
        database=MYSQL_DATABASE,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD
    )

def create_table():
    """创建数据库表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            msg_id VARCHAR(255) PRIMARY KEY,  -- 修改这里
            chat_id VARCHAR(255),
            user_id VARCHAR(255),
            user_name VARCHAR(255),
            message TEXT,
            timestamp BIGINT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS temp_admins (
            chat_id VARCHAR(255),
            user_id VARCHAR(255),
            user_nickname VARCHAR(255),
            PRIMARY KEY (chat_id, user_id)
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

def insert_message(msg_id, chat_id, user_id, user_name, message, timestamp):
    """插入消息记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO messages (msg_id, chat_id, user_id, user_name, message, timestamp) VALUES (%s, %s, %s, %s, %s, %s)",
                       (msg_id, chat_id, user_id, user_name, message, timestamp))
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error inserting message: {err}")
    finally:
        cursor.close()
        conn.close()

def get_user_messages(chat_id, user_id, limit=10):
    """获取用户最近的消息记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT msg_id FROM messages WHERE chat_id=%s AND user_id=%s ORDER BY id DESC LIMIT %s", (chat_id, user_id, limit))
    messages = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return messages

def add_temp_admin(chat_id, user_id, user_nickname):
    """添加临时管理员"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT IGNORE INTO temp_admins (chat_id, user_id, user_nickname) VALUES (%s, %s, %s)", (chat_id, user_id, user_nickname))
    conn.commit()
    cursor.close()
    conn.close()

def remove_temp_admin(chat_id, user_id):
    """移除临时管理员"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM temp_admins WHERE chat_id=%s AND user_id=%s", (chat_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()

def get_temp_admins(chat_id):
    """获取临时管理员列表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, user_nickname FROM temp_admins WHERE chat_id=%s", (chat_id,))
    admins = cursor.fetchall()
    cursor.close()
    conn.close()
    return admins

# 消息处理函数
def handle_message(json_data):
    """处理接收到的消息"""
    event_type = json_data.get("header", {}).get("eventType")

    if event_type == "message.receive.normal":
        chat_id = json_data["event"]["chat"]["chatId"]
        msg_id = json_data["event"]["message"]["msgId"]
        content_type = json_data["event"]["message"]["contentType"]
        user_id = json_data["event"]["sender"]["senderId"]
        user_name = json_data["event"]["sender"]["senderNickname"]
        user_level = json_data["event"]["sender"]["senderUserLevel"]
        timestamp = json_data["event"]["message"]["sendTime"]

        # 记录消息到数据库
        try:
            message_content = json.dumps(json_data["event"]["message"]["content"], ensure_ascii=False)
            print(message_content)
            insert_message(msg_id, chat_id, user_id, user_name, message_content, timestamp)
        except Exception as e:
            print(f"Error inserting message into database: {e}")

        content = json_data["event"]["message"]["content"].get("text", "")

        # 管理员指令处理
        if content_type == "text":
            temp_admins = [admin[0] for admin in get_temp_admins(chat_id)]
            if content.startswith("!help") or content.startswith("!ban") or content.startswith("!unban") or content.startswith("!kick") or content.startswith("!delmsg") or content.startswith("!addadmin") or content.startswith("!deladmin") or content.startswith("!adminlist"):
                if user_level == "owner" or user_level == "administrator":
                    if content.startswith("!ban"):
                        handle_ban_command(content, chat_id, json_data)
                    elif content.startswith("!unban"):
                        handle_unban_command(content, chat_id, json_data)
                    elif content.startswith("!kick"):
                        handle_kick_command(content, chat_id, json_data)
                    elif content.startswith("!addadmin"):
                        handle_addadmin_command(content, chat_id, json_data)
                    elif content.startswith("!deladmin"):
                        handle_deladmin_command(content, chat_id, json_data)
                    elif content.startswith("!adminlist"):
                        handle_adminlist_command(content, chat_id, json_data)
                    elif content.startswith("!delmsg"):
                        handle_delmsg_command(content, chat_id, json_data, msg_id)
                    elif content.startswith("!help"):
                        yhchat.push(chat_id, "group", "markdown", {"text": """#### 命令帮助
* !ban | 禁言
> !ban @用户 时间（禁言时长只能是 10、1h、6h、12h
* !unban | 取消禁言
> !unban @用户（对用户取消禁言
* !kick | 将用户移出群聊
> !kick @用户
* !delmsg | 删除用户消息
> !delmsg (并引用需要撤回的消息
> !delmsg @用户 需要撤回的条数(最大400条
* !addadmin | 添加临时管理员
> !addadmin @用户
* !deladmin | 删除临时管理员
> !deladmin @用户
* !adminlist | 查看临时管理员列表"""})
                        return
                """else:
                    yhchat.push(chat_id, "group", "text", {"text": "你没有权限执行此操作1"})"""
            if content.startswith("!delmsg") or content.startswith("!help"):
                if user_id in temp_admins:
                    if content.startswith("!delmsg"):
                        handle_delmsg_command(content, chat_id, json_data, msg_id)
                    elif content.startswith("!help"):
                        yhchat.push(chat_id, "group", "markdown", {"text": """#### 命令帮助
* !delmsg | 删除用户消息
> !delmsg (并引用需要撤回的消息
> !delmsg @用户 需要撤回的条数(最大400条"""})
                        return
                
                """else:
                    yhchat.push(chat_id, "group", "text", {"text": "你没有权限执行此操作"})"""
                    
def handle_addadmin_command(content, chat_id, json_data):
    """处理 !addadmin 命令"""
    parts = content.split()
    if len(parts) >= 2:
        executorUser=json_data["event"]["sender"]["senderNickname"]
        executorUserId=json_data["event"]["sender"]["senderId"]
        user_nickname = parts[1].replace("@", "")
        at_user_id = json_data["event"]["message"]["content"]["at"][0]
        #user_info = at_user_nickname
        """if user_info and "data" in user_info and "nickname" in user_info["data"]:
            user_nickname = user_info["data"]["nickname"]
        else:
            user_nickname = at_user_id # 如果获取不到昵称，则使用 ID 代替"""
        add_temp_admin(chat_id, at_user_id, user_nickname)
        yhchat.push(chat_id, "group", "text", {"text": f"已将 {user_nickname} 添加为临时管理员"})
        if chat_id == "big":
            yhchat.push("531122894", "group", "text", {"text": f"{user_nickname} 已被添加为临时管理员\n\n操作人：{executorUser}({executorUserId})"})
    else:
        yhchat.push(chat_id, "group", "text", {"text": "指令使用帮助：\n!addadmin @用户"})

def handle_deladmin_command(content, chat_id, json_data):
    """处理 !deladmin 命令"""
    parts = content.split()
    if len(parts) >= 2:
        executorUser=json_data["event"]["sender"]["senderNickname"]
        executorUserId=json_data["event"]["sender"]["senderId"]
        at_user_nickname = parts[1].replace("@", "")
        at_user_id = json_data["event"]["message"]["content"]["at"][0]
        remove_temp_admin(chat_id, at_user_id)
        yhchat.push(chat_id, "group", "text", {"text": f"已将 {at_user_nickname} 从临时管理员列表中移除"})
        if chat_id == "big":
            yhchat.push("531122894", "group", "text", {"text": f"{at_user_nickname} 已被移除临时管理员\n\n操作人：{executorUser}({executorUserId})"})
    else:
        yhchat.push(chat_id, "group", "text", {"text": "指令使用帮助：\n!deladmin @用户"})

def handle_adminlist_command(content, chat_id, json_data):
    """处理 !adminlist 命令"""
    temp_admins = get_temp_admins(chat_id)
    if temp_admins:
        admin_list_text = "当前群组的临时管理员列表：\n"
        for admin_id, admin_nickname in temp_admins:
            admin_list_text += f"- {admin_nickname} ({admin_id})\n"
        yhchat.push(chat_id, "group", "text", {"text": admin_list_text})
    else:
        yhchat.push(chat_id, "group", "text", {"text": "当前群组没有临时管理员"})
        
def handle_ban_command(content, chat_id, json_data):
    """处理 !ban 命令"""
    parts = content.split()
    if len(parts) >= 3:
      executorUser=json_data["event"]["sender"]["senderNickname"]
      executorUserId=json_data["event"]["sender"]["senderId"]
      at_user_nickname = parts[1].replace("@", "")
      duration = parts[-1]
      at_user_id = json_data["event"]["message"]["content"]["at"][0]

      if duration.endswith("h"):
          try:
              hours = int(duration[:-1])
              if hours not in [1, 6, 12]:
                  yhchat.push(chat_id, "group", "text", {"text": "禁言时长只能是 1h, 6h, 12h"})
                  return
              ban_time_seconds = hours * 3600
          except ValueError:
              yhchat.push(chat_id, "group", "text", {"text": "无效的禁言时长"})
              return
      elif duration == "10":
          ban_time_seconds = 600
      else:
          yhchat.push(chat_id, "group", "text", {"text": "禁言时长只能是 10、1h、6h、12h"})
          return
      yhchat.ban(chat_id, at_user_id, ban_time_seconds)
      yhchat.push(chat_id, "group", "text", {"text": f"{at_user_nickname} 已被禁言 {duration}"})
      if chat_id == "big":
          yhchat.push("531122894", "group", "text", {"text": f"{at_user_nickname} 已被禁言 {duration}\n\n操作人：{executorUser}({executorUserId})"})
    else:
        yhchat.push(chat_id, "group", "text", {"text": "指令使用帮助：\n!ban @用户 时长\n时长选项：10（10分钟）、1h（1小时）、6h（6小时）、12h（12小时）"})

def handle_unban_command(content, chat_id, json_data):
    """处理 !unban 命令"""
    parts = content.split()
    if len(parts) >= 2:
        executorUser=json_data["event"]["sender"]["senderNickname"]
        executorUserId=json_data["event"]["sender"]["senderId"]
        at_user_nickname = parts[1].replace("@", "")
        at_user_id = json_data["event"]["message"]["content"]["at"][0]
        yhchat.ban(chat_id, at_user_id, 0)  # 解除禁言
        yhchat.push(chat_id, "group", "text", {"text": f"{at_user_nickname} 已被解除禁言"})
        if chat_id == "big":
            yhchat.push("531122894", "group", "text", {"text": f"{at_user_nickname} 已被解除禁言\n\n操作人：{executorUser}({executorUserId})"})
    else:
        yhchat.push(chat_id, "group", "text", {"text": "指令使用帮助：\n!unban @用户"})

def handle_kick_command(content, chat_id, json_data):
    """处理 !kick 命令"""
    parts = content.split()
    if len(parts) >= 2:
        executorUser=json_data["event"]["sender"]["senderNickname"]
        executorUserId=json_data["event"]["sender"]["senderId"]
        at_user_nickname = parts[1].replace("@", "")
        at_user_id = json_data["event"]["message"]["content"]["at"][0]
        yhchat.kick(chat_id, at_user_id)
        yhchat.push(chat_id, "group", "text", {"text": f"{at_user_nickname} 已被移出群聊"})
        if chat_id == "big":
            yhchat.push("531122894", "group", "text", {"text": f"{at_user_nickname} 已被移出群聊\n\n操作人：{executorUser}({executorUserId})"})
    else:
        yhchat.push(chat_id, "group", "text", {"text": "指令使用帮助：\n!kick @用户"})

def handle_delmsg_command(content, chat_id, json_data, current_msg_id):
    """处理 !delmsg 命令"""
    parts = content.split()
    if "parent" in json_data["event"]["message"]["content"] and len(parts) == 1:
        executorUser=json_data["event"]["sender"]["senderNickname"]
        executorUserId=json_data["event"]["sender"]["senderId"]
        # 撤回引用的消息
        #print(json_data["event"]["message"]["content"]["parentId"])
        parent_msg_id = json_data["event"]["message"]["parentId"]
        yhchat.del_message(parent_msg_id, chat_id)
        yhchat.push(chat_id, "group", "text", {"text": "已撤回引用的消息"})
        yhchat.push("531122894", "group", "text", {"text": f"已撤回引用的消息\n\n操作人：{executorUser}({executorUserId})"})
    elif len(parts) >= 2:
        # 撤回指定用户的最近消息
        try:
            num_messages = int(parts[-1])
            if num_messages > 400 or num_messages < 1:
                yhchat.push(chat_id, "group", "text", {"text": f"只能删除1-400条消息"})
                return
        except ValueError:
            yhchat.push(chat_id, "group", "text", {"text": f"请输入正确的数字[1-400]"})
            return
        at_user_id = json_data["event"]["message"]["content"]["at"][0]
        msg_ids = get_user_messages(chat_id, at_user_id, num_messages)
        for msg_id in msg_ids:
            yhchat.del_message(msg_id, chat_id)
            time.sleep(0.2)
        yhchat.push(chat_id, "group", "text", {"text": f"已撤回 {parts[1]} 最近 {num_messages} 条消息"})
        executorUser=json_data["event"]["sender"]["senderNickname"]
        executorUserId=json_data["event"]["sender"]["senderId"]
        if chat_id == "big":
            yhchat.push("531122894", "group", "text", {"text": f"{parts[1]} 已被撤回最近 {num_messages} 条消息\n\n操作人：{executorUser}({executorUserId})"})
    else:
      yhchat.push(chat_id, "group", "text", {"text": "指令使用帮助：\n!delmsg 引用需要删除的消息\n!delmsg @用户 10"})

# yhchat API 函数 (保持原样，仅修改 del_message)
class yhchat:
    @staticmethod
    def push(recvId, recvType, contentType, content):
        url = f"https://yhchat.hqycloud.top/open-apis/v1/bot/send?token={TOKEN}"
        payload = json.dumps({
            "recvId": recvId,
            "recvType": recvType,
            "contentType": contentType,
            "content": content
        })
        headers = {
            'Content-Type': 'application/json'
        }
        response = requests.request("POST", url, headers=headers, data=payload)
        return json.loads(response.text)

    @staticmethod
    def parent_push(recvId, recvType, contentType, content, parentId):
        url = f"https://yhchat.hqycloud.top/open-apis/v1/bot/send?token={TOKEN}"
        payload = json.dumps({
            "recvId": recvId,
            "recvType": recvType,
            "contentType": contentType,
            "content": content,
            "parentId": parentId
        })
        headers = {
            'Content-Type': 'application/json'
        }
        response = requests.request("POST", url, headers=headers, data=payload)
        return json.loads(response.text)

    @staticmethod
    def batch_push(recvIds, recvType, contentType, content):
        url = f"https://yhchat.hqycloud.top/open-apis/v1/bot/batch_send?token={TOKEN}"
        payload = json.dumps({
            "recvIds": recvIds,
            "recvType": recvType,
            "contentType": contentType,
            "content": content
        })
        headers = {
            'Content-Type': 'application/json'
        }
        response = requests.request("POST", url, headers=headers, data=payload)
        return json.loads(response.text)

    @staticmethod
    def del_message(msgId, chatId):
        url = f"https://yhchat.hqycloud.top/open-apis/v1/bot/recall?token={TOKEN}"
        payload = json.dumps({
            "msgId": msgId,
            "chatId": chatId,
            "chatType": "group"
        })
        headers = {
            'Content-Type': 'application/json'
        }
        response = requests.request("POST", url, headers=headers, data=payload)
        return json.loads(response.text)
    
    @staticmethod
    def get_user_info(userId):
        url = f"https://yhchat.hqycloud.top/open-apis/v1/user/info?token={TOKEN}"
        payload = json.dumps({
            "userId": userId
        })
        headers = {
            'Content-Type': 'application/json'
        }
        response = requests.request("POST", url, headers=headers, data=payload)
        return json.loads(response.text)
    
    @staticmethod
    def del_message(msgId, chatId):
        url = f"https://yhchat.hqycloud.top/open-apis/v1/bot/recall?token={TOKEN}"
        payload = json.dumps({
            "msgId": msgId,
            "chatId": chatId,
            "chatType": "group"
        })
        headers = {
            'Content-Type': 'application/json'
        }
        response = requests.request("POST", url, headers=headers, data=payload)
        return json.loads(response.text)

    @staticmethod
    def ban(groupId,userId,ban_time):
        headers = {
            "User-Agent": "windows 1.5.47",
            "Accept": "application/x-protobuf",
            "Accept-Encoding": "gzip",
            "Host": "yhchat.hqycloud.top",
            "Content-Type": "application/x-protobuf",
            "token": ADMIN_TOKEN
        }
        url = f"https://yhchat.hqycloud.top/v1/group/gag-member"
        payload = json.dumps({"groupId":groupId,"userId":userId,"gag":ban_time})
        response = requests.request("POST", url, headers=headers, data=payload)
        return json.loads(response.text)

    @staticmethod
    def kick(groupId,userId):
        headers = {
            "User-Agent": "windows 1.5.47",
            "Accept": "application/x-protobuf",
            "Accept-Encoding": "gzip",
            "Host": "yhchat.hqycloud.top",
            "Content-Type": "application/x-protobuf",
            "token": ADMIN_TOKEN
        }
        url = f"https://yhchat.hqycloud.top/v1/group/remove-member"
        payload = json.dumps({"groupId":groupId,"userId":userId})
        response = requests.request("POST", url, headers=headers, data=payload)
        return json.loads(response.text)

# Flask 路由
@app.route('/yhchat', methods=['POST'])
def receive_message():
    try:
        json_data = request.get_json()
        thread = Thread(target=handle_message, args=(json_data,))
        thread.start()
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        print("Error:", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 主程序入口
if __name__ == '__main__':
    create_table()
    app.run(host='0.0.0.0', port=34436)