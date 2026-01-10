import sqlite3
import json
from datetime import datetime

DB_PATH = "call_metrics.db"

def inspect_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print(f"\n{'='*20} RECENT CALLS {'='*20}")
        print(f"{'Call SID':<38} | {'Status':<10} | {'Score':<5} | {'Agent Path'}")
        print("-" * 80)
        
        cursor.execute("SELECT call_sid, status, total_score, agent_path FROM calls ORDER BY start_time DESC LIMIT 10")
        rows = cursor.fetchall()
        
        for row in rows:
            path = row['agent_path']
            # Truncate path if too long
            if len(path) > 30:
                path = path[:27] + "..."
            print(f"{row['call_sid']:<38} | {row['status']:<10} | {str(row['total_score']):<5} | {path}")

        print(f"\n{'='*20} LEARNED RULES {'='*20}")
        cursor.execute("SELECT rule_text, source_call_sid, created_at FROM learned_rules ORDER BY created_at DESC")
        rules = cursor.fetchall()
        
        if not rules:
            print("No rules learned yet.")
        else:
            for r in rules:
                print(f"[{r['created_at']}] FROM {r['source_call_sid'][:8]}...")
                print(f"RULE: {r['rule_text']}")
                print("-" * 40)
        
        conn.close()
        
    except Exception as e:
        print(f"Error reading DB: {e}")

if __name__ == "__main__":
    inspect_db()
