from sqlmodel import SQLModel, Field, create_engine, Session, select
from sqlalchemy import text
from typing import Optional
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "projects-web.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    path: str
    display_name: Optional[str] = None
    last_session_id: Optional[str] = None
    category: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SessionMeta(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True)
    session_id: str = Field(index=True)
    display_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Approval(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True)
    tool_name: str
    tool_input_json: str
    decision: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None


class Mission(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    shared_prompt: Optional[str] = None
    mode: str = "parallel"  # 'parallel' | 'sequential'
    created_at: datetime = Field(default_factory=datetime.utcnow)
    archived_at: Optional[datetime] = None


class MissionAgent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    mission_id: int = Field(index=True, foreign_key="mission.id")
    project_id: int = Field(foreign_key="project.id")
    stream_id: Optional[str] = None
    label: Optional[str] = None
    message: str
    elevated: bool = False
    new_conversation: bool = False
    status: str = "pending"  # pending|running|done|error|cancelled
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    order_index: int = 0       # for sequential dispatch


class Watcher(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    name: str
    trigger_type: str  # 'file_change' | 'cron' | 'test_loop' | 'manual'
    trigger_config: str  # JSON config
    action_prompt: str
    enabled: bool = True
    elevated: bool = False
    last_fired_at: Optional[datetime] = None
    fire_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WatcherFire(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    watcher_id: int = Field(foreign_key="watcher.id", index=True)
    stream_id: Optional[str] = None
    trigger_info: Optional[str] = None
    fired_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"


class MissionScratchpad(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    mission_id: int = Field(index=True, foreign_key="mission.id")
    agent_id: Optional[int] = Field(default=None, foreign_key="missionagent.id")
    author: str  # 'agent' | 'planner' | 'user'
    text: str
    ref_files: Optional[str] = None  # JSON list of file refs
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StreamSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: str = Field(index=True, unique=True)
    project_id: int
    git_head: Optional[str] = None
    git_repo: bool = False
    started_at: datetime = Field(default_factory=datetime.utcnow)


class StreamCost(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: str = Field(index=True, unique=True)
    project_id: int = Field(index=True)
    mission_id: Optional[int] = Field(default=None, index=True)
    watcher_id: Optional[int] = Field(default=None, index=True)
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    duration_ms: int = 0
    captured_at: datetime = Field(default_factory=datetime.utcnow)


class Checkpoint(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: str = Field(index=True)
    project_id: int
    tool_use_id: Optional[str] = None
    label: Optional[str] = None
    stash_sha: str  # output of `git stash create`
    files_changed: Optional[str] = None  # JSON list
    created_at: datetime = Field(default_factory=datetime.utcnow)


def init_db():
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(project)")).fetchall()
        if not any(c[1] == "display_name" for c in cols):
            conn.execute(text("ALTER TABLE project ADD COLUMN display_name VARCHAR"))
            conn.commit()
        if not any(c[1] == "category" for c in cols):
            conn.execute(text("ALTER TABLE project ADD COLUMN category VARCHAR"))
            conn.commit()
        # Add order_index to MissionAgent if missing
        try:
            macols = conn.execute(text("PRAGMA table_info(missionagent)")).fetchall()
            if macols and not any(c[1] == "order_index" for c in macols):
                conn.execute(text("ALTER TABLE missionagent ADD COLUMN order_index INTEGER DEFAULT 0"))
                conn.commit()
        except Exception:
            pass
        # Add mode to Mission if missing
        try:
            mcols = conn.execute(text("PRAGMA table_info(mission)")).fetchall()
            if mcols and not any(c[1] == "mode" for c in mcols):
                conn.execute(text("ALTER TABLE mission ADD COLUMN mode VARCHAR DEFAULT 'parallel'"))
                conn.commit()
        except Exception:
            pass


def get_session():
    with Session(engine) as session:
        yield session


def seed_projects(defaults: list[dict]):
    with Session(engine) as session:
        for d in defaults:
            existing = session.exec(select(Project).where(Project.name == d["name"])).first()
            if not existing:
                session.add(Project(name=d["name"], path=d["path"]))
        session.commit()
