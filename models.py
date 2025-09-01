# SQLAlchemy Models (antes: deepseek_python_20250830_f6b98c.py)
import os
from dotenv import load_dotenv
from sqlalchemy import (create_engine, Column, Integer, String, Float, 
                        DateTime, func, VARCHAR)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

load_dotenv()

MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "g273f123")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "binance")
DATABASE_URL = f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"

try:
    engine = create_engine(DATABASE_URL, pool_recycle=3600)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    print("✅ Database connection established successfully.")
except Exception as e:
    print(f"❌ Error connecting to the database: {e}")
    engine = None
    SessionLocal = None
    Base = object

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    pnl = Column(Float, nullable=False, default=0.0)
    roe = Column(Float, nullable=False, default=0.0)
    leverage = Column(Integer, nullable=False)
    close_type = Column(String(20), nullable=False, default="unknown")
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    date = Column(String(10), nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    strategy = Column(String(50), nullable=True)
    duration = Column(Float, nullable=True)

class DailySummary(Base):
    __tablename__ = "daily_summary"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(VARCHAR(10), nullable=False, unique=True, index=True)
    total_trades = Column(Integer, default=0)
    open_trades = Column(Integer, default=0)
    closed_trades = Column(Integer, default=0)
    daily_pnl = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

def init_db():
    if engine:
        try:
            Base.metadata.create_all(bind=engine)
            print("🔍 Database tables verified/created.")
        except Exception as e:
            print(f"❌ Could not create tables: {e}")