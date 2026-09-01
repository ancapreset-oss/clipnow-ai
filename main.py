import os, uuid, json, subprocess, shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlmodel import SQLModel, Field, Session, create_engine, select

BASE=Path(__file__).resolve().parent
ST=BASE/"storage"; VIDEOS=ST/"videos"; CLIPS=ST/"clips"; SUBS=ST/"subs"
for p in (VIDEOS,CLIPS,SUBS): p.mkdir(parents=True,exist_ok=True)
engine=create_engine(f"sqlite:///{BASE/'clipnow.db'}",connect_args={"check_same_thread":False})

class Project(SQLModel,table=True):
    id:str=Field(primary_key=True); name:str; source_path:str; status:str="queued"; progress:int=0
    duration:float=0; created_at:datetime=Field(default_factory=datetime.utcnow); error:Optional[str]=None
class Clip(SQLModel,table=True):
    id:str=Field(primary_key=True); project_id:str; title:str; start:float; end:float; viral_score:int
    subtitle_style:str="viral"; path:str=""; subtitle_path:str=""
SQLModel.metadata.create_all(engine)

app=FastAPI(title="ClipNow AI")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

def probe(p):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(p)],capture_output=True,text=True)
    return float(r.stdout.strip() or 0)
def transcribe(p):
    try:
        from faster_whisper import WhisperModel
        model=WhisperModel(os.getenv("WHISPER_MODEL","small"),device="cpu",compute_type="int8")
        segs,_=model.transcribe(str(p),vad_filter=True)
        return [{"start":s.start,"end":s.end,"text":s.text.strip()} for s in segs]
    except Exception:
        return []
def srt_for_segments(segs,start,end):
    out=[]; n=1
    for s in segs:
        if s["end"]<start or s["start"]>end: continue
        a=max(start,s["start"])-start; b=min(end,s["end"])-start
        def tc(x):
            ms=int((x-int(x))*1000); sec=int(x)%60; mins=int(x//60)%60; hrs=int(x//3600)
            return f"{hrs:02}:{mins:02}:{sec:02},{ms:03}"
        out += [str(n),f"{tc(a)} --> {tc(b)}",s["text"],""]; n+=1
    return "\n".join(out)
def moments(segs,dur):
    if not dur: return []
    candidates=[]
    words=("cara","tips","penting","ternyata","jangan","rahasia","wow","kenapa","how","why","secret","mistake","best")
    for s in segs:
        text=s["text"]; score=68+min(25,sum(w in text.lower() for w in words)*5)
        if len(text)>70: score+=4
        st=max(0,s["start"]-3); en=min(dur,st+30)
        candidates.append((min(99,score),st,en,text[:70]))
    candidates.sort(reverse=True)
    picked=[]
    for score,st,en,title in candidates:
        if all(abs(st-x["start"])>15 for x in picked):
            picked.append({"score":score,"start":st,"end":en,"title":title or "Best Moment"})
        if len(picked)>=3: break
    if not picked:
        L=min(30,dur)
        starts=[0,max(0,dur/2-L/2),max(0,dur-L)]
        picked=[{"score":s,"start":st,"end":min(dur,st+L),"title":f"Viral Moment {i+1}"} for i,(s,st) in enumerate(zip((92,88,85),starts))]
    return picked
def render(src,out,start,end,aspect,srt=None):
    if aspect=="16:9": vf="scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
    elif aspect=="1:1": vf="scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
    else: vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    cmd=["ffmpeg","-y","-ss",str(start),"-i",str(src),"-t",str(max(1,end-start)),"-vf",vf]
    if srt and Path(srt).exists():
        # Subtitle burn-in uses libass; escape path for filter syntax.
        sp=str(Path(srt).resolve()).replace("\\","/").replace(":","\\:")
        cmd[-1]=vf+",subtitles='"+sp+"'"
    cmd += ["-c:v","libx264","-preset","veryfast","-c:a","aac","-movflags","+faststart",str(out)]
    subprocess.run(cmd,check=True,capture_output=True)
def process(pid,aspect,style):
    with Session(engine) as db:
        p=db.get(Project,pid)
        try:
            p.status="analyzing";p.progress=10;db.add(p);db.commit()
            p.duration=probe(Path(p.source_path));db.add(p);db.commit()
            p.status="transcribing";p.progress=30;db.add(p);db.commit()
            segs=transcribe(Path(p.source_path))
            p.status="finding_moments";p.progress=50;db.add(p);db.commit()
            for m in moments(segs,p.duration):
                cid=str(uuid.uuid4()); srt=SUBS/f"{cid}.srt"
                srt.write_text(srt_for_segments(segs,m["start"],m["end"]),encoding="utf8")
                out=CLIPS/f"{cid}.mp4"
                render(Path(p.source_path),out,m["start"],m["end"],aspect,srt)
                db.add(Clip(id=cid,project_id=pid,title=m["title"],start=m["start"],end=m["end"],viral_score=m["score"],subtitle_style=style,path=str(out),subtitle_path=str(srt)))
            p.status="completed";p.progress=100;db.add(p);db.commit()
        except Exception as e:
            p.status="failed";p.error=str(e);db.add(p);db.commit()

@app.get("/api/health")
def health(): return {"ok":True,"service":"ClipNow AI"}
@app.post("/api/projects")
async def create(background_tasks:BackgroundTasks,file:UploadFile=File(...),aspect:str=Form("9:16"),subtitle_style:str=Form("viral")):
    ext=Path(file.filename or "").suffix.lower()
    if ext not in {".mp4",".mov",".webm"}: raise HTTPException(400,"Format harus MP4, MOV, atau WEBM")
    pid=str(uuid.uuid4()); path=VIDEOS/f"{pid}{ext}"
    with path.open("wb") as f:
        while chunk:=await file.read(1024*1024): f.write(chunk)
    with Session(engine) as db:
        db.add(Project(id=pid,name=file.filename or "Video",source_path=str(path)));db.commit()
    background_tasks.add_task(process,pid,aspect,subtitle_style)
    return {"id":pid}
@app.get("/api/projects")
def projects():
    with Session(engine) as db:return db.exec(select(Project).order_by(Project.created_at.desc())).all()
@app.get("/api/projects/{pid}")
def project(pid:str):
    with Session(engine) as db:
        p=db.get(Project,pid)
        if not p: raise HTTPException(404,"Not found")
        return {"project":p,"clips":db.exec(select(Clip).where(Clip.project_id==pid)).all()}
@app.get("/api/clips/{cid}/download")
def download(cid:str):
    with Session(engine) as db:
        c=db.get(Clip,cid)
        if not c or not Path(c.path).exists(): raise HTTPException(404,"Clip not found")
        return FileResponse(c.path,media_type="video/mp4",filename=f"ClipNow-{c.id}.mp4")
