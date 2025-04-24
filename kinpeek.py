from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import yaml
import requests
import secrets
import datetime
import os

# Initialize FastAPI app
app = FastAPI()

# Load configuration from config.yaml
with open("config.yaml", "r") as config_file:
    config = yaml.safe_load(config_file)
STASH_SERVER = f"http://{config['stash']['server_ip']}:{config['stash']['port']}"
STASH_API_KEY = config['stash']['api_key']

# SQLite database setup
DATABASE_URL = "sqlite:///shared_videos.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database model
class SharedVideo(Base):
    __tablename__ = "shared_videos"
    id = Column(Integer, primary_key=True, index=True)
    share_id = Column(String, unique=True, index=True)
    video_name = Column(String)
    stash_video_id = Column(Integer)
    expires_at = Column(DateTime)
    hits = Column(Integer, default=0)

Base.metadata.create_all(bind=engine)

# Pydantic model for sharing a video
class ShareVideoRequest(BaseModel):
    video_name: str
    stash_video_id: int
    days_valid: int = 7  # Default to 7 days validity

# Generate a unique share ID
def generate_share_id(length=8):
    return secrets.token_urlsafe(length)

# Share a video
@app.post("/share")
async def share_video(request: ShareVideoRequest):
    share_id = generate_share_id()
    expires_at = datetime.datetime.now() + datetime.timedelta(days=request.days_valid)
    
    db = SessionLocal()
    try:
        shared_video = SharedVideo(
            share_id=share_id,
            video_name=request.video_name,
            stash_video_id=request.stash_video_id,
            expires_at=expires_at,
            hits=0
        )
        db.add(shared_video)
        db.commit()
        return {"share_url": f"/share/{share_id}"}
    finally:
        db.close()

# Stream video via share link
@app.get("/share/{share_id}")
async def stream_shared_video(share_id: str):
    db = SessionLocal()
    try:
        video = db.query(SharedVideo).filter(SharedVideo.share_id == share_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Share link not found")
        if video.expires_at < datetime.datetime.now():
            raise HTTPException(status_code=403, detail="Share link has expired")
        
        # Increment hit counter
        video.hits += 1
        db.commit()
        
        # Construct Stash streaming URL
        stash_url = f"{STASH_SERVER}/scene/{video.stash_video_id}/stream?apikey={STASH_API_KEY}"
        
        # Stream the video from Stash
        response = requests.get(stash_url, stream=True)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch video from Stash")
        
        # Return an HTML page with video player
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{video.video_name}</title>
        </head>
        <body>
            <video width="800" controls>
                <source src="/stream/{share_id}" type="video/mp4">
                Your browser does not support the video tag.
            </video>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    finally:
        db.close()

# Proxy the video stream
@app.get("/stream/{share_id}")
async def proxy_video_stream(share_id: str):
    db = SessionLocal()
    try:
        video = db.query(SharedVideo).filter(SharedVideo.share_id == share_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Share link not found")
        if video.expires_at < datetime.datetime.now():
            raise HTTPException(status_code=403, detail="Share link has expired")
        
        # Construct Stash streaming URL
        stash_url = f"{STASH_SERVER}/scene/{video.stash_video_id}/stream?apikey={STASH_API_KEY}"
        
        # Stream the video from Stash
        response = requests.get(stash_url, stream=True)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch video from Stash")
        
        # Proxy the stream
        def stream_content():
            for chunk in response.iter_content(chunk_size=1024*1024):
                if chunk:
                    yield chunk
        
        return StreamingResponse(
            stream_content(),
            media_type="video/mp4",
            headers={
                "Content-Length": response.headers.get("Content-Length"),
                "Accept-Ranges": "bytes"
            }
        )
    finally:
        db.close()

# Get shared video details (for admin purposes)
@app.get("/shared_videos")
async def list_shared_videos():
    db = SessionLocal()
    try:
        videos = db.query(SharedVideo).all()
        return [
            {
                "share_id": v.share_id,
                "video_name": v.video_name,
                "stash_video_id": v.stash_video_id,
                "expires_at": v.expires_at,
                "hits": v.hits
            }
            for v in videos
        ]
    finally:
        db.close()
