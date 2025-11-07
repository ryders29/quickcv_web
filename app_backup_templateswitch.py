from flask import Flask, render_template, request, make_response
from datetime import date
import json, re
from pathlib import Path
from playwright.sync_api import sync_playwright

APP_DIR = Path(__file__).parent
TEMPLATE_PATH = APP_DIR / "cv_template.html"
app = Flask(__name__)

def safe_get(d, k, default=""): return d.get(k, default) if isinstance(d, dict) else default
def as_bullets(items):
    if not items: return ""
    return "<ul>\n" + "\n".join(f"<li>{x}</li>" for x in items) + "\n</ul>"

def render_experience(items):
    if not items: return "<p>—</p>"
    out=[]
    for j in items:
        out.append(f"""
        <div class="exp">
          <div class="row">
            <div><span class="job-title">{safe_get(j,"title")}</span> · <span class="company">{safe_get(j,"company")}</span></div>
            <div class="meta">{safe_get(j,"location")} · {safe_get(j,"start")} — {safe_get(j,"end")}</div>
          </div>
          {as_bullets(j.get("highlights", []))}
        </div>
        """)
    return "\n".join(out)

def render_education(items):
    if not items: return "<p>—</p>"
    out=[]
    for ed in items:
        out.append(f"""
        <div class="edu">
          <div class="row">
            <div><strong>{safe_get(ed,"qualification")}</strong> — {safe_get(ed,"institution")}</div>
            <div class="meta">{safe_get(ed,"start")} — {safe_get(ed,"end")}</div>
          </div>
          <p>{safe_get(ed,"details")}</p>
        </div>
        """)
    return "\n".join(out)

def render_badges(items): return "" if not items else " ".join(f"<span>{x}</span>" for x in items)
def render_projects(items):
    if not items: return ""
    cards=[]
    for p in items:
        name=safe_get(p,"name"); link=safe_get(p,"link"); summary=safe_get(p,"summary")
        a1=f"<a href='{link}'>" if link else ""; a2="</a>" if link else ""
        cards.append(f"<li><strong>{a1}{name}{a2}</strong> — {summary}</li>")
    return "<section><h2>Projects</h2><ul>" + "\n".join(cards) + "</ul></section>"

def render_block(title, items):
    if not items: return ""
    return f"<section><h2>{title}</h2><ul>" + "\n".join(f"<li>{x}</li>" for x in items) + "</ul></section>"

def render_html(data, template_html):
    keys = {
        "name": safe_get(data,"name"),
        "role": safe_get(data,"role"),
        "location": safe_get(data,"location"),
        "email": safe_get(data,"email"),
        "phone": safe_get(data,"phone"),
        "website": safe_get(data,"website"),
        "summary": safe_get(data,"summary"),
        "skills_html": render_badges(data.get("skills",[])),
        "experience_html": render_experience(data.get("experience",[])),
        "education_html": render_education(data.get("education",[])),
        "projects_block": render_projects(data.get("projects",[])),
        "certs_block": render_block("Certifications", data.get("certs",[])),
        "awards_block": render_block("Awards", data.get("awards",[])),
        "updated": safe_get(data,"updated", str(date.today())),
    }
    return template_html.format(**keys)

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
        "certs": [s.strip() for s in form.get("certs","").split(",") if s.strip()],
        "awards": [s.strip() for s in form.get("awards","").split(",") if s.strip()],
    }

def safe_filename(name_fallback="cv"):
    raw = name_fallback or "cv"
    fname = re.sub(r"[^A-Za-z0-9_-]+","_", raw).strip("_") or "cv"
    return fname

@app.route("/generate", methods=["POST"])
def generate_html_download():
    data = collect_data(request.form)
    template_html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = render_html(data, template_html)
    fname = safe_filename(data.get("name"))
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename={fname}.html"
    return resp

@app.route("/generate_pdf", methods=["POST"])
def generate_pdf_download():
    data = collect_data(request.form)
    template_html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = render_html(data, template_html)
    fname = safe_filename(data.get("name")) + ".pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        pdf_bytes = page.pdf(format="A4", print_background=True)
        browser.close()
    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f"attachment; filename={fname}"
    return resp

if __name__ == "__main__":
    app.run(debug=True, port=5001)
