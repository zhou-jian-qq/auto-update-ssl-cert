from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware

from .certs import remaining_days
from .config import settings
from .db import get_db, init_db
from .scheduler import start_scheduler
from .services import (
    check_bank,
    confirm_certificate,
    create_bank,
    dashboard_stats,
    import_uploaded_certificate,
    record_download,
    update_bank,
)

app = FastAPI(title=settings.app_name)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def require_user(request: Request) -> str:
    username = request.session.get("user")
    if not username:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return username


@app.on_event("startup")
def startup() -> None:
    init_db()
    start_scheduler()


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "settings": settings})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == settings.admin_username and password == settings.admin_password:
        request.session["user"] = username
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "settings": settings, "error": "用户名或密码错误"},
        status_code=401,
    )


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: str = Depends(require_user)):
    stats = dashboard_stats()
    return templates.TemplateResponse("dashboard.html", {"request": request, "settings": settings, "user": user, **stats})


@app.get("/banks/new", response_class=HTMLResponse)
def new_bank_page(request: Request, user: str = Depends(require_user)):
    return templates.TemplateResponse("bank_form.html", {"request": request, "settings": settings, "user": user, "bank": None})


@app.post("/banks")
def add_bank(
    request: Request,
    user: str = Depends(require_user),
    name: str = Form(...),
    code: str = Form(...),
    host: str = Form(...),
    port: int = Form(443),
    threshold_days: int = Form(30),
    website_url: str = Form(""),
    notes: str = Form(""),
    enabled: str | None = Form(None),
):
    bank_id = create_bank(
        {
            "name": name,
            "code": code,
            "host": host,
            "port": port,
            "threshold_days": threshold_days,
            "website_url": website_url,
            "notes": notes,
            "enabled": enabled == "on",
        }
    )
    return RedirectResponse(f"/banks/{bank_id}", status_code=303)


@app.get("/banks/{bank_id}", response_class=HTMLResponse)
def bank_detail(request: Request, bank_id: int, user: str = Depends(require_user)):
    with get_db() as conn:
        bank = conn.execute("SELECT * FROM banks WHERE id = ?", (bank_id,)).fetchone()
        if not bank:
            raise HTTPException(404, "银行配置不存在")
        certs = conn.execute("SELECT * FROM certificates WHERE bank_id = ? ORDER BY created_at DESC", (bank_id,)).fetchall()
        logs = conn.execute("SELECT * FROM check_logs WHERE bank_id = ? ORDER BY checked_at DESC LIMIT 30", (bank_id,)).fetchall()
        notices = conn.execute("SELECT * FROM notifications WHERE bank_id = ? ORDER BY sent_at DESC LIMIT 20", (bank_id,)).fetchall()
        downloads = conn.execute(
            """
            SELECT d.*, c.sha256_fingerprint FROM downloads d
            JOIN certificates c ON c.id = d.certificate_id
            WHERE c.bank_id = ?
            ORDER BY d.downloaded_at DESC LIMIT 20
            """,
            (bank_id,),
        ).fetchall()
    enriched = []
    for cert in certs:
        item = dict(cert)
        item["days_left"] = remaining_days(cert["not_after"])
        enriched.append(item)
    return templates.TemplateResponse(
        "bank_detail.html",
        {
            "request": request,
            "settings": settings,
            "user": user,
            "bank": bank,
            "certs": enriched,
            "logs": logs,
            "notices": notices,
            "downloads": downloads,
        },
    )


@app.get("/banks/{bank_id}/edit", response_class=HTMLResponse)
def edit_bank_page(request: Request, bank_id: int, user: str = Depends(require_user)):
    with get_db() as conn:
        bank = conn.execute("SELECT * FROM banks WHERE id = ?", (bank_id,)).fetchone()
    if not bank:
        raise HTTPException(404, "银行配置不存在")
    return templates.TemplateResponse("bank_form.html", {"request": request, "settings": settings, "user": user, "bank": bank})


@app.post("/banks/{bank_id}")
def edit_bank(
    bank_id: int,
    user: str = Depends(require_user),
    name: str = Form(...),
    code: str = Form(...),
    host: str = Form(...),
    port: int = Form(443),
    threshold_days: int = Form(30),
    website_url: str = Form(""),
    notes: str = Form(""),
    enabled: str | None = Form(None),
):
    update_bank(
        bank_id,
        {
            "name": name,
            "code": code,
            "host": host,
            "port": port,
            "threshold_days": threshold_days,
            "website_url": website_url,
            "notes": notes,
            "enabled": enabled == "on",
        },
    )
    return RedirectResponse(f"/banks/{bank_id}", status_code=303)


@app.post("/banks/{bank_id}/check")
def manual_check(bank_id: int, user: str = Depends(require_user)):
    check_bank(bank_id)
    return RedirectResponse(f"/banks/{bank_id}", status_code=303)


@app.post("/banks/{bank_id}/upload")
async def upload_cert(bank_id: int, user: str = Depends(require_user), cert_file: UploadFile = File(...)):
    content = await cert_file.read()
    try:
        text = content.decode("utf-8")
        import_uploaded_certificate(bank_id, text)
    except Exception as exc:
        raise HTTPException(400, f"证书解析失败：{exc}") from exc
    return RedirectResponse(f"/banks/{bank_id}", status_code=303)


@app.post("/certificates/{cert_id}/confirm")
def confirm_cert(cert_id: int, user: str = Depends(require_user)):
    confirm_certificate(cert_id, user)
    with get_db() as conn:
        cert = conn.execute("SELECT bank_id FROM certificates WHERE id = ?", (cert_id,)).fetchone()
    return RedirectResponse(f"/banks/{cert['bank_id']}", status_code=303)


@app.get("/certificates/{cert_id}/download")
def download_cert(cert_id: int, user: str = Depends(require_user)):
    with get_db() as conn:
        cert = conn.execute("SELECT * FROM certificates WHERE id = ?", (cert_id,)).fetchone()
    if not cert:
        raise HTTPException(404, "证书不存在")
    path = Path(cert["pem_path"])
    if not path.exists():
        raise HTTPException(404, "证书文件不存在")
    record_download(cert_id, user)
    return FileResponse(path, media_type="application/x-x509-ca-cert", filename=path.name)
