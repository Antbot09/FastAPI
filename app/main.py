from fastapi import FastAPI, HTTPException, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, EmailStr, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from typing import List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from sqlalchemy.sql import text
import logging
import asyncio

# Database setup
DATABASE_URL = "postgresql+asyncpg://postgres:123@localhost:5432/fastapi_db"
engine = create_async_engine(DATABASE_URL, echo=True)
Base = declarative_base()
async_session = async_sessionmaker(engine, expire_on_commit=False)

# Dependency
async def get_session():
    async with async_session() as session:
        yield session

# User model
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)

# Pydantic schemas
class UserCreate(BaseModel):
    name: str
    email: EmailStr

class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)

# FastAPI app
app = FastAPI()

# Middleware to log requests and responses
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logging.info(f"Request: {request.method} {request.url}")
        response = await call_next(request)
        logging.info(f"Response status: {response.status_code}")
        return response

# Add middleware to the app
app.add_middleware(LoggingMiddleware)

# Custom exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": exc.errors(), "body": exc.body},
    )

# Add middleware to restrict allowed hosts (optional security)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

@app.post("/api/v1/users/", response_model=UserResponse)
async def create_user(user: UserCreate, session: AsyncSession = Depends(get_session)):
    new_user = User(name=user.name, email=user.email)
    session.add(new_user)
    try:
        await session.commit()
        await session.refresh(new_user)
        return new_user
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Error creating user")

@app.get("/api/v1/users/", response_model=List[UserResponse])
async def get_users(session: AsyncSession = Depends(get_session)):
    result = await session.execute(text("SELECT * FROM users"))
    users = result.fetchall()
    return users

@app.get("/api/v1/users/{id}", response_model=UserResponse)
async def get_user(id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(f"SELECT * FROM users WHERE id = {id}")
    user = result.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.put("/api/v1/users/{id}", response_model=UserResponse)
async def update_user(id: int, user: UserCreate, session: AsyncSession = Depends(get_session)):
    result = await session.execute(f"SELECT * FROM users WHERE id = {id}")
    existing_user = result.fetchone()
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found")

    existing_user.name = user.name
    existing_user.email = user.email
    session.add(existing_user)
    try:
        await session.commit()
        await session.refresh(existing_user)
        return existing_user
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Error updating user")

@app.delete("/api/v1/users/{id}")
async def delete_user(id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(text(f"SELECT * FROM users WHERE id = :id"), {"id": id})
    user = result.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": id})
    try:
        await session.commit()
        return {"message": "User deleted successfully"}
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Error deleting user")

# Function to initialize the database schema
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Initialize the database schema when the script is run
if __name__ == "__main__":
    asyncio.run(init_db())