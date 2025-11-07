from flask import Flask, render_template, request, make_response
from datetime import date
import json, re
from pathlib import Path
from playwright.sync_api import sync_playwright

APP_DIR = Path(__file__).parent
app = Flask(__name__)

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
        title = safe_get(j,'title')
        company = safe_get(j,'company')
        loc = safe_get(j,'location')
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
    html = "".join(out)
    return html

def render_education(items):
    if not items: return ""
    out=[]
    for ed in items:
        if not has_content(ed): continue
        qual = safe_get(ed,'qualification')
        inst = safe_get(ed,'institution')
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
    html = "".join(out)
    return html

def render_with_placeholders(template_html, keys):
    def repl(m): return str(keys.get(m.group(1), ""))
    return re.sub(r"\[\[(\w+)\]\]", repl, template_html)

def render_html(data, template_html):
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
        "template": form.get("template","classic"),
    }

def safe_filename(name_fallback="cv"):
    raw = name_fallback or "cv"
    fname = re.sub(r"[^A-Za-z0-9_-]+","_", raw).strip("_") or "cv"
    return fname

from flask import make_response
from playwright.sync_api import sync_playwright

@app.route("/generate_pdf", methods=["POST"])
def generate_pdf_download():
    data = collect_data(request.form)
    template_file = (APP_DIR / f"cv_{data.get('template','classic').lower()}.html")
    if not template_file.exists(): template_file = APP_DIR / "cv_classic.html"
    html = render_html(data, template_file.read_text(encoding="utf-8"))
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
    template_file = (APP_DIR / f"cv_{data.get('template','classic').lower()}.html")
    if not template_file.exists(): template_file = APP_DIR / "cv_classic.html"
    html = render_html(data, template_file.read_text(encoding="utf-8"))
    fname = safe_filename(data.get("name")) + ".html"
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename={fname}"
    return resp

if __name__ == "__main__":
    app.run(debug=True, port=5001)
