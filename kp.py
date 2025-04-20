# sexyproxy.py  –  100 % self‑contained

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import (
    StreamingResponse, HTMLResponse,
    RedirectResponse, JSONResponse
)
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import yaml, uuid, httpx, logging, textwrap

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sexyproxy")

# ───────────────────────── helpers ──────────────────────────
def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def parse_exp(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

HLS_HEADERS = {
    "Cache-Control": "public, max-age=0, s-maxage=86400, immutable"
}

def forward_range(req: Request) -> dict:
    out = {}
    for h in ("range", "if-range", "if-modified-since", "if-none-match"):
        if h in req.headers:
            out[h] = req.headers[h]
    return out

async def jellyfin_media_source(item_id: str, client: httpx.AsyncClient, api_key: str, base: str) -> str:
    """Return the first MediaSourceId for a given item."""
    url = f"{base}/Items/{item_id}?api_key={api_key}"
    r = await client.get(url)
    r.raise_for_status()
    return r.json()["MediaSources"][0]["Id"]

# ───────────────────────── config ──────────────────────────
def load_cfg() -> dict:
    p = Path("config.yaml")
    if not p.exists():
        raise FileNotFoundError("config.yaml missing")
    return yaml.safe_load(p.read_text())

_cfg = load_cfg()
JELLYFIN_URL  = _cfg["jellyfin"]["url"].rstrip("/")
API_KEY       = _cfg["jellyfin"]["api_key"]
USER_ID       = _cfg["jellyfin"]["user_id"]
STASH_URL     = _cfg["stash"]["url"].rstrip("/")
STASH_API_KEY = _cfg["stash"]["api_key"]
PROXY_HOST    = _cfg["proxy"]["host"]
PROXY_PORT    = _cfg["proxy"]["port"]

# ───────────────────────── storage ─────────────────────────
SHARES_FILE = Path("shares.yaml")
def load_shares() -> dict:
    if not SHARES_FILE.exists():
        return {"shares": {}}
    return yaml.safe_load(SHARES_FILE.read_text()) or {"shares": {}}
def save_shares(d: dict):
    SHARES_FILE.write_text(yaml.safe_dump(d))

playlist_items: Dict[str, List[dict]] = {}

# ───────────────────────── FastAPI ─────────────────────────
app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/shares", 302)

# ───────────────────────── models ──────────────────────────
class ShareData(BaseModel):
    source: str
    item_id: Optional[str] = None
    media_source_id: Optional[str] = None   # ← NEW
    scene_id: Optional[str] = None
    name: str
    expires: str
    max_views: Optional[int] = None
    views: int = 0
    allowed_ips: List[str] = []

class AddShareRequest(BaseModel):
    source: str
    item_id: Optional[str] = None
    media_source_id: Optional[str] = None
    scene_id: Optional[str] = None
    name: str
    expires: str
    max_views: Optional[int] = None
    allowed_ips: List[str] = []

# ───────────────────────── playlist helper ─────────────────
async def generate_playlist_data(plid: str) -> Tuple[str, int]:
    url = f"{JELLYFIN_URL}/Users/{USER_ID}/Items?PlaylistId={plid}&api_key={API_KEY}"
    async with httpx.AsyncClient() as c:
        r = await c.get(url)
    if r.status_code != 200:
        return f"Jellyfin {r.status_code}", 502

    data = r.json()
    shares = load_shares(); shares.setdefault("shares", {})
    playlist_items[plid] = []

    async with httpx.AsyncClient() as c:
        for it in data.get("Items", []):
            msrc = await jellyfin_media_source(it["Id"], c, API_KEY, JELLYFIN_URL)
            obf  = str(uuid.uuid4())
            hurl = f"/hls/{obf}/master.m3u8"
            exp  = (utc_now() + timedelta(days=7)).isoformat()
            shares["shares"][obf] = {
                "source": "jellyfin",
                "item_id": it["Id"],
                "media_source_id": msrc,
                "name": it["Name"],
                "expires": exp,
                "max_views": None,
                "views": 0,
                "allowed_ips": []
            }
            playlist_items[plid].append({
                "name": it["Name"],
                "url":  hurl,
                "type": "application/x-mpegURL"
            })

    save_shares(shares)
    return "OK", 200

# ───────────────────────── HLS master ──────────────────────
@app.get("/hls/{obf}/master.m3u8")
async def hls_master(obf: str, request: Request):
    shares = load_shares()["shares"]
    if obf not in shares:
        raise HTTPException(404)
    sd = ShareData(**shares[obf])

    if utc_now() > parse_exp(sd.expires):
        del shares[obf]; save_shares({"shares": shares}); raise HTTPException(410)
    if sd.max_views and sd.views >= sd.max_views:
        del shares[obf]; save_shares({"shares": shares}); raise HTTPException(410)
    if sd.allowed_ips and request.client.host not in sd.allowed_ips:
        raise HTTPException(403)

    sd.views += 1; shares[obf]["views"] = sd.views; save_shares({"shares": shares})

    j_url = (f"{JELLYFIN_URL}/Videos/{sd.item_id}/master.m3u8"
             f"?api_key={API_KEY}&MediaSourceId={sd.media_source_id}")
    async with httpx.AsyncClient() as c:
        r = await c.get(j_url)
    if r.status_code != 200:
        snippet = textwrap.shorten((await r.aread()).decode('utf‑8','ignore'), 300)
        log.error("Jellyfin %s → %s\n%s", j_url, r.status_code, snippet)
        raise HTTPException(r.status_code, f"origin {r.status_code}")

    body = r.text.replace(JELLYFIN_URL, f"/hls/{obf}")
    return StreamingResponse(iter([body]),
                             media_type="application/x-mpegURL",
                             headers=HLS_HEADERS)

# ───────────────────────── HLS segment ─────────────────────
@app.get("/hls/{obf}/{seg:path}")
async def hls_segment(obf: str, seg: str, request: Request):
    shares = load_shares()["shares"]
    if obf not in shares:
        raise HTTPException(404)
    sd = ShareData(**shares[obf])

    if utc_now() > parse_exp(sd.expires):
        del shares[obf]; save_shares({"shares": shares}); raise HTTPException(410)
    if sd.max_views and sd.views >= sd.max_views:
        del shares[obf]; save_shares({"shares": shares}); raise HTTPException(410)
    if sd.allowed_ips and request.client.host not in sd.allowed_ips:
        raise HTTPException(403)

    origin = (f"{JELLYFIN_URL}/Videos/{sd.item_id}/{seg}"
              f"?api_key={API_KEY}&MediaSourceId={sd.media_source_id}")
    if request.url.query:
        origin += "&" + request.url.query

    headers = forward_range(request)
    client  = httpx.AsyncClient()
    try:
        resp = await client.get(origin, headers=headers, stream=True)
    except Exception as e:
        await client.aclose(); raise HTTPException(502, str(e))

    async def gen():
        async for chunk in resp.aiter_bytes(): yield chunk
        await client.aclose()

    hdr = {**HLS_HEADERS}
    for k in ("content-length", "content-range", "accept-ranges"):
        if k in resp.headers: hdr[k] = resp.headers[k]
    hdr.setdefault("Accept-Ranges", "bytes")

    return StreamingResponse(gen(), status_code=resp.status_code,
                             media_type=resp.headers.get("content-type","video/MP2T"),
                             headers=hdr)

# ───────────────────────── Direct MP4 (Stash) ──────────────
@app.get("/stream/{obf}")
async def stash_stream(obf: str, request: Request):
    shares = load_shares()["shares"]
    if obf not in shares:
        raise HTTPException(404)
    sd = ShareData(**shares[obf])
    if sd.source != "stash":
        raise HTTPException(400)

    if utc_now() > parse_exp(sd.expires):
        del shares[obf]; save_shares({"shares": shares}); raise HTTPException(410)
    if sd.max_views and sd.views >= sd.max_views:
        del shares[obf]; save_shares({"shares": shares}); raise HTTPException(410)
    if sd.allowed_ips and request.client.host not in sd.allowed_ips:
        raise HTTPException(403)

    sd.views += 1; shares[obf]["views"] = sd.views; save_shares({"shares": shares})

    origin = f"{STASH_URL}/scene/{sd.scene_id}/stream?apikey={STASH_API_KEY}"
    headers = forward_range(request)
    client  = httpx.AsyncClient()
    try:
        resp = await client.get(origin, headers=headers, stream=True, follow_redirects=True)
    except Exception as e:
        await client.aclose(); raise HTTPException(502, str(e))
    if resp.status_code >= 400:
        snippet = textwrap.shorten((await resp.aread()).decode('utf‑8','ignore'), 300)
        log.error("Stash %s → %s\n%s", origin, resp.status_code, snippet)
        await client.aclose(); raise HTTPException(resp.status_code)

    async def gen():
        async for chunk in resp.aiter_bytes(): yield chunk
        await client.aclose()

    h = {k: resp.headers[k]
         for k in ("content-length", "content-range", "accept-ranges", "content-type")
         if k in resp.headers}
    h.setdefault("Accept-Ranges", "bytes")
    h.setdefault("Cache-Control", "public, max-age=0, s-maxage=86400")

    return StreamingResponse(gen(), status_code=resp.status_code,
                             media_type=h.pop("content-type","video/mp4"), headers=h)

# ───────────────────────── GUI routes ───────────────────────
@app.get("/playlist/{playlist_id}", response_class=HTMLResponse)
async def playlist_gui(request: Request, playlist_id: str):
    if playlist_id not in playlist_items:
        msg, st = await generate_playlist_data(playlist_id)
        if st != 200:
            raise HTTPException(st, msg)
    return templates.TemplateResponse("index.html",
        {"request": request, "items": playlist_items[playlist_id]})

@app.get("/shares", response_class=HTMLResponse)
async def shares_gui(request: Request):
    data = load_shares()["shares"]
    items=[]
    for obf,s in data.items():
        if s["source"]=="jellyfin":
            url,typ=f"/hls/{obf}/master.m3u8","application/x-mpegURL"
        else:
            url,typ=f"/stream/{obf}","video/mp4"
        items.append({"name":s["name"],"url":url,"type":typ})
    return templates.TemplateResponse("index.html",{"request":request,"items":items})

# ───────────────────────── Share form ───────────────────────
@app.get("/shares/new", response_class=HTMLResponse)
async def new_share_form(request: Request):
    return templates.TemplateResponse("new_share.html", {"request": request})

@app.post("/shares/new")
async def create_share(
    source:str = Form(...),
    item_id:str = Form(""),
    scene_id:str = Form(""),
    name:str = Form(...),
    expiration:str = Form(""),
    max_views:str = Form(""),
    allowed_ips:str = Form("")
):
    if source not in ("jellyfin","stash"): raise HTTPException(400)
    if source=="jellyfin" and not item_id.strip(): raise HTTPException(400,"item id")
    if source=="stash"   and not scene_id.strip(): raise HTTPException(400,"scene id")

    exp_dt = parse_exp(expiration) if expiration.strip() else utc_now()+timedelta(days=7)
    mv = int(max_views) if max_views.strip().isdigit() and int(max_views)>0 else None
    ips=[ip.strip() for ip in allowed_ips.split(",") if ip.strip()]

    ms_id = None
    if source=="jellyfin":
        async with httpx.AsyncClient() as c:
            ms_id = await jellyfin_media_source(item_id.strip(), c, API_KEY, JELLYFIN_URL)

    obf=str(uuid.uuid4())
    entry={"source":source,"name":name.strip(),"expires":exp_dt.isoformat(),
           "views":0,"allowed_ips":ips}
    if mv: entry["max_views"]=mv
    if source=="jellyfin":
        entry.update({"item_id":item_id.strip(),"media_source_id":ms_id})
    else:
        entry["scene_id"]=scene_id.strip()

    d=load_shares(); d.setdefault("shares",{})[obf]=entry; save_shares(d)
    return RedirectResponse("/shares",303)

# ───────────────────────── JSON add/remove ──────────────────
@app.post("/shares/add")
async def add_share_api(r: AddShareRequest):
    d=load_shares(); d.setdefault("shares",{})
    if r.source=="jellyfin" and not r.media_source_id:
        async with httpx.AsyncClient() as c:
            msrc=await jellyfin_media_source(r.item_id, c, API_KEY, JELLYFIN_URL)
        r.media_source_id = msrc
    obf=str(uuid.uuid4()); d["shares"][obf]=r.dict(); save_shares(d)
    return {"obfuscated_id":obf}

@app.delete("/shares/{obf}")
async def del_share(obf:str):
    d=load_shares()
    if obf not in d.get("shares",{}): raise HTTPException(404)
    del d["shares"][obf]; save_shares(d); return {"message":"removed"}

# ───────────────────────── M3U generator ────────────────────
@app.get("/generate_m3u/{playlist_id}")
async def gen_m3u(playlist_id:str):
    if playlist_id not in playlist_items:
        msg,st=await generate_playlist_data(playlist_id)
        if st!=200: raise HTTPException(st,msg)
    out="#EXTM3U\n"
    for it in playlist_items[playlist_id]:
        out+=f"#EXTINF:-1,{it['name']}\n{it['url']}\n"
    Path("public_playlist.m3u").write_text(out)
    return {"message":"public_playlist.m3u created"}

# ───────────────────────── Run ──────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=PROXY_HOST, port=PROXY_PORT,
                proxy_headers=True, forwarded_allow_ips="*")
