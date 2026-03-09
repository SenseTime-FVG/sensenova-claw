import sqlite3

db_path = "SenseAssistant/agentos.db"
conn = sqlite3.connect(db_path)

# 删除没有有效对话的空白会话
conn.execute("""
    DELETE FROM sessions
    WHERE session_id NOT IN (
        SELECT DISTINCT session_id FROM turns
        WHERE user_input IS NOT NULL AND user_input != ''
    )
""")

conn.commit()
deleted = conn.total_changes
conn.close()

print(f"已删除 {deleted} 个空白会话")
