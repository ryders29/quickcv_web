
from flask import Flask, render_template, request, make_response, redirect, url_for
from datetime import date
import json
from pathlib import Path

APP_DIR = Path(__file__).parent
TEMPLATE_PATH = APP_DIR / "cv_template.html"

app = Flask(__name__)

def safe_get(d, key, default=""):
    return d.get(key, default) if isinstance(d, dict) else default

def as_bullets(items):
    if not items:
        return ""
    lis = "\n".join(f"<li>{x}</li>" for x in items)
    return f"<ul>\n{lis}\n</ul>"

def render_experience(items):
    if not items:
        return "<p>—</p>"
    out = []
    for job in items:
        title = safe_get(job, "title")
        company = safe_get(job, "company")
        location = safe_get(job, "location")
        start = safe_get(job, "start")
        end = safe_get(job, "end")
        highlights = as_bullets(job.get("highlights", []))
        out.append(f"""
        <div class="exp">
          <div class="row">
            <div><span class="job-title">{title}</span> · <span class="company">{company}</span></div>
            <div class="meta">{location} · {start} — {end}</div>
          </div>
          {highlights}
        </div>
        """)
    return "\n".join(out)

def render_education(items):
    if not items:
        return "<p>—</p>"
    out = []
    for ed in items:
        qual = safe_get(ed, "qualification")
        inst = safe_get(ed, "institution")
        start = safe_get(ed, "start")
        end = safe_get(ed, "end")
        details = safe_get(ed, "details")
        out.append(f"""
        <div class="edu">
          <div class="row">
            <div><strong>{qual}</strong> — {inst}</div>
            <div class="meta">{start} — {end}</div>
          </div>
          <p>{details}</p>
        </div>
        """)
    return "\n".join(out)

def render_badges(items):
    if not items:
        return ""
    return " ".join(f"<span>{x}</span>" for x in items)

def render_projects(items):
    if not items:
        return ""
    cards = []
    for p in items:
        name = safe_get(p, "name")
        link = safe_get(p, "link")
        summary = safe_get(p, "summary")
        a_start = f"<a href='{link}'>" if link else ""
        a_end = "</a>" if link else ""
        cards.append(f"<li><strong>{a_start}{name}{a_end}</strong> — {summary}</li>")
    return "<section><h2>Projects</h2><ul>" + "\n".join(cards) + "</ul></section>"

def render_block(title, items):
    if not items:
        return ""
    lis = "\n".join(f"<li>{x}</li>" for x in items)
    return f"<section><h2>{title}</h2><ul>{lis}</ul></section>"

def render_html(data, template_html):
    skills_html = render_badges(data.get("skills", []))
    experience_html = render_experience(data.get("experience", []))
    education_html = render_education(data.get("education", []))
    projects_block = render_projects(data.get("projects", []))
    certs_block = render_block("Certifications", data.get("certs", []))
    awards_block = render_block("Awards", data.get("awards", []))

    keys = {
        "name": safe_get(data, "name"),
        "role": safe_get(data, "role"),
        "location": safe_get(data, "location"),
        "email": safe_get(data, "email"),
        "phone": safe_get(data, "phone"),
        "website": safe_get(data, "website"),
        "summary": safe_get(data, "summary"),
        "skills_html": skills_html,
        "experience_html": experience_html,
        "education_html": education_html,
        "projects_block": projects_block,
        "certs_block": certs_block,
        "awards_block": awards_block,
        "updated": safe_get(data, "updated", str(date.today())),
    }
    return template_html.format(**keys)

@app.route("/", methods=["GET"])
def form():
    return render_template("form.html")

@app.route("/generate", methods=["POST"])
def generate():
    # Read values
    name = request.form.get("name","")
    role = request.form.get("role","")
    location = request.form.get("location","")
    email = request.form.get("email","")
    phone = request.form.get("phone","")
    website = request.form.get("website","")
    summary = request.form.get("summary","")
    skills = [s.strip() for s in request.form.get("skills","").split(",") if s.strip()]

    # Experience/Education/Projects accept JSON arrays for v1
    def parse_json_field(field):
        txt = request.form.get(field,"").strip()
        if not txt:
            return []
        try:
            return json.loads(txt)
        except Exception:
            return []

    experience = parse_json_field("experience_json")
    education = parse_json_field("education_json")
    projects = parse_json_field("projects_json")
    certs = [s.strip() for s in request.form.get("certs","").split(",") if s.strip()]
    awards = [s.strip() for s in request.form.get("awards","").split(",") if s.strip()]

    data = {
        "name": name, "role": role, "location": location,
        "email": email, "phone": phone, "website": website,
        "summary": summary, "skills": skills,
        "experience": experience, "education": education,
        "projects": projects, "certs": certs, "awards": awards
    }

    template_html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = render_html(data, template_html)

    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Content-Disposition"] = "inline; filename=generated_cv.html"
    return resp

if __name__ == "__main__":
    app.run(debug=True, port=5001)
