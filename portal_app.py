import os
import sys
import json
import webbrowser
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from jobspy import scrape_jobs
from openai import OpenAI

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
IS_VERCEL = bool(os.environ.get("VERCEL"))
if IS_VERCEL:
    OUTPUT_FOLDER = Path("/tmp/output")
else:
    OUTPUT_FOLDER = BASE_DIR / "data_folder" / "output"

CACHE_FILE = OUTPUT_FOLDER / "cached_jobs.json"
APPLIED_FILE = OUTPUT_FOLDER / "applied_jobs.json"
PDF_RESUME_PATH = BASE_DIR / "data_folder" / "output" / "Mohamed_Yasin_Mohamoud_Resume_Latest.pdf"

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

CANDIDATE_PROFILE = """
Candidate: Mohamed Yasin Mohamoud
Location: Edmonton, AB, Canada
Phone: (587) 306-4137 | Email: Suxufi34@gmail.com
LinkedIn: linkedin.com/in/mfaratoon | Portfolio: youtube.com/User/MrFaratoon
Summary: Dynamic IT Educator, Technical Support Specialist, and AI Automation Trainer with 5+ years of computer instruction at the International Organization for Migration (IOM) in Indonesia, teaching Computer Basics, MS Office, and editing to global refugees. Honored with an official UN/IOM Certificate of Commendation. Holds a BA in Mass Communication from AVU and Google IT Support Professional credentials (IT Security, System Administration, OS Power User, Networking). Educated 100,000+ students online. Legally authorized to work in Canada.
"""

RELEVANT_KEYWORDS = [
    "instructor", "teacher", "trainer", "literacy", "computer", "it", 
    "support", "coordinator", "assistant", "ai", "automation", "data", "admin", "volunteer", "education", "analyst"
]

IRRELEVANT_KEYWORDS = [
    "driver", "snow", "truck", "welder", "cook", "mechanic", "nurse", "plumber"
]

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception:
        return None

def load_applied_links():
    if APPLIED_FILE.exists():
        try:
            with open(APPLIED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_applied_link(job_url):
    applied = load_applied_links()
    applied.add(job_url)
    with open(APPLIED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(applied), f, indent=2)

def generate_tailored_materials(job, client=None):
    company = job.get('company', 'Hiring Team')
    title = job.get('title', 'Position')
    location = job.get('location', 'Edmonton, AB')

    if client:
        prompt = f"""
You are an expert career advisor in Canada.
Analyze this job for candidate Mohamed Yasin Mohamoud:

{CANDIDATE_PROFILE}

Job Title: {title}
Company: {company}
Location: {location}
Job Description Excerpt:
{job.get('description', '')[:1500]}

Generate a JSON object with:
1. "match_score": percentage match string like "94%"
2. "match_reason": 1-2 sentence explanation of why Mohamed is a strong fit based on his IOM teaching, Google IT certs, and AVU degree.
3. "key_pitch": 2 sentences highlighting key strengths for this role.
4. "cover_letter": a tailored, professional 3-paragraph Canadian-style cover letter ready to submit.

Return ONLY valid JSON.
"""
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.4
            )
            data = json.loads(response.choices[0].message.content)
            return data
        except Exception:
            pass

    cover_letter = f"""Dear Hiring Manager at {company},

I am writing to express my enthusiastic interest in the {title} position in {location}. With over five years of dedicated experience delivering computer literacy, office productivity software, and digital media instruction for the International Organization for Migration (IOM) in Indonesia, alongside comprehensive credentials in Google IT Support and modern AI automation, I am eager to contribute to your organization.

During my service with IOM, I designed and facilitated interactive training modules in Computer Basics, Microsoft Office Suite (Word, Excel, PowerPoint), and digital editing for diverse multicultural refugee cohorts. My commitment to empowering learners with workforce-ready technical skills was recognized with an official Certificate of Commendation from IOM leadership. Additionally, I hold a Bachelor's Degree in Media and Mass Communication (AVU) and have completed advanced certifications in IT Security, Systems Administration, and Computer Networking through Coursera/Google.

I am deeply committed to serving the Edmonton community and would welcome the opportunity to bring my instructional background, cross-cultural empathy, and technical problem-solving capabilities to {company}. Thank you for your time and consideration.

Sincerely,

Mohamed Yasin Mohamoud
Edmonton, AB, Canada
Phone: (587) 306-4137 | Email: Suxufi34@gmail.com"""

    return {
        "match_score": "94%",
        "match_reason": f"Directly aligns with your 5+ years of computer instruction at UN/IOM, AVU degree, and Google IT Support certifications.",
        "key_pitch": "Highlight your UN/IOM Certificate of Commendation, adult digital literacy coaching, and systems administration skills.",
        "cover_letter": cover_letter
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/jobs")
def get_cached_jobs():
    applied_links = load_applied_links()
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                jobs = json.load(f)
                for j in jobs:
                    j["is_applied"] = j.get("job_url") in applied_links
                return jsonify({"status": "success", "jobs": jobs, "cached": True})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "success", "jobs": [], "cached": False})

@app.route("/api/search", methods=["POST"])
def search_jobs():
    data = request.json or {}
    term = data.get("term", "computer instructor")
    location = data.get("location", "Edmonton, AB")
    is_remote = bool(data.get("remote", False))
    limit = int(data.get("limit", 5))

    client = get_openai_client()
    applied_links = load_applied_links()

    try:
        raw_jobs = scrape_jobs(
            site_name=["indeed", "zip_recruiter", "glassdoor"],
            search_term=term,
            location=location,
            results_wanted=limit * 2,
            hours_old=72,
            country_indeed="Canada",
            is_remote=is_remote
        )

        filtered_jobs = []
        if not raw_jobs.empty:
            for _, row in raw_jobs.iterrows():
                title = str(row.get("title", "")).strip()
                title_lower = title.lower()
                if any(bad in title_lower for bad in IRRELEVANT_KEYWORDS):
                    continue

                job_url = str(row.get("job_url", "")).strip()
                if not job_url or any(j["job_url"] == job_url for j in filtered_jobs):
                    continue

                job_item = {
                    "site": str(row.get("site", "indeed")).title(),
                    "title": title,
                    "company": str(row.get("company", "Organization")),
                    "location": str(row.get("location", location)),
                    "job_url": job_url,
                    "description": str(row.get("description", ""))[:2000],
                    "date_posted": str(row.get("date_posted", "Recent")),
                    "job_type": str(row.get("job_type", "Full-time / Part-time")),
                    "is_applied": job_url in applied_links
                }

                # AI materials
                ai_data = generate_tailored_materials(job_item, client)
                job_item["match_score"] = ai_data.get("match_score", "92%")
                job_item["match_reason"] = ai_data.get("match_reason", "")
                job_item["key_pitch"] = ai_data.get("key_pitch", "")
                job_item["cover_letter"] = ai_data.get("cover_letter", "")

                filtered_jobs.append(job_item)
                if len(filtered_jobs) >= limit:
                    break

        # Save to cache
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(filtered_jobs, f, indent=2)

        return jsonify({"status": "success", "jobs": filtered_jobs, "count": len(filtered_jobs)})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/mark_applied", methods=["POST"])
def mark_applied():
    data = request.json or {}
    job_url = data.get("job_url")
    if job_url:
        save_applied_link(job_url)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "No job_url provided"}), 400

@app.route("/download/resume")
def download_resume():
    if PDF_RESUME_PATH.exists():
        return send_file(
            PDF_RESUME_PATH,
            as_attachment=True,
            download_name="Mohamed_Yasin_Mohamoud_Resume.pdf"
        )
    return "Resume PDF not found. Please generate it first.", 404

def start_server():
    port = int(os.environ.get("PORT", 5050))
    print(f"\n=======================================================")
    print(f"   Mohamed Yasin Mohamoud - Job Portal UI")
    print(f"   Listening on http://0.0.0.0:{port}...")
    print(f"=======================================================\n")
    if not os.environ.get("DOCKER") and not os.environ.get("VERCEL"):
        webbrowser.open(f"http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    start_server()
