from flask import Flask, render_template, request, make_response, redirect
from datetime import date, datetime
import json, re, os, sqlite3, secrets, string
from pathlib import Path
from playwright.sync_api import sync_playwright

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "quickcv.db"

app = Flask(__name__)

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS cv_store(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        data_json TEXT NOT NULL,
        template TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def gen_slug(n=7):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))

def safe_get(d, k, default=""): return d.get(k, default) if isinstance(d, dict) else default

def has_content(obj):
    if not isinstance(obj, dict): return False
    return any((obj.get('title'), obj.get('company'), obj.get('qualification'),
                obj.get('institution'), obj.get('summary'), obj.get('details'),
                obj.get('start'), obj.get('end'), obj.get('location'),
                obj.get('highlights')))

def date_range(start, end):
    s = (start or "").strip()
    e = (end or "").strip()
    if s and e: return f"{s} — {e}"
    if s: return s
    if e: return e
    return ""

def as_bullets(items):
    if not items: return ""
    clean = [x for x in items if str(x).strip()]
    if not clean: return ""
    return "<ul class='bullets'>" + "".join(f"<li>{x}</li>" for x in clean) + "</ul>"

def render_experience(items):
    if not items: return ""
    out=[]
    for j in items:
        if not has_content(j): continue
        title = safe_get(j,'title'); company = safe_get(j,'company'); loc = safe_get(j,'location')
        when = date_range(safe_get(j,'start'), safe_get(j,'end'))
        header_parts = [p for p in [title, company] if p]
        header = " — ".join(header_parts) if header_parts else ""
        meta = " · ".join([p for p in [loc, when] if p])
        out.append(
            "<div class='item'>"
            + (f"<div class='item-h'><strong>{header}</strong></div>" if header else "")
            + (f"<div class='item-m'>{meta}</div>" if meta else "")
            + as_bullets(j.get('highlights', []))
            + "</div>"
        )
    return "".join(out)

def render_education(items):
    if not items: return ""
    out=[]
    for ed in items:
        if not has_content(ed): continue
        qual = safe_get(ed,'qualification'); inst = safe_get(ed,'institution')
        when = date_range(safe_get(ed,'start'), safe_get(ed,'end'))
        header_parts = [p for p in [qual, inst] if p]
        header = " — ".join(header_parts) if header_parts else ""
        out.append(
            "<div class='item'>"
            + (f"<div class='item-h'><strong>{header}</strong></div>" if header else "")
            + (f"<div class='item-m'>{when}</div>" if when else "")
            + (f"<p class='item-p'>{safe_get(ed,'details')}</p>" if safe_get(ed,'details') else "")
            + "</div>"
        )
    return "".join(out)

def render_with_placeholders(template_html, keys):
    def repl(m): return str(keys.get(m.group(1), ""))
    return re.sub(r"\[\[(\w+)\]\]", repl, template_html)

def render_cv_html(data, template_html):
    skills_clean = [s.strip() for s in data.get("skills", []) if s.strip()]
    keys = {
        "name": safe_get(data,"name"),
        "role": safe_get(data,"role"),
        "location": safe_get(data,"location"),
        "email": safe_get(data,"email"),
        "phone": safe_get(data,"phone"),
        "website": safe_get(data,"website"),
        "summary": safe_get(data,"summary"),
        "skills": ", ".join(skills_clean),
        "experience_html": render_experience(data.get("experience", [])),
        "education_html": render_education(data.get("education", [])),
        "updated": str(date.today()),
    }
    return render_with_placeholders(template_html, keys)

def build_cover_body(d):
    role = safe_get(d,"role")
    company = safe_get(d,"cover_company")
    jobrole = safe_get(d,"cover_role")
    summary = safe_get(d,"summary")
    skills = d.get("skills", [])
    top_skills = ", ".join(skills[:6]) if isinstance(skills,list) else skills
    intro = f"I am applying for the {jobrole} role at {company}." if jobrole and company else ("I am applying for the role at your company." if jobrole or company else "I am interested in opportunities at your company.")
    p1 = f"{intro} I bring experience as {role} and a track record of delivering results."
    p2 = f"{summary}" if summary else ""
    p3 = f"My key strengths include {top_skills}." if (isinstance(top_skills,str) and top_skills.strip()) else "I'm eager to develop new skills in this role."
    p4 = "I would welcome the chance to discuss how I can contribute."
    return "</p><p>".join([x for x in [p1,p2,p3,p4] if x])

def render_cover_html(data, template_html):
    keys = {
        "name": safe_get(data,"name"),
        "role": safe_get(data,"role"),
        "location": safe_get(data,"location"),
        "email": safe_get(data,"email"),
        "phone": safe_get(data,"phone"),
        "website": safe_get(data,"website"),
        "company": safe_get(data,"cover_company"),
        "jobrole": safe_get(data,"cover_role"),
        "body": build_cover_body(data),
        "date": str(date.today()),
    }
    return render_with_placeholders(template_html, keys)

@app.route("/", methods=["GET"])
def form():
    return render_template("form.html")

def collect_data(form):
    parse_json = lambda f: (json.loads(form.get(f,"")) if form.get(f,"").strip() else [])
    return {
        "name": form.get("name",""),
        "role": form.get("role",""),
        "location": form.get("location",""),
        "email": form.get("email",""),
        "phone": form.get("phone",""),
        "website": form.get("website",""),
        "summary": form.get("summary",""),
        "skills": [s.strip() for s in form.get("skills","").split(",") if s.strip()],
        "experience": parse_json("experience_json"),
        "education": parse_json("education_json"),
        "projects": parse_json("projects_json"),
        "template": form.get("template","classic"),
        "cover_company": form.get("cover_company",""),
        "cover_role": form.get("cover_role",""),
    }

def safe_filename(name_fallback="file"):
    raw = name_fallback or "file"
    import re as _re
    fname = _re.sub(r"[^A-Za-z0-9_-]+","_", raw).strip("_") or "file"
    return fname

@app.route("/generate_pdf", methods=["POST"])
def generate_pdf_download():
    data = collect_data(request.form)
    template_choice = (data.get("template","classic") or "classic").lower()
    template_file = APP_DIR / f"cv_{template_choice}.html"
    if not template_file.exists(): template_file = APP_DIR / "cv_classic.html"
    html = render_cv_html(data, template_file.read_text(encoding="utf-8"))
    fname = safe_filename(data.get("name")) + ".pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        pdf_bytes = page.pdf(format="A4", print_background=True, margin={"top":"12mm","bottom":"12mm","left":"12mm","right":"12mm"})
        browser.close()
    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f"attachment; filename={fname}"
    return resp

@app.route("/generate", methods=["POST"])
def generate_html_download():
    data = collect_data(request.form)
    template_choice = (data.get("template","classic") or "classic").lower()
    template_file = APP_DIR / f"cv_{template_choice}.html"
    if not template_file.exists(): template_file = APP_DIR / "cv_classic.html"
    html = render_cv_html(data, template_file.read_text(encoding="utf-8"))
    fname = safe_filename(data.get("name")) + ".html"
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename={fname}"
    return resp

@app.route("/cover_pdf", methods=["POST"])
def cover_pdf_download():
    data = collect_data(request.form)
    template_choice = (data.get("template","modern") or "modern").lower()
    template_file = APP_DIR / f"cover_{template_choice}.html"
    if not template_file.exists(): template_file = APP_DIR / "cover_modern.html"
    html = render_cover_html(data, template_file.read_text(encoding="utf-8"))
    fname = safe_filename("Cover_Letter_" + safe_get(data,"name")) + ".pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        pdf_bytes = page.pdf(format="A4", print_background=True, margin={"top":"18mm","bottom":"18mm","left":"18mm","right":"18mm"})
        browser.close()
    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f"attachment; filename={fname}"
    return resp

@app.route("/cover_html", methods=["POST"])
def cover_html_download():
    data = collect_data(request.form)
    template_choice = (data.get("template","modern") or "modern").lower()
    template_file = APP_DIR / f"cover_{template_choice}.html"
    if not template_file.exists(): template_file = APP_DIR / "cover_modern.html"
    html = render_cover_html(data, template_file.read_text(encoding="utf-8"))
    fname = safe_filename("Cover_Letter_" + safe_get(data,"name")) + ".html"
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename={fname}"
    return resp

@app.route("/save", methods=["POST"])
def save_share():
    data = collect_data(request.form)
    record = {
        "data_json": json.dumps(data),
        "template": (data.get("template","classic") or "classic").lower(),
        "created_at": datetime.utcnow().isoformat(timespec="seconds")+"Z"
    }
    slug = gen_slug()
    conn = db()
    tries = 0
    while True:
        try:
            conn.execute("INSERT INTO cv_store(slug, data_json, template, created_at) VALUES(?,?,?,?)",
                         (slug, record["data_json"], record["template"], record["created_at"]))
            conn.commit()
            break
        except sqlite3.IntegrityError:
            slug = gen_slug()
            tries += 1
            if tries > 5:
                conn.close()
                return make_response("Error generating link", 500)
    conn.close()
    link_html = f"/v/{slug}"
    link_pdf = f"/p/{slug}.pdf"
    html = f"""
<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Share Link</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px}}
.card{{border:1px solid #eee;border-radius:12px;padding:16px;margin:12px 0}}
.row{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
input.link{{width:100%;padding:10px;border:1px solid #ddd;border-radius:8px}}
button{{padding:10px 14px;border:0;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,.06);cursor:pointer}}
a.btn{{text-decoration:none}}
</style></head>
<body>
<h1>Your shareable links</h1>
<div class='card'>
  <div>Public CV page:</div>
  <div class='row'>
    <input class='link' value='{link_html}' readonly>
    <a class='btn' href='{link_html}'><button>Open</button></a>
  </div>
</div>
<div class='card'>
  <div>Direct PDF:</div>
  <div class='row'>
    <input class='link' value='{link_pdf}' readonly>
    <a class='btn' href='{link_pdf}'><button>Download</button></a>
  </div>
</div>
<div class='card'>
  <a class='btn' href='/'><button>Back to form</button></a>
</div>
</body></html>
"""
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp

@app.route("/v/<slug>", methods=["GET"])
def view_shared(slug):
    conn = db()
    row = conn.execute("SELECT data_json, template FROM cv_store WHERE slug=?", (slug,)).fetchone()
    conn.close()
    if not row:
        return make_response("Not found", 404)
    data = json.loads(row["data_json"])
    template_choice = (row["template"] or "classic").lower()
    template_file = APP_DIR / f"cv_{template_choice}.html"
    if not template_file.exists(): template_file = APP_DIR / "cv_classic.html"
    html = render_cv_html(data, template_file.read_text(encoding="utf-8"))
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp

@app.route("/p/<slug>.pdf", methods=["GET"])
def view_shared_pdf(slug):
    conn = db()
    row = conn.execute("SELECT data_json, template FROM cv_store WHERE slug=?", (slug,)).fetchone()
    conn.close()
    if not row:
        return make_response("Not found", 404)
    data = json.loads(row["data_json"])
    template_choice = (row["template"] or "classic").lower()
    template_file = APP_DIR / f"cv_{template_choice}.html"
    if not template_file.exists(): template_file = APP_DIR / "cv_classic.html"
    html = render_cv_html(data, template_file.read_text(encoding="utf-8"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        pdf_bytes = page.pdf(format="A4", print_background=True, margin={"top":"12mm","bottom":"12mm","left":"12mm","right":"12mm"})
        browser.close()
    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f"inline; filename={safe_filename('CV')}.pdf"
    return resp

def analyze(data):
    score = 0
    tips = []
    name_ok = bool(data.get("name"))
    email_ok = bool(re.search(r".+@.+\..+", data.get("email","")))
    phone_ok = bool(re.search(r"\d", data.get("phone","")))
    score += 5 if name_ok else 0
    score += 5 if email_ok else 0
    score += 5 if phone_ok else 0
    s = (data.get("summary","") or "").strip()
    sl = len(s)
    if 120 <= sl <= 400: score += 15
    elif 60 <= sl < 120 or 400 < sl <= 700: score += 8; tips.append("Tighten your profile summary to about 2–4 lines.")
    else: tips.append("Write a concise 2–4 line profile summary.")
    skills = [x for x in data.get("skills",[]) if x]
    sc = len(skills)
    if sc >= 8: score += 12
    elif 5 <= sc < 8: score += 8
    elif 1 <= sc < 5: score += 4; tips.append("Add more relevant skills (aim for 8–12).")
    else: tips.append("List key skills to quickly show your strengths.")
    exp = data.get("experience",[]) or []
    if len(exp) >= 1: score += 15
    else: tips.append("Add at least one experience entry, even volunteer or projects.")
    bullets_total = 0
    bullet_words_good = 0
    action_hits = 0
    action_verbs = set(["led","built","created","designed","implemented","launched","increased","reduced","improved","optimized","managed","developed","delivered","owned","drove","resolved","automated","collaborated","analyzed","architected"])
    date_ok = 0
    for e in exp:
        hs = e.get("highlights",[]) or []
        bullets_total += len(hs)
        for h in hs:
            words = len(h.split())
            if 8 <= words <= 24: bullet_words_good += 1
            if re.match(r"(?i)("+ "|".join(action_verbs) + r")\b", h.strip()): action_hits += 1
        if e.get("start") or e.get("end"):
            if re.match(r"^\d{4}(-\d{2})?$", (e.get("start") or "")) or re.match(r"^\d{4}$", (e.get("start") or "")): date_ok += 1
            if re.match(r"^\d{4}(-\d{2})?$", (e.get("end") or "")) or re.match(r"^\d{4}$", (e.get("end") or "")): date_ok += 1
    if bullets_total >= 4: score += 8
    elif 1 <= bullets_total < 4: score += 4; tips.append("Add more bullet achievements under experience.")
    else: tips.append("Add bullet points with achievements under experience.")
    if bullets_total > 0:
        ratio = bullet_words_good / max(1, bullets_total)
        if ratio >= 0.6: score += 8
        else: tips.append("Keep bullet points concise (8–24 words).")
    if action_hits >= max(1, bullets_total//2): score += 8
    else: tips.append("Start bullets with strong verbs (Built, Led, Improved).")
    if date_ok >= max(1, len(exp)): score += 4
    else: tips.append("Use consistent dates like 2023-06 or 2023.")
    edu = data.get("education",[]) or []
    if len(edu) >= 1: score += 8
    else: tips.append("Add your education or courses.")
    website = data.get("website","").strip()
    if website: score += 4
    else: tips.append("Add a portfolio or LinkedIn URL.")
    score = max(0, min(100, score))
    rating = "Outstanding" if score >= 85 else ("Strong" if score >= 70 else ("OK" if score >= 55 else "Needs improvement"))
    return score, rating, tips

@app.route("/analyze", methods=["POST"])
def analyze_route():
    data = collect_data(request.form)
    score, rating, tips = analyze(data)
    html = f"""
<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>CV Rating</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px}}
.card{{border:1px solid #eee;border-radius:12px;padding:16px;margin:12px 0}}
.big{{font-size:42px;font-weight:800;line-height:1}}
.bar{{height:10px;border-radius:6px;background:#f2f2f2;overflow:hidden;margin-top:10px}}
.fill{{height:100%;width:{score}%;background:linear-gradient(90deg,#4caf50,#2196f3)}}
.tag{{display:inline-block;padding:6px 10px;border-radius:999px;background:#eef3ff;color:#1f6feb;font-weight:700;margin-top:8px}}
ul{{margin:8px 0 0 18px}}
button{{padding:10px 14px;border:0;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,.06);cursor:pointer}}
a.btn{{display:inline-block;text-decoration:none;margin-right:8px}}
</style></head>
<body>
<h1>CV Rating</h1>
<div class='card'>
  <div class='big'>{score}/100</div>
  <div class='tag'>{rating}</div>
  <div class='bar'><div class='fill'></div></div>
</div>
<div class='card'>
  <strong>Quick wins</strong>
  <ul>{"".join(f"<li>{t}</li>" for t in tips[:8]) or "<li>Looks solid.</li>"}</ul>
</div>
<div class='card'>
  <a class='btn' href='/'><button>Back to form</button></a>
</div>
</body></html>
"""
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp

if __name__ == "__main__":
    init_db()
    import sys
    host = "127.0.0.1"; port = 5001
    if "--host=0.0.0.0" in sys.argv: host = "0.0.0.0"
    app.run(debug=True, host=host, port=port)
