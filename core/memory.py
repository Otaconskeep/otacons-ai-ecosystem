import sqlite3, time
from pathlib import Path
class MemoryStore:
 def __init__(self,path):
  self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.db=sqlite3.connect(self.path); self.db.row_factory=sqlite3.Row; self.migrate()
 def migrate(self):
  self.db.executescript('''CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY); CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY); CREATE TABLE IF NOT EXISTS agents(id TEXT, user_id TEXT, PRIMARY KEY(id,user_id)); CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,user_id TEXT,agent_id TEXT,title TEXT,created_at REAL); CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id TEXT,user_id TEXT,agent_id TEXT,role TEXT,content TEXT,created_at REAL); CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT,agent_id TEXT,content TEXT,source_conversation_id TEXT, memory_type TEXT DEFAULT 'fact',active INTEGER DEFAULT 1,created_at REAL,updated_at REAL);'''); self.db.commit()
 def create_conversation(self,user,agent,title='New conversation'):
  import uuid; cid=str(uuid.uuid4()); self.db.execute('INSERT INTO conversations VALUES(?,?,?,?,?)',(cid,user,agent,title,time.time())); self.db.commit(); return cid
 def append(self,cid,user,agent,role,content): self.db.execute('INSERT INTO messages(conversation_id,user_id,agent_id,role,content,created_at) VALUES(?,?,?,?,?,?)',(cid,user,agent,role,content,time.time())); self.db.commit()
 def list_conversations(self,user,agent): return [dict(x) for x in self.db.execute('SELECT * FROM conversations WHERE user_id=? AND agent_id=? ORDER BY created_at DESC',(user,agent))]
 def get_conversation(self,cid,user,agent):
  row=self.db.execute('SELECT * FROM conversations WHERE id=? AND user_id=? AND agent_id=?',(cid,user,agent)).fetchone(); return {'conversation':dict(row) if row else None,'messages':self.messages(cid)}
 def delete_conversation(self,cid,user,agent): self.db.execute('DELETE FROM messages WHERE conversation_id=? AND user_id=? AND agent_id=?',(cid,user,agent)); self.db.execute('DELETE FROM conversations WHERE id=? AND user_id=? AND agent_id=?',(cid,user,agent)); self.db.commit()
 def messages(self,cid,limit=20): return [dict(x) for x in self.db.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?', (cid,limit)).fetchall()][::-1]
 def remember(self,user,agent,content,source=None): self.db.execute('INSERT INTO memories(user_id,agent_id,content,source_conversation_id,created_at,updated_at) VALUES(?,?,?,?,?,?)',(user,agent,content,source,time.time(),time.time())); self.db.commit()
 def retrieve(self,user,agent,query,limit=5):
  terms=set(query.lower().split()); rows=self.db.execute('SELECT * FROM memories WHERE user_id=? AND agent_id=? AND active=1',(user,agent)).fetchall(); ranked=sorted(rows,key=lambda r:sum(t in r['content'].lower() for t in terms),reverse=True); return [dict(x) for x in ranked[:limit] if any(t in x['content'].lower() for t in terms)]
 def list_memories(self,user,agent): return [dict(x) for x in self.db.execute('SELECT * FROM memories WHERE user_id=? AND agent_id=? AND active=1 ORDER BY id',(user,agent))]
 def delete_memory(self,mid,user,agent): self.db.execute('UPDATE memories SET active=0,updated_at=? WHERE id=? AND user_id=? AND agent_id=?',(time.time(),mid,user,agent)); self.db.commit()
 def close(self): self.db.close()
