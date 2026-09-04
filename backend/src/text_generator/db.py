import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]

connect_args = {
    "timeout": 10,
    "command_timeout": 30,
    "server_settings": {
        "application_name": "textgen",
    },
}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=connect_args,
)

SessionMaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
