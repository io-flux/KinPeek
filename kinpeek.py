from fastapi import FastAPI, HTTPException, Response, Depends, status
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
import yaml
import requests
import secrets
import datetime
import uvicorn
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import timedelta
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production (e.g., ["http://your-domain.com"])
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Load configuration
try:
    with open("config.yaml", "r") as config_file:
        config = yaml.safe_load(config_file)
except Exception as e:
    logger.error(f"Failed to load config.yaml: {e}")
    raise

KINPEEK_HOST = config['kinpeek']['host']
KINPEEK_PORT = config['kinpeek']['port']
STASH_SERVER = f"http://{config['stash']['server_ip']}:{config['stash']['port']}"
STASH_API_KEY = config['stash']['api_key']
DISCLAIMER = config.get('disclaimer', '')
ADMIN_USERNAME = config['kinpeek']['admin_username']
ADMIN_PASSWORD = config['kinpeek']['admin_password']

# JWT settings
SECRET_KEY = secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
try:
    HASHED_ADMIN_PASSWORD = pwd_context.hash(ADMIN_PASSWORD)  # Hash at startup
    logger.info("Admin password hashed successfully")
except Exception as e:
    logger.error(f"Failed to hash admin password: {e}")
    raise

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

# Pydantic models
class ShareVideoRequest(BaseModel):
    video_name: str
    stash_video_id: int
    days_valid: int = 7

class Token(BaseModel):
    access_token: str
    token_type: str

# JWT authentication
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.now(datetime.timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(OAuth2PasswordRequestForm)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None or username != ADMIN_USERNAME:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception

# Generate unique share ID
def generate_share_id(length=8):
    return secrets.token_urlsafe(length)

# Root redirect to admin panel
@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/static/admin.html")

# Login endpoint
@app.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    logger.debug(f"Login attempt: username={form_data.username}")
    try:
        if not form_data.username or not form_data.password:
            logger.warning("Missing username or password in login request")
            raise HTTPException(status_code=422, detail="Username and password are required")
        if form_data.username != ADMIN_USERNAME:
            logger.warning(f"Invalid username: {form_data.username}")
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        if not pwd_context.verify(form_data.password, HASHED_ADMIN_PASSWORD):
            logger.warning("Password verification failed")
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        access_token = create_access_token(data={"sub": form_data.username})
        logger.info(f"Login successful for username={form_data.username}")
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Share a video
@app.post("/share")
async def share_video(request: ShareVideoRequest, current_user: str = Depends(get_current_user)):
    share_id = generate_share_id()
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=request.days_valid)
    
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
        logger.info(f"Video shared: share_id={share_id}, stash_video_id={request.stash_video_id}")
        return {"share_url": f"/share/{share_id}"}
    except Exception as e:
        logger.error(f"Error sharing video: {e}")
        raise HTTPException(status_code=500, detail="Failed to share video")
    finally:
        db.close()

# Edit a share
@app.put("/edit_share/{share_id}")
async def edit_share(share_id: str, request: ShareVideoRequest, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    try:
        video = db.query(SharedVideo).filter(SharedVideo.share_id == share_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Share link not found")
        video.video_name = request.video_name
        video.expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=request.days_valid)
        db.commit()
        logger.info(f"Share updated: share_id={share_id}")
        return {"message": "Share updated"}
    except Exception as e:
        logger.error(f"Error updating share: {e}")
        raise HTTPException(status_code=500, detail="Failed to update share")
    finally:
        db.close()

# Delete a share
@app.delete("/delete_share/{share_id}")
async def delete_share(share_id: str, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    try:
        video = db.query(SharedVideo).filter(SharedVideo.share_id == share_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Share link not found")
        db.delete(video)
        db.commit()
        logger.info(f"Share deleted: share_id={share_id}")
        return {"message": "Share deleted"}
    except Exception as e:
        logger.error(f"Error deleting share: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete share")
    finally:
        db.close()

# Stream video via share link
@app.get("/share/{share_id}", response_class=HTMLResponse)
async def stream_shared_video(share_id: str):
    db = SessionLocal()
    try:
        video = db.query(SharedVideo).filter(SharedVideo.share_id == share_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Share link not found")
        if video.expires_at < datetime.datetime.now(datetime.timezone.utc):
            raise HTTPException(status_code=403, detail="Share link has expired")
        
        video.hits += 1
        db.commit()
        logger.info(f"Video streamed: share_id={share_id}, hits={video.hits}")
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{video.video_name}</title>
            <link href="/static/styles.css" rel="stylesheet">
            <link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet">
        </head>
        <body>
            <div class="container">
                <img src="/static/logo-placeholder.png" alt="Logo" class="logo">
                <div class="video-container">
                    <video id="video-player" class="video-js vjs-default-skin" controls preload="auto" width="800">
                        <source src="/stream/{share_id}" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>
                </div>
                <p class="disclaimer">{DISCLAIMER}</p>
            </div>
            <script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
            <script>
                var player = videojs('video-player', {{
                    playbackRates: [0.5, 1, 1.5, 2]
                }});
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    except Exception as e:
        logger.error(f"Error streaming video: {e}")
        raise HTTPException(status_code=500, detail="Failed to stream video")
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
        if video.expires_at < datetime.datetime.now(datetime.timezone.utc):
            raise HTTPException(status_code=403, detail="Share link has expired")
        
        stash_url = f"{STASH_SERVER}/scene/{video.stash_video_id}/stream?apikey={STASH_API_KEY}"
        response = requests.get(stash_url, stream=True)
        if response.status_code != 200:
            logger.error(f"Failed to fetch video from Stash: status={response.status_code}")
            raise HTTPException(status_code=500, detail="Failed to fetch video from Stash")
        
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
    except Exception as e:
        logger.error(f"Error proxying video stream: {e}")
        raise HTTPException(status_code=500, detail="Failed to proxy video stream")
    finally:
        db.close()

# List shared videos
@app.get("/shared_videos")
async def list_shared_videos(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    try:
        videos = db.query(SharedVideo).all()
        logger.info(f"Retrieved {len(videos)} shared videos")
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
    except Exception as e:
        logger.error(f"Error listing shared videos: {e}")
        raise HTTPException(status_code=500, detail="Failed to list shared videos")
    finally:
        db.close()

# Run Uvicorn server
if __name__ == "__main__":
    uvicorn.run(app, host=KINPEEK_HOST, port=KINPEEK_PORT)
