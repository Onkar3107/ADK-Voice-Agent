import sqlite3
import logging
import json
import time
from datetime import datetime
from typing import List, Optional

import google.generativeai as genai
import os

logger = logging.getLogger("RLService")

class RLService:
    def __init__(self, db_path="call_metrics.db"):
        self.db_path = db_path
        self._init_db()
        
        # Configure GenAI for the Learning Loop with separate API key
        # Use RL_GOOGLE_API_KEY if available, otherwise fallback to GOOGLE_API_KEY
        rl_api_key = os.environ.get("RL_GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if rl_api_key:
            genai.configure(api_key=rl_api_key)
            logger.info(f"RL: Configured with {'dedicated' if os.environ.get('RL_GOOGLE_API_KEY') else 'shared'} API key")

    def _init_db(self):
        """Initializes the SQLite database with necessary tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table: calls
        # Tracks the overall state and score of a call
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS calls (
                call_sid TEXT PRIMARY KEY,
                status TEXT, -- INIT, LISTENING, THINKING, SPEAKING, COMPLETED
                total_score INTEGER DEFAULT 0,
                agent_path TEXT, -- JSON list of agents visited
                start_time TIMESTAMP,
                end_time TIMESTAMP
            )
        ''')

        # Table: call_events
        # Granular event log for detailed analysis
        # Table: call_events
        # Granular event log for detailed analysis
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS call_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_sid TEXT,
                timestamp REAL,
                event_type TEXT,
                value TEXT,
                FOREIGN KEY(call_sid) REFERENCES calls(call_sid)
            )
        ''')
        
        # Table: transcripts (New)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_sid TEXT,
                role TEXT, -- user/assistant
                content TEXT,
                timestamp REAL
            )
        ''')

        # Table: learned_rules (New)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS learned_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_text TEXT,
                source_call_sid TEXT,
                created_at TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()

    def start_call(self, call_sid: str):
        """Records a new call."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO calls (call_sid, status, start_time, agent_path, total_score)
            VALUES (?, ?, ?, ?, ?)
        ''', (call_sid, "INIT", datetime.now(), "[]", 0))
        conn.commit()
        conn.close()
        logger.info(f"RL: Started tracking call {call_sid}")

    def update_status(self, call_sid: str, status: str):
        """Updates the high-level status of the call."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE calls SET status = ? WHERE call_sid = ?', (status, call_sid))
        conn.commit()
        conn.close()

    def log_event(self, call_sid: str, event_type: str, value: str = ""):
        """Logs a specific event (e.g., THINKING_START)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO call_events (call_sid, timestamp, event_type, value)
            VALUES (?, ?, ?, ?)
        ''', (call_sid, time.time(), event_type, value))
        conn.commit()
        conn.close()

    def log_agent_routing(self, call_sid: str, agent_name: str):
        """Tracks which agent is handling the request (for routing penalty)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get current path
        cursor.execute('SELECT agent_path FROM calls WHERE call_sid = ?', (call_sid,))
        row = cursor.fetchone()
        if row:
            current_path = json.loads(row[0]) if row[0] else []
            current_path.append(agent_name)
            
            # Update path
            cursor.execute('UPDATE calls SET agent_path = ? WHERE call_sid = ?', 
                           (json.dumps(current_path), call_sid))
            
            # --- ROUTING PENALTY CHECK ---
            # Ideally, we want Root -> SpecificAgent. 
            # If we see SpecificAgent -> Root -> AnotherStrictAgent, that might be bad.
            # Simple Heuristic: If path length > 3 in a single turn, penalize (ping pong).
            # For now, just logging.
            
        conn.commit()
        conn.close()

    def process_turn_success(self, call_sid: str):
        """
        Called when user replies again. 
        Implies the *previous* turn was successful (they heard us and replied).
        Reward: +10
        """
        self._add_score(call_sid, 10, "TURN_SUCCESS")

    def process_hangup(self, call_sid: str, final_status: str):
        """
        Called when Twilio sends a 'completed' status callback.
        Check internal status to determine if it was a 'Thinking Hangup'.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT status FROM calls WHERE call_sid = ?', (call_sid,))
        row = cursor.fetchone()
        
        if row:
            internal_status = row[0]
            logger.info(f"RL: Hangup for {call_sid}. Internal Status: {internal_status}")
            
            if internal_status == "THINKING":
                # User hung up while we were thinking (latency violation)
                self._add_score(call_sid, -50, "PENALTY_LATENCY_HANGUP")
                logger.warning(f"RL: PENALTY APPLIED to {call_sid} for Thinking Hangup.")
            else:
                # Normal hangup (maybe successful?)
                # We give a small completion bonus, unless it was a very short call?
                # Let's just give +50 for a "completed" interaction for now.
                self._add_score(call_sid, 50, "CALL_COMPLETION_BONUS")
        
        conn.commit()
        conn.close()

    def _add_score(self, call_sid: str, points: int, reason: str):
        """Atomic update of score."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE calls SET total_score = total_score + ? WHERE call_sid = ?', (points, call_sid))
        conn.commit()
        conn.close()
        self.log_event(call_sid, "SCORE_CHANGE", f"{points} ({reason})")

    # --- LEARNING LOOP ---
    
    def log_chat(self, call_sid: str, role: str, content: str):
        """Logs a chat turn."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO transcripts (call_sid, role, content, timestamp) VALUES (?, ?, ?, ?)',
                       (call_sid, role, content, time.time()))
        conn.commit()
        conn.close()

    def get_transcript(self, call_sid: str) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT role, content FROM transcripts WHERE call_sid = ? ORDER BY timestamp ASC', (call_sid,))
        rows = cursor.fetchall()
        conn.close()
        
        transcript = ""
        for role, content in rows:
            transcript += f"{role.upper()}: {content}\n"
        return transcript

    def get_active_rules(self) -> str:
        """Returns a string list of all learned rules."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT rule_text FROM learned_rules ORDER BY created_at DESC LIMIT 5') # Last 5 rules
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return ""
            
        rules_str = "\n".join([f"- {r[0]}" for r in rows])
        return f"\n\n### LEARNED GUIDELINES (Critically Important):\n{rules_str}\n"

    def analyze_and_learn(self, call_sid: str):
        """
        Reflects on a specific call using an LLM to generate granular rules.
        Falls back to generic rule if API quota is exceeded.
        """
        # 1. Check Score
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT total_score FROM calls WHERE call_sid = ?', (call_sid,))
        row = cursor.fetchone()
        conn.close()
        
        if not row or row[0] >= 0:
            logger.info(f"RL: Call {call_sid} score {row[0] if row else 'NA'} is positive. No learning needed.")
            return

        logger.info(f"RL: Analyzing failed call {call_sid} (Score: {row[0]})...")
        
        # 2. Get Transcript
        transcript = self.get_transcript(call_sid)
        if not transcript:
            logger.warning("RL: No transcript found for analysis.")
            return
            
        # 3. Prompt Judge
        try:
            # Use configured model or fallback to environment
            model_name = os.environ.get("RL_GEMINI_MODEL") or os.environ.get("GOOGLE_GENAI_MODEL", "gemini-2.0-flash")
            model = genai.GenerativeModel(model_name)
            
            prompt = f"""
            You are a Senior Supervisor for a Customer Support AI.
            The following call ended in failure (User Hangup or Frustration).
            
            TRANSCRIPT:
            {transcript}
            
            Valid Tools available to the agent: [check_balance, process_payment, check_outage, run_diagnostics, escalate_to_human].
            
            TASK:
            Identify the ONE critical mistake the agent made (e.g., bad routing, hallucinations, verbosity).
            Write a SINGLE, concise system prompt instruction to prevent this in the future.
            Start the rule with "IF" or "ALWAYS" or "NEVER".
            Do not provide explanations, JUST the rule.
            
            Example: "IF user mentions 'bill', ALWAYS route to BillingAgent."
            """
            
            response = model.generate_content(prompt)
            rule = response.text.strip()
            
            logger.info(f"RL: Learned New Rule: {rule}")
            self._save_rule(rule, call_sid)
            
        except Exception as e:
            error_str = str(e)
            print(f"CRITICAL RL FAILURE: {e}")
            logger.error(f"RL: Learning failed: {e}")
            
            # Fallback: Insert generic rule if quota exceeded
            if "429" in error_str or "quota" in error_str.lower() or "RESOURCE_EXHAUSTED" in error_str:
                logger.warning("RL: API quota exceeded, using fallback rule.")
                fallback_rule = "IF call processing takes longer than 15 seconds, optimize response time and reduce complexity."
                self._save_rule(fallback_rule, call_sid, is_fallback=True)
            
    def _save_rule(self, rule_text: str, call_sid: str, is_fallback: bool = False):
        """Save a rule to the database, avoiding duplicates."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if this exact rule already exists
        cursor.execute('SELECT id FROM learned_rules WHERE rule_text = ?', (rule_text,))
        if cursor.fetchone():
            logger.info(f"RL: Rule already exists, skipping duplicate: {rule_text[:50]}...")
            conn.close()
            return
            
        # Insert new rule
        cursor.execute('INSERT INTO learned_rules (rule_text, source_call_sid, created_at) VALUES (?, ?, ?)',
                       (rule_text, call_sid, datetime.now()))
        conn.commit()
        conn.close()
        
        logger.info(f"RL: {'Fallback' if is_fallback else 'Learned'} rule saved: {rule_text[:50]}...")
