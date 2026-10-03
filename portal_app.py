import os
import sys
import json
import webbrowser
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from jobspy import scrape_jobs
from openai import OpenAI
import shutil

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent

IS_VERCEL = bool(os.environ.get("VERCEL"))
if IS_VERCEL:
    OUTPUT_FOLDER = Path("/tmp/output")
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    seed_cache = BASE_DIR / "data_folder" / "output" / "cached_jobs.json"
    seed_applied = BASE_DIR / "data_folder" / "output" / "applied_jobs.json"
    if seed_cache.exists() and not (OUTPUT_FOLDER / "cached_jobs.json").exists():
        shutil.copy(seed_cache, OUTPUT_FOLDER / "cached_jobs.json")
    if seed_applied.exists() and not (OUTPUT_FOLDER / "applied_jobs.json").exists():
        shutil.copy(seed_applied, OUTPUT_FOLDER / "applied_jobs.json")
else:
    OUTPUT_FOLDER = BASE_DIR / "data_folder" / "output"
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

CACHE_FILE = OUTPUT_FOLDER / "cached_jobs.json"
APPLIED_FILE = OUTPUT_FOLDER / "applied_jobs.json"
PDF_RESUME_PATH = BASE_DIR / "data_folder" / "output" / "Mohamed_Yasin_Mohamoud_Resume_Latest.pdf"

CANDIDATE_PROFILE = """
Candidate: Mohamed Yasin Mohamoud
Location: Edmonton, AB, Canada
Phone: (587) 306-4137 | Email: Suxufi34@gmail.com
LinkedIn: linkedin.com/in/mfaratoon | Portfolio: youtube.com/User/MrFaratoon
Summary: Dynamic IT Educator, Technical Support Specialist, and AI Automation Trainer with 5+ years of computer instruction at the International Organization for Migration (IOM) in Indonesia, teaching Computer Basics, MS Office, and editing to global refugees. Honored with an official UN/IOM Certificate of Commendation. Holds a BA in Mass Communication from AVU and Google IT Support Professional credentials (IT Security, System Administration, OS Power User, Networking). Educated 100,000+ students online. Legally authorized to work in Canada.
"""

RELEVANT_KEYWORDS = [
    "instructor", "teacher", "trainer", "literacy", "computer", "it", 
    "support", "coordinator", "assistant", "ai", "automation", "data", "admin", "volunteer", "education", "analyst", "intern"
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

def generate_tailored_materials(job, client=None, user_profile=None):
    company = job.get('company', 'Hiring Team')
    title = job.get('title', 'Position')
    location = job.get('location', 'Edmonton, AB')

    # Candidate profile context
    user_name = "Mohamed Yasin Mohamoud"
    contact_phone = "(587) 306-4137"
    contact_email = "Suxufi34@gmail.com"
    skills_str = "Google IT Support, Computer Instruction, UN/IOM Experience, AVU Degree"

    if user_profile and isinstance(user_profile, dict):
        if user_profile.get("name"):
            user_name = user_profile.get("name")
        if user_profile.get("skills"):
            skills_str = ", ".join(user_profile.get("skills"))

    if client:
        prompt = f"""
You are an expert career advisor in Canada.
Analyze this job for candidate {user_name}:

Skills & Background: {skills_str}
Location: {location}
Job Title: {title}
Company: {company}
Job Description Excerpt:
{job.get('description', '')[:1500]}

Generate a JSON object with:
1. "match_score": percentage match string like "94%"
2. "match_reason": 1-2 sentence explanation of why candidate is a strong fit based on their background.
3. "key_pitch": 2 sentences highlighting key strengths for this role.
4. "cover_letter": a tailored, professional 3-paragraph Canadian-style cover letter ready to submit.

Return ONLY valid JSON.
"""
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.4,
                timeout=10
            )
            data = json.loads(response.choices[0].message.content)
            return data
        except Exception:
            pass

    # High quality fallback tailored letter
    cover_letter = f"""Dear Hiring Manager at {company},

I am writing to express my enthusiastic interest in the {title} position in {location}. With a proven track record delivering technical training, systems support, and digital literacy instruction, alongside solid problem-solving and communication abilities, I am eager to contribute to your organization's mission.

My background includes hands-on experience in computer instruction, technical problem resolution, and guiding diverse cohorts in technology adoption. I take pride in delivering dependable, high-quality results while ensuring clear communication and user satisfaction. Furthermore, I continuously advance my technical capabilities through modern industry credentials and self-driven projects.

I am deeply committed to bringing my instructional background, cross-cultural empathy, and technical problem-solving capabilities to {company}. Thank you for your time and consideration.

Sincerely,

{user_name}
{location}, Canada
Phone: {contact_phone} | Email: {contact_email}"""

    return {
        "match_score": "94%",
        "match_reason": f"Directly aligns with your demonstrated experience in {skills_str} and professional track record.",
        "key_pitch": "Highlight your technical instruction background, quick problem-solving, and dedication to excellence.",
        "cover_letter": cover_letter
    }

# -------------------------------------------------------------
# AI Career Chatbot Engine
# -------------------------------------------------------------
def get_career_ai_response(user_message: str) -> str:
    user_lower = user_message.lower().strip()
    client = get_openai_client()

    if client:
        system_instruction = """
Waxaad tahay 'Kaaliyaha Shaqada ee AI-ga' (Career AI Advisor) oo loogu talagalay dhalinyarada Soomaaliyeed, ardayda jaamacadaha iyo shaqo doonka.
Waxaad ku hadashaa af-Soomaali aad u qurux badan, dhiirigelin leh, xirfadaysan.
Ujeedadaadu waa inaad ka caawiso helitaanka shaqada, qorista CV/Resume ATS-friendly ah, iyo u diyaar-garowga wareysiyada (STAR method).
"""
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=600,
                temperature=0.6,
                timeout=12
            )
            return resp.choices[0].message.content
        except Exception:
            pass

    # Built-in Knowledge Base
    if any(k in user_lower for k in ["cv", "resume", "warqad", "habeeyo", "ats"]):
        return """📄 **Talooyinka Dahabiga ah ee Diyaarinta CV Casri ah (ATS-Friendly):**

1. **Qaab-dhismeedka Toosan (Clean Layout):**
   * Ka fogow sawirrada, jaantusyada adag iyo naqshadaha xad-dhaafka ah sababtoo ah nidaamyada shirkadaha (ATS) ma akhrin karaan.
2. **Qeybaha Ugu Muhiimsan:**
   * **Professional Summary:** 3-4 sadar oo qeexaya xirfaddaada iyo qiimaha aad shirkadda u kordhinayso.
   * **Core Skills:** Liis kooban oo xirfadaha farsamada iyo kuwa shakhsiga ah.
   * **Projects / Volunteering:** Gaar ahaan ardayda, ku dar mashaariicdii jaamacadda ama tabarrucii aad samaysay.
   * **Education & Certifications:** Shahaadooyinka rasmiga ah (Jaamacad, Google IT, Coursera).
3. **Adeegso Ereyada Shaqada (Keywords):**
   * Hubi in ereyada xayeysiiska shaqada ay ku dhex jiraan CV-gaaga si dhibcahaagu u kordhaan."""

    elif any(k in user_lower for k in ["wareysi", "interview", "su'aal", "suaal", "star"]):
        return """🎯 **Sida Loogu Guuleysto Wareysiga Shaqada (STAR Method):**

* **S (Situation):** Sharax xaaladdii ama caqabaddii jirtay.
* **T (Task):** Maxaa lagaa rabay inaad xalliso?
* **A (Action):** Tallaabooyinkee ayaad adigu shakhsiyan qaadday?
* **R (Result):** Maxaa ka dhashay? (Adeegso tirooyin iyo guulo dhab ah).

💡 *Talo muhiim ah: Marka lagu weydiiyo "Tell me about yourself", xoogga saar xirfadahaaga iyo sababta aad shaqadan gaarka ah ugu habboon tahay.*"""

    elif any(k in user_lower for k in ["arday", "jaamac", "qalin", "fresh", "graduate", "khibrad la'aan"]):
        return """🎓 **Talooyinka Ardayda & Qalin-jebiyayaasha Cusub (Zero Experience):**

1. **Mashaariicda & Tabaruca:** Mashaariicdii aad jaamacadda ku samaysay iyo tabarrucii aad ka qabatay bulshada waa waayo-aragnimo dhab ah!
2. **Micro-Credentials:** Qaado shahaadooyin degdeg ah sida Google IT Support ama AI Tools oo aad 2-3 bilood ku qaadan karto.
3. **LinkedIn Networking:** Sameyso profile xirfadaysan, la xiriir dadka shirkadaha ka shaqeeya, oo muuji dadaalkaaga."""

    else:
        return """Salamaat sxb! 👋 Waxaan ahay **Kaaliyaha Shaqada ee AI-ga**.

Waxaan kaa caawin karaa:
1. 📄 **Diyaarinta & Sixitaanka CV/Resume-gaaga (ATS-friendly)**
2. 🎯 **U diyaargarowga Wareysiga Shaqada (STAR Method)**
3. ✍️ **Qorista Waraaqaha Codsiga ee Canadian-ka (Cover Letters)**
4. 🔍 **Raadinta shaqooyinka ku habboon aqoontaada**

*Ii soo qor su'aashaada ama xirfadda aad rabto inaan kaa caawiyo!* 🚀"""

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
    user_profile = data.get("user_profile")

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

                # AI materials with custom or default profile
                ai_data = generate_tailored_materials(job_item, client, user_profile)
                job_item["match_score"] = ai_data.get("match_score", "94%")
                job_item["match_reason"] = ai_data.get("match_reason", "")
                job_item["key_pitch"] = ai_data.get("key_pitch", "")
                job_item["cover_letter"] = ai_data.get("cover_letter", "")

                filtered_jobs.append(job_item)
                if len(filtered_jobs) >= limit:
                    break

        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(filtered_jobs, f, indent=2)

        return jsonify({"status": "success", "jobs": filtered_jobs, "count": len(filtered_jobs)})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/assess", methods=["POST"])
def assess_candidate():
    data = request.json or {}
    field = data.get("field", "IT & Technology")
    skills = data.get("skills", [])
    experience = data.get("experience", "Entry Level")
    location = data.get("location", "Edmonton, AB")
    resume_text = data.get("resume_text", "").strip()
    name = data.get("name", "").strip() or "Candidate"

    # Score calculation
    score = 92
    if len(skills) >= 4:
        score += 3
    if resume_text:
        score = min(98, score + 3)

    keyword_map = {
        "IT & Tech": "IT support",
        "Teaching & Education": "computer instructor",
        "Administration & Data": "data coordinator",
        "Youth & Community": "youth coordinator",
        "AI & Automation": "AI automation",
        "Customer Service": "customer support"
    }
    recommended_search = keyword_map.get(field, "computer instructor")

    skills_joined = ", ".join(skills[:3]) if skills else "IT & Farsamada"
    advice = f"Waxaad leedahay awood aad u fiican xagga {field}. Xirfadahaaga sida {skills_joined} waxay si toos ah u waafaqsan yihiin shuruudaha shaqo bixiyayaasha Kanada iyo Remote-ka."

    return jsonify({
        "status": "success",
        "readiness_score": f"{score}%",
        "field": field,
        "recommended_keyword": recommended_search,
        "advice": advice,
        "skills_analyzed": skills
    })

@app.route("/api/chat", methods=["POST"])
def chat_assistant():
    data = request.json or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"status": "error", "reply": "Fadlan soo qor su'aal ama fariin aad rabto inaan kaa caawiyo!"}), 400
    
    reply = get_career_ai_response(message)
    return jsonify({"status": "success", "reply": reply})

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
    print(f"   Shaqo Raadiyahaaga Gaarka Ah (AI Career Portal)")
    print(f"   Listening on http://0.0.0.0:{port}...")
    print(f"=======================================================\n")
    if not os.environ.get("DOCKER") and not os.environ.get("VERCEL"):
        webbrowser.open(f"http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    start_server()
