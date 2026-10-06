import os
import sys
import json
import webbrowser
import random
import re
import urllib.parse
import shutil
from datetime import datetime
from pathlib import Path
import requests
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

try:
    from jobspy import scrape_jobs
except ImportError:
    scrape_jobs = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent

def load_env_file():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

load_env_file()

IS_VERCEL = bool(os.environ.get("VERCEL"))
if IS_VERCEL:
    OUTPUT_FOLDER = Path("/tmp/output")
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    seed_cache = BASE_DIR / "data_folder" / "output" / "cached_jobs.json"
    seed_applied = BASE_DIR / "data_folder" / "output" / "applied_jobs.json"
    seed_bookings = BASE_DIR / "data_folder" / "output" / "bookings.json"
    if seed_cache.exists() and not (OUTPUT_FOLDER / "cached_jobs.json").exists():
        shutil.copy(seed_cache, OUTPUT_FOLDER / "cached_jobs.json")
    if seed_applied.exists() and not (OUTPUT_FOLDER / "applied_jobs.json").exists():
        shutil.copy(seed_applied, OUTPUT_FOLDER / "applied_jobs.json")
    if seed_bookings.exists() and not (OUTPUT_FOLDER / "bookings.json").exists():
        shutil.copy(seed_bookings, OUTPUT_FOLDER / "bookings.json")
else:
    OUTPUT_FOLDER = BASE_DIR / "data_folder" / "output"
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

CACHE_FILE = OUTPUT_FOLDER / "cached_jobs.json"
APPLIED_FILE = OUTPUT_FOLDER / "applied_jobs.json"
BOOKINGS_FILE = OUTPUT_FOLDER / "bookings.json"
PDF_RESUME_PATH = BASE_DIR / "data_folder" / "output" / "Mohamed_Yasin_Mohamoud_Resume_Latest.pdf"

# In-memory session message tracking (max 30 messages per session)
CHAT_SESSIONS = {}
MAX_SESSION_MESSAGES = 30

CANDIDATE_PROFILE = """
Candidate: Mohamed Yasin
Role: Dynamic IT Educator, Computer Support Specialist, and AI Automation Trainer
Experience: Experienced computer systems instructor and AI automation trainer specializing in Computer Basics, Systems Administration, and AI Chatbots. Dedicated to empowering Somali youth and university students.
Education: BA in Media & Mass Communication (AVU) and Google IT Support Professional credentials (IT Security, System Administration, OS, Networking). Educated 100,000+ students online.
Locations Supported: Somalia (Mogadishu, Hargeisa), East Africa (Kenya, Ethiopia), Global Remote, Canada (Edmonton).
"""

RELEVANT_KEYWORDS = [
    "instructor", "teacher", "trainer", "literacy", "computer", "it", 
    "support", "coordinator", "assistant", "ai", "automation", "data", "admin", "volunteer", "education", "analyst", "intern", "developer", "software", "network", "system"
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

def load_bookings():
    if BOOKINGS_FILE.exists():
        try:
            with open(BOOKINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_booking(record):
    bookings = load_bookings()
    bookings.append(record)
    with open(BOOKINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(bookings, f, indent=2)

def is_spam_or_invalid(text: str) -> tuple[bool, str]:
    text_clean = text.strip()
    if not text_clean:
        return True, "Fariintaadu waa maran tahay. Fadlan su'aal ama codsi soo qor."

    # 1. Media and injection check (Only Text allowed!)
    media_patterns = [
        r"data:image\/",
        r"data:video\/",
        r"\.(?:png|jpe?g|gif|webp|bmp|mp4|mov|avi|mkv|webm|svg)\b",
        r"<img\b",
        r"<video\b",
        r"<iframe\b",
        r"<script\b",
        r"base64,",
        r"\[img\]",
        r"\[video\]"
    ]
    for pat in media_patterns:
        if re.search(pat, text_clean, re.IGNORECASE):
            return True, "⚠️ Kaliya qoraal (text) ayaa la oggol yahay. Sawirrada, muuqaallada, iyo faylasha lama oggola fadlan."

    # 2. Character repetition spam (e.g. "aaaaaa", "!!!!!!", "zzzzzz")
    if re.search(r"(.)\1{6,}", text_clean):
        return True, "⚠️ Fadlan hadalka ha ku badin si uusan credit-ku u khasaarin. Haddii aad buugaag doonaysid, toos ugu biir: https://dhegeysobuug.substack.com/ (waxaad helaysaa 2 buug oo bilaash ah oo si toos ah automatic inbox-kaaga ugu soo dhacaya marka aad subscribe gareyso)."

    # 3. Gibberish / keyboard mash detection
    words = text_clean.split()
    for w in words:
        if len(w) > 35 and not w.startswith("http"):
            return True, "⚠️ Qoraalkaaga waxaa ku jira ereyo aan la fahmi karin. Haddii aad buugaag u baahan tahay, toos uga hel: https://dhegeysobuug.substack.com/ (waxaad helaysaa 2 buug oo bilaash ah oo si automatic ah inbox-kaaga ugu soo dhacaya)."
        if len(w) >= 9 and not re.search(r"[aeiouy]", w, re.IGNORECASE) and not w.isdigit():
            return True, "⚠️ Fadlan soo qor fariin macno leh. Haddii aad buug doonayso, toos ugu biir warsidaha: https://dhegeysobuug.substack.com/ waxaadna helaysaa 2 buug oo bilaash ah oo si automatic ah inbox-kaaga ugu soo dhacaya."

    # 4. Profanity check
    vulgar = ["wasmo", "siil", "gus", "futada", "fck", "bitch", "shit"]
    for v in vulgar:
        if re.search(r"\b" + re.escape(v) + r"\b", text_clean, re.IGNORECASE):
            return True, "⚠️ Fadlan ilaali asluubta iyo anshaxa suuban. Ereyadan lama oggola."

    return False, ""

def check_session_limit(session_id: str) -> tuple[bool, int, int]:
    """Returns (is_allowed, remaining_messages, current_count)"""
    current = CHAT_SESSIONS.get(session_id, 0)
    if current >= MAX_SESSION_MESSAGES:
        return False, 0, current
    current += 1
    CHAT_SESSIONS[session_id] = current
    remaining = max(0, MAX_SESSION_MESSAGES - current)
    return True, remaining, current

def get_curated_somali_it_jobs(term="Dhammaan", location="Dhammaan", is_remote=False):
    loc_l = location.lower() if location else ""
    term_l = term.lower() if term else ""

    all_jobs = [
        # 1. Finance & Accounting
        {
            "site": "SomaliJobs",
            "title": "Finance & Accounting Officer",
            "company": "Dahabshiil Group",
            "location": "Muqdisho & Hargeysa, Soomaaliya",
            "job_url": "https://www.dahabshiil.com/careers/finance-accounting-officer",
            "description": "Dahabshiil Group waxay raadinaysaa sarkaal xisaabeed oo maamula xisaab-xirka bisha, diyaarinta warbixinnada maaliyadeed, xisaabinta dakhliga iyo kharashka, iyo dib-u-eegista xisaabaadka bangiga. Shuruudo: Shahaadada koowaad ee Xisaabaadka ama Maaliyadda, aqoonta Excel iyo software-ada xisaabaadka.",
            "date_posted": "2026-10-03",
            "job_type": "Full-time",
            "category": "finance"
        },
        # 2. HR & Administration
        {
            "site": "SomaliJobs",
            "title": "Human Resources (HR) & Admin Assistant",
            "company": "Salaam Somali Bank",
            "location": "Muqdisho, Soomaaliya",
            "job_url": "https://salaambank.so/careers/hr-admin-assistant-2026",
            "description": "Salaam Somali Bank wuxuu shaqaaleysiinayaa Kaaliyaha HR & Maamulka. Shaqada waxaa ka mid ah qabashada codsiyada shaqo-doonka, abaabulka wareysiyada, diyaarinta heshiisyada shaqaalaha, iyo ilaalinta faylalka shaqaalaha.",
            "date_posted": "2026-10-02",
            "job_type": "Full-time",
            "category": "finance"
        },
        # 3. Customer Care & Call Center
        {
            "site": "SomaliJobs",
            "title": "Customer Care & Call Center Representative",
            "company": "Hormuud Telecom",
            "location": "Muqdisho, Soomaaliya",
            "job_url": "https://www.hormuud.com/careers/customer-care-representative",
            "description": "Hormuud Telecom waxay qaadanaysaa shaqaale u heellan adeegga macaamiisha (Call Center). Shaqadu waxay tahay ka jawaabista taleefannada macaamiisha, xallinta cabashooyinka EVC Plus, Internet-ka iyo xirmooyinka adeegga. Luuqadaha: Af-Soomaali sugan iyo Ingiriis fudud.",
            "date_posted": "2026-10-03",
            "job_type": "Full-time",
            "category": "sales"
        },
        # 4. Sales & Marketing
        {
            "site": "SomaliJobs",
            "title": "Sales & Corporate Marketing Executive",
            "company": "Telesom Company",
            "location": "Hargeysa & Burco, Soomaaliya",
            "job_url": "https://www.telesom.com/careers/sales-executive",
            "description": "Telesom waxay raadinaysaa saraakiil iib iyo suuqgeyn oo dardargeliya iibka xirmooyinka ganacsiga (Enterprise internet & Zaad). Waxaa loo baahan yahay shakhsi firfircoon oo leh xirfad xiriir iyo qancin macaamiil.",
            "date_posted": "2026-10-01",
            "job_type": "Full-time",
            "category": "sales"
        },
        # 5. Healthcare & Nutrition (NGO)
        {
            "site": "ReliefWeb",
            "title": "Public Health & Nutrition Field Officer",
            "company": "Save the Children Somalia",
            "location": "Baydhabo & Muqdisho, Soomaaliya",
            "job_url": "https://somalia.savethechildren.net/careers/health-nutrition-officer",
            "description": "Kormeerka xarumaha daryeelka hooyada iyo dhallaanka, bixinta dawooyinka iyo nafaqada degdegga ah, iyo diyaarinta xogta caafimaadka bulshada ee deegaannada Koonfur-Galbeed iyo Banaadir.",
            "date_posted": "2026-10-02",
            "job_type": "Contract",
            "category": "health"
        },
        # 6. Humanitarian Project Officer
        {
            "site": "ReliefWeb",
            "title": "Project Officer – Community Resilience & Youth Support",
            "company": "Somali Red Crescent Society (SRCS)",
            "location": "Garoowe & Hargeysa, Soomaaliya",
            "job_url": "https://www.srcs.org.so/careers/project-officer",
            "description": "Hoggaaminta barnaamijyada taakuleynta bulshada, tababarrada farsamada gacanta ee dhalinyarada, iyo isku-xirka laamaha dowladda iyo hay'adaha gargaarka.",
            "date_posted": "2026-10-01",
            "job_type": "Full-time",
            "category": "health"
        },
        # 7. Education & Teaching
        {
            "site": "SomaliJobs",
            "title": "Secondary School English & Mathematics Teacher",
            "company": "Kulan Education Network",
            "location": "Muqdisho & Kismaayo, Soomaaliya",
            "job_url": "https://kulan.edu.so/careers/teachers-2026",
            "description": "Bixinta casharrada maadooyinka Ingiriisiga iyo Xisaabta ee ardayda fasallada sare (Form 1 - Form 4), diyaarinta casharrada, iyo saxidda imtixaanaadka.",
            "date_posted": "2026-10-02",
            "job_type": "Full-time",
            "category": "education"
        },
        # 8. Logistics & Procurement
        {
            "site": "UNJobs",
            "title": "Logistics & Procurement Assistant",
            "company": "UN World Food Programme (WFP Somalia)",
            "location": "Muqdisho & Berbera, Soomaaliya",
            "job_url": "https://www.wfp.org/careers/somalia-logistics-assistant",
            "description": "Dabagalka maraakiibta iyo shixnadaha gargaarka, maareynta bakhaarada kaydka, xiriirinta shirkadaha gaadiidka, iyo hubinta badqabka agabka cuntada.",
            "date_posted": "2026-10-03",
            "job_type": "Contract",
            "category": "logistics"
        },
        # 9. IT Support & Systems
        {
            "site": "SomaliTech",
            "title": "IT Support & Network Technician",
            "company": "Premier Bank",
            "location": "Muqdisho, Soomaaliya",
            "job_url": "https://premierbank.so/careers/it-support-technician",
            "description": "Xallinta cilladaha kombuyuutarrada xarumaha bangiga, habeynta LAN/WAN routers, iyo taageerada shaqaalaha xagga software-ka iyo amniga nidaamka.",
            "date_posted": "2026-10-02",
            "job_type": "Full-time",
            "category": "tech"
        },
        # 10. Web & Software Development
        {
            "site": "SomaliTech",
            "title": "Web & Software Developer (Full Stack)",
            "company": "Dahabshiil Bank International",
            "location": "Hargeysa, Soomaaliya",
            "job_url": "https://www.dahabshiil.com/careers/software-developer",
            "description": "Dhisidda iyo dayactirka bogagga internet-ka iyo adeegyada fintech. Xirfadaha: HTML, CSS, JavaScript/React, Python/Node.js, iyo maamulka SQL databases.",
            "date_posted": "2026-10-01",
            "job_type": "Full-time",
            "category": "tech"
        },
        # 11. Digital Marketing & Content Creation (Remote)
        {
            "site": "RemoteGlobal",
            "title": "Digital Marketing & Social Media Specialist (Remote)",
            "company": "Isbar Media & Tech Hub",
            "location": "Remote (Soomaaliya & Global)",
            "job_url": "https://isbar-ai.com/#jobsSection",
            "description": "Maareynta baraha bulshada (Facebook, TikTok, LinkedIn), abuurista qoraallada xayeysiiska, naqshadeynta boorarka digital-ka ah, iyo kordhinta macaamiisha.",
            "date_posted": "2026-10-03",
            "job_type": "Remote / Full-time",
            "category": "sales"
        },
        # 12. East Africa Regional (Kenya)
        {
            "site": "EastAfricaJobs",
            "title": "Customer Operations & Junior Analyst",
            "company": "Safaricom Tech Hub",
            "location": "Nairobi, Kenya",
            "job_url": "https://safaricom.co.ke/careers/operations-analyst",
            "description": "Falanqaynta xogta macaamiisha, soo saarista warbixinnada suuqa, iyo taageerada adeegyada lacag-dirista ee gobolka Bariga Afrika.",
            "date_posted": "2026-10-02",
            "job_type": "Full-time",
            "category": "finance"
        }
    ]

    matched = []
    category_map = {
        "finance": ["finance", "xisaab", "accounting", "admin", "hr", "maamul", "bank"],
        "sales": ["sales", "marketing", "iib", "suuqgeyn", "customer", "call center"],
        "health": ["health", "caafimaad", "nutrition", "ngo", "project officer", "gargaar"],
        "education": ["teacher", "education", "waxbarasho", "tababar", "school", "macallin"],
        "logistics": ["logistics", "procurement", "supply", "gaadiid", "bakhaar"],
        "tech": ["it", "developer", "software", "network", "tech", "cloud", "engineer", "computer"]
    }

    selected_cats = []
    for cat, kws in category_map.items():
        if any(k in term_l for k in kws):
            selected_cats.append(cat)

    for j in all_jobs:
        j_loc = j["location"].lower()
        j_cat = j.get("category", "")
        j_title = j["title"].lower()
        j_desc = j["description"].lower()

        # Location matching
        loc_ok = True
        if any(k in loc_l for k in ["muqdisho", "mogadishu", "banaadir"]):
            loc_ok = "muqdisho" in j_loc or "remote" in j_loc
        elif any(k in loc_l for k in ["hargeysa", "hargeisa", "puntland", "garoowe", "burco"]):
            loc_ok = any(c in j_loc for c in ["hargeysa", "garoowe", "burco", "remote"])
        elif any(k in loc_l for k in ["kenya", "nairobi"]):
            loc_ok = "kenya" in j_loc or "nairobi" in j_loc or "remote" in j_loc
        elif "remote" in loc_l or is_remote:
            loc_ok = "remote" in j_loc

        # Category/term matching
        term_ok = True
        if selected_cats:
            term_ok = (j_cat in selected_cats)
        elif term_l and term_l not in ["dhammaan", "all", "shaqo", "jobs"]:
            term_ok = (term_l in j_title or term_l in j_desc or term_l in j["company"].lower())

        if loc_ok and term_ok:
            matched.append(j)

    return matched if matched else all_jobs[:6]

def generate_tailored_materials(job, client=None, user_profile=None):
    company = job.get('company', 'Hiring Organization')
    title = job.get('title', 'IT Specialist')
    location = job.get('location', 'Soomaaliya & Remote')

    user_name = "Mohamed Yasin Mohamoud"
    contact_phone = "+1 (587) 306-4137"
    contact_email = "Suxufi34@gmail.com"
    skills_str = "Google IT Support, Computer Instruction, Network Administration, AI Automation"

    if user_profile and isinstance(user_profile, dict):
        if user_profile.get("name"):
            user_name = user_profile.get("name")
        if user_profile.get("skills"):
            skills_str = ", ".join(user_profile.get("skills"))
        if user_profile.get("location"):
            location = user_profile.get("location")

    if client:
        prompt = f"""
You are an expert career and IT hiring advisor for Somali youth and tech professionals.
Analyze this job for candidate {user_name}:

Skills & Background: {skills_str}
Location: {location}
Job Title: {title}
Company: {company}

Job Description Excerpt:
{job.get('description', '')[:1500]}

Generate a JSON object with:
1. "match_score": percentage match string like "96%"
2. "match_reason": 1-2 sentence explanation in Somali of why this Somali IT candidate is a strong fit.
3. "key_pitch": 2 sentences in Somali highlighting key strengths for this role.
4. "cover_letter": a tailored, professional 3-paragraph cover letter ready to submit.

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

I am writing to express my enthusiastic interest in the {title} position in {location}. With a solid technical foundation in computer science and information technology, including practical proficiency in {skills_str}, I am keen to contribute positively to your organization's IT operations and technological advancements.

My background includes hands-on experience in technical troubleshooting, network maintenance, systems support, and modern digital tools adoption. I take pride in delivering dependable, high-quality results while ensuring system reliability, data security, and efficient user support. Furthermore, I continuously advance my technical skill set with emerging AI technologies, automated workflows, and industry-standard practices.

I am deeply motivated to bring my technical aptitude, strong work ethic, and dedication to {company}. Thank you for your time and consideration.

Sincerely,

{user_name}
{location}
Phone: {contact_phone} | Email: {contact_email}"""

    return {
        "match_score": "96%",
        "match_reason": f"Waxay si toos ah u waafaqsan tahay xirfadahaaga IT-ga ee {skills_str} iyo baahida shaqo-bixiyaha.",
        "key_pitch": "Muuji awooddaada farsamo, xallinta degdegga ah ee ciladaha IT-ga, iyo la-qabsiga teknoolajiyadda cusub.",
        "cover_letter": cover_letter
    }

# -------------------------------------------------------------
# AI Career & Course Chatbot Engine (Multi-AI & Smart Search)
# -------------------------------------------------------------
def query_gemini_api(user_message: str, system_prompt: str) -> str:
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\nFadlan u jawaab fariintan ardayga/shaqadoonka:\n{user_message}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.6,
                "maxOutputTokens": 800
            }
        }
        resp = requests.post(url, json=payload, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
    except Exception:
        pass
    return None

def query_groq_api(user_message: str, system_prompt: str) -> str:
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return None
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 800,
            "temperature": 0.6
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return None

def get_job_portals_directory() -> str:
    return """🌐 **Hagaha Bogagga & Xiriirrada Tooska ah ee Shaqo Raadinta (Job Portals & Direct Links):**

🇸🇴 **1. Soomaaliya & Bariga Afrika:**
• 🔗 [SomaliJobs (somalijobs.com)](https://somalijobs.com) — Madasha 1-aad ee shirkadaha Soomaalida (Dahabshiil, Hormuud, Premier Bank, Telesom).
• 🔗 [Shafaf Jobs (shafaf.net)](https://shafaf.net) — Shaqooyinka dawladda, NGO-yada iyo mashaariicda gargaarka.
• 🔗 [ReliefWeb Somalia](https://reliefweb.int/jobs?country=216) — Shaqooyinka hay'adaha caalamiga ah (Save the Children, DRC, NRC, IRC).
• 🔗 [UN Jobs Somalia](https://unjobs.org/duty_stations/somalia) — Fursadaha tooska ah ee Qaramada Midoobay (WFP, UNICEF, WHO, UNDP).

🌍 **2. Shaqooyinka Online-ka ah ee Guriga (Remote):**
• 🔗 [RemoteOK (remoteok.com)](https://remoteok.com) — Shaqooyinka remote-ka ah ee caalamka (Developer, Customer Support, Marketing).
• 🔗 [We Work Remotely](https://weworkremotely.com) — Shaqooyin la aamini karo oo adduunka oo dhan laga qabto.
• 🔗 [LinkedIn Jobs](https://www.linkedin.com/jobs) — Fursadaha caalamiga ah & xiriirka shaqo-bixiyeyaasha.

🇨🇦 **3. Kanada & Gobolka Alberta (Edmonton):**
• 🔗 [Indeed Canada (ca.indeed.com)](https://ca.indeed.com) — Shaqooyinka Edmonton, Calgary & guud ahaan Canada.
• 🔗 [Job Bank Canada (jobbank.gc.ca)](https://www.jobbank.gc.ca) — Xariirka rasmiga ah ee Dawladda Federaalka Canada.

📱 **4. Madasha Shaqo Baahiye & Isbar AI:**
• 🔗 [Shaqo Baahiye Live Portal (isbar-ai.com)](https://isbar-ai.com/#jobsSection) — Raadi shaqooyinka tooska ah.
• 🤖 [Telegram Bot: @Baahiyebot](https://t.me/Baahiyebot) — Kaaliyaha 24/7 ee Telegram.
• 📄 [Soo Degso ATS Resume (PDF)](/download/resume) — CV-gaaga oo PDF diyaar ah."""

def smart_local_career_engine(user_message: str) -> str:
    user_lower = user_message.lower().strip()

    # 1. Job Portals & Links Directory Request
    if any(k in user_lower for k in [
        "link", "links", "goob", "goobaha", "website", "websites", "web",
        "portal", "portals", "xagee", "halkee", "meelaha", "bogagga", "bog",
        "url", "internetyada", "site", "sites"
    ]):
        return get_job_portals_directory()

    # 2. ATS Resume / CV Guidance & Direct Download
    if any(k in user_lower for k in ["cv", "resume", "ats", "warqad", "codsi", "cover letter", "warqadda"]):
        return """📄 **Hagaha Diyaarinta CV ATS ah & Soo Dejinta Resume-ga:**

Si CV-gaagu ugu gudbo shaandhada casriga ah ee shirkadaha (Applicant Tracking System - ATS):
1. **Qaab Fudud (Clean Layout):** Isticmaal font-yo cadcad (sida Arial, Calibri, ama Inter), kana fogow columns-ka is-dul-saaran.
2. **Keywords-ka Shaqada:** Ku dar ereyada muhiimka ah ee shaqo-bixiyuhu ku xusay xayeysiiska (Job Description).
3. **Natiijooyin Cad:** Ku cabbir guulahaaga tirooyin (tusaale: *"Waxaan xalliyay 90%+ cabashooyinka macaamiisha"*).

📥 **Soo Degso CV ATS ah oo Diyaarsan:**
• 👉 [Soo Degso Resume ATS ah (PDF)](/download/resume)
• ⚡ [Dhis CV-gaaga Bogga (AI Assessment)](#assessSection)
• 📅 Hadii aad rabto dib-u-eegis toos ah oo 1-on-1 ah, [Qabso Ballan Live ah](#bookingSection) ama WhatsApp: `+1 (587) 306-4137`."""

    # 3. Books & Substack
    if any(k in user_lower for k in ["buug", "book", "isbar", "qiimaha", "pages", "bogag", "soo dir", "dhegeyso", "buugaag"]):
        return """📚 **Buugaagta Casriga ah ee 'Isbar' (Macallin La'aan):**

1. 💻 **ISBAR COMPUTER** ($5 Kaliya | 89 Pages) • Qore: Yahye Cabdirahmaan • Editor: Mohamed Yasin
2. 👨‍💻 **ISBAR PROGRAMMING** ($5 Kaliya | 177 Pages) • Qore: Yahye Abdirahmaan • Editor: Mohamed Yasin
3. 🧠 **ISBAR AI BASIC** ($7 Kaliya | 189 Pages) • Qore: Yahye Abdirahmaan / Mohamed Yasin
4. 🤖 **ISBAR ChatGPT Prompts** (🎁 FREE / 100% Bilaash! | 87 Pages) • Qore: Mohamed Yasin • Editor: Yahye Abdirahman

📬 **Sidee ku helaysaa Buugaagta Bilaashka ah?**
Qof kasta oo ku biira (subscribe gareeya) warsidaha **Dhegeyso Buug** wuxuu helayaa **2 Buug oo Bilaash ah (Free)** oo si toos ah (automatic ah) ugu soo dhacaya email-kiisa!
👉 **Ku biir halkan si aad 2-da buug u hesho:** [dhegeysobuug.substack.com](https://dhegeysobuug.substack.com/)"""

    # 4. Open Source & Repo
    if any(k in user_lower for k in ["sida loo", "sidee loo", "sameeyaa", "repo", "source code", "shubo", "deploy", "dhis", "github"]):
        return """⭐ **Madashan waa 100% Open Source (Bilaash):**

Repository-ga rasmiga ah ee mashruucan waa bilaash qof kasta ayaana ka faa'iideysan kara:
🔗 **GitHub:** [github.com/Faratoon/Shaqo-Raadiyahaaga-Gaarka-Ah](https://github.com/Faratoon/Shaqo-Raadiyahaaga-Gaarka-Ah)

🚀 **Ma rabtaa inaad barato sida nidaamkan oo kale loogu shubo loona dhiso iyadoo AI la adeegsanayo?**
• Waxaad dooran kartaa **'Ballan Qabso'** (Live 1-on-1 Mentorship oo toos ah oo aad la yeelanayso **Mohamed Yasin**).
• 📅 Qabso Ballan Live ah bogga ama toos WhatsApp: `+1 (587) 306-4137`."""

    # 5. Courses & Automation
    if any(k in user_lower for k in ["koorso", "course", "automation", "data writing", "video editing", "whatsapp", "telegram", "bilaash"]):
        return """🎓 **Koorsooyinka AI Automation & Xirfadaha Casriga ah:**

🔹 **Paid Course (Qiimo-dhimis Gaar ah):**
• **AI ChatGPT – Data Writing 📝**: Baro curinta nuxurka, ganacsiga, iyo qorista shaqooyinka.
  - Waqtiga: 4–5 Maalmood | Qiimaha: $24 (Ardayda: **$10 Kaliya!**)

🎓 **Free Courses (100% Bilaash Ardayda Sanadkan):**
• 🎥 **AI Video Editing**: Habaynta video-yada adoo adeegsanaya AI tools (4–5 Maalmood).
• 📱 **WhatsApp Automation Business Bot**: Chatbot ganacsi oo 24/7 shaqeeya.
• 📞 **Telegram Automation Business Bot**: Bot wata flowchart iyo database.
• 🌐 **Web Design with AI Tools**: Dhis website casri ah adoo adeegsanaya AI (Free!).

📅 *Dooro koorsadaada oo ku dhufo [Ballan Qabso](#bookingSection) si aad toos ugu biirto!*"""

    # 6. Booking & Contact
    if any(k in user_lower for k in ["booking", "ballan", "xiriir", "contact", "la kulan", "caawin", "mentorship", "mohamed"]):
        return """📅 **Ballan Live ah & Xiriir Toos ah (Live Booking):**

Waxaad si toos ah ula xiriiri kartaa **Mohamed Yasin**:
• 📅 **Live Booking Form:** Guji tab-ka [Ballan Live ah](#bookingSection) ee bogga si aad u doorato taariikhda iyo waqtiga.
• 📱 **WhatsApp:** [+1 (587) 306-4137](https://wa.me/15873064137)
• 📧 **Email:** `Suxufi34@gmail.com`
• 📍 **Goobta:** Edmonton, Alberta, Canada 🇨🇦 & Online Global
• 🔗 **LinkedIn:** [linkedin.com/in/mfaratoon](https://www.linkedin.com/in/mfaratoon)
• 📺 **YouTube:** [youtube.com/@Mfaratoon](https://www.youtube.com/@Mfaratoon)"""

    # 7. Career Quiz
    if any(k in user_lower for k in ["quiz", "quize", "xirfad", "ii raadi", "dooro", "talo", "i haga"]):
        return """🎯 **Quiz: Ii Raadi Shaqada Ku Habboon (Career Matching Quiz) 🧭**

Si aan kuugu helo shaqada kugu habboon, fadlan ka dooro 3-dan su'aalood:

1. 💼 **Qeybta aad rabto:**
   • 📊 Maamul & Xisaabaad | 📞 Customer Care & Iib | 🏥 Caafimaad & NGO
   • 📚 Waxbarasho & Macallin | 💻 IT & Farsamo | 📦 Logistics & Gaadiid

2. 📍 **Goobta aad joogto:**
   • 🇸🇴 Muqdisho | 🇸🇴 Hargeysa & Puntland | 🇰🇪 Nairobi | 🌐 Remote (Guriga)

3. 🎓 **Khibraddaada:**
   • 🌱 Ku cusub (Fresh Graduate) | 💼 1-3 Sano | 🏆 3+ Sano

*Ii soo qor tusaale: "Maamul, Muqdisho, Ku cusub", waxaana si toos ah kuugu soo saari doonaa shaqooyinka bannaan!* 🚀"""

    # 8. Dynamic Search Across Curated Live Jobs
    all_jobs = get_curated_somali_it_jobs()
    matched_jobs = []

    # Category and keyword matching
    keywords_found = []
    category_tokens = {
        "tech": ["it", "developer", "software", "web", "python", "react", "code", "network", "cyber", "cloud", "support", "farsamo", "computer", "technician"],
        "finance": ["finance", "accounting", "xisaab", "maaliyad", "bank", "dahabshiil", "salaam", "admin", "hr", "maamul"],
        "sales": ["sales", "marketing", "iib", "customer", "call center", "hormuud", "telesom", "suuqgeyn"],
        "health": ["health", "nurse", "doctor", "nutrition", "nafaqo", "caafimaad", "ngo", "gargaar", "save the children", "srcs"],
        "education": ["teacher", "education", "macallin", "school", "dugsi", "waxbarasho", "kulan"],
        "logistics": ["logistics", "procurement", "warehouse", "gaadiid", "supply chain", "wfp", "badeecad"],
        "remote": ["remote", "online", "guriga"],
        "canada": ["canada", "edmonton", "calgary", "toronto"],
        "somalia": ["muqdisho", "hargeysa", "garoowe", "puntland", "kismaayo", "berbera", "baydhabo", "soomaaliya"]
    }

    matched_categories = []
    for cat, tokens in category_tokens.items():
        if any(t in user_lower for t in tokens):
            matched_categories.append(cat)
            keywords_found.append(cat)

    scored_jobs = []
    if matched_categories or any(w in user_lower for w in ["shaqo", "shaqooyin", "jobs", "fursad", "raadi", "fursado"]):
        for j in all_jobs:
            j_cat = j.get("category", "")
            j_title = j.get("title", "").lower()
            j_desc = j.get("description", "").lower()
            j_company = j.get("company", "").lower()
            j_loc = j.get("location", "").lower()

            score = 0
            for word in user_lower.split():
                cleaned_word = re.sub(r'[^a-zA-Z0-9]', '', word)
                if len(cleaned_word) >= 3 and cleaned_word in j_title:
                    score += 25
                elif len(cleaned_word) >= 3 and cleaned_word in j_company:
                    score += 10

            for cat in matched_categories:
                for tok in category_tokens.get(cat, []):
                    if tok in j_title:
                        score += 15
                    if tok in j_company:
                        score += 5
                    if tok in j_desc:
                        score += 2
                if j_cat == cat:
                    score += 10

            if "remote" in user_lower and "remote" in j_loc:
                score += 10
            if "muqdisho" in user_lower and "muqdisho" in j_loc:
                score += 10
            if "hargeysa" in user_lower and "hargeysa" in j_loc:
                score += 10
            if "kenya" in user_lower and "kenya" in j_loc:
                score += 10
            if "canada" in user_lower and "canada" in j_loc:
                score += 10

            if not matched_categories:
                score = 1

            if score > 0:
                scored_jobs.append((score, j))

        scored_jobs.sort(key=lambda x: x[0], reverse=True)
        matched_jobs = [item[1] for item in scored_jobs]

    if matched_jobs:
        selected_jobs = matched_jobs[:3]
        results_text = "💼 **Fursadaha Shaqo ee Ku Habboon Codsigaaga:**\n\n"
        for idx, j in enumerate(selected_jobs, 1):
            results_text += f"{idx}. 🏢 **{j.get('title')}** — *{j.get('company')}*\n"
            results_text += f"   📍 **Goobta:** {j.get('location')} | ⏱️ {j.get('job_type', 'Full-time')}\n"
            desc = j.get('description', '')
            if len(desc) > 130:
                desc = desc[:130] + "..."
            results_text += f"   📝 {desc}\n"
            results_text += f"   👉 [Codso Shaqadan (Direct Link)]({j.get('job_url')})\n\n"

        results_text += "🔗 **Bogagga & Xiriirrada Dheeraadka ah:**\n"
        results_text += "• [SomaliJobs (somalijobs.com)](https://somalijobs.com) | [ReliefWeb Somalia](https://reliefweb.int/jobs?country=216) | [Indeed Canada](https://ca.indeed.com)\n"
        results_text += "• 📱 [Eeg Dhammaan Shaqooyinka ee Boggan](#jobsSection) | [Soo Degso CV ATS ah (PDF)](/download/resume)\n\n"
        results_text += "💡 *Qor magac shaqo oo kale ama qor 'links' si aad u hesho dhammaan bogagga shaqada!*"
        return results_text

    # 9. Smart Conversational Guidance (NEVER repeats the greeting loop!)
    featured_jobs = all_jobs[:3]
    reply = "Salamaat walaal! Waxaan ahay **Kaaliyaha Shaqo Baahiye & Isbar AI** 🚀\n\n"
    reply += "Waxaan diyaar kuugu ahay inaan toos kuugu raadiyo shaqooyin, kugu xiro shirkadaha bannaan, ama kugu caawiyo diyaarinta CV ATS ah.\n\n"
    reply += "✨ **Fursadaha Maanta Ugu Caansan ee Diyaar ah:**\n"
    for idx, j in enumerate(featured_jobs, 1):
        reply += f"{idx}. 💼 **{j.get('title')}** ({j.get('company')}) — [Codso Halkan]({j.get('job_url')})\n"
    
    reply += "\n💡 **Si degdeg ah wax u baaro:**\n"
    reply += "• Qor xirfaddaada (tusaale: *IT, Maamul, Caafimaad, Iib, Remote*) si aad shaqooyin u hesho.\n"
    reply += "• Qor *'links'* si aad u hesho dhammaan bogagga shaqooyinka laga raadsado.\n"
    reply += "• Qor *'cv'* si aad u hesho talooyinka ATS iyo PDF Resume-gaaga.\n"
    reply += "• Qor *'quiz'* si nidaamku kuugu doorto shaqada kugu habboon."
    return reply

def get_career_ai_response(user_message: str) -> str:
    user_lower = user_message.lower().strip()
    
    system_instruction = """Waxaad tahay 'Kaaliyaha AI ee Shaqo Baahiye' (Dhammaan Fursadaha Shaqo, Bogagga Shaqada & Akadeemiyada Isbar).
Waxaad caawisaa dhalinyarada Soomaaliyeed ee raadinaya shaqooyinka (Soomaaliya, Bariga Afrika, Remote, iyo Kanada).
Marka aad shaqooyin xusayso, sii xiriirrada tooska ah (links) sida SomaliJobs, ReliefWeb, UNJobs, Indeed, iyo isbar-ai.com.
U jawaab si kooban, dhiirrigelin leh, oo waxtar leh."""

    # 1. Try Gemini API first (Generous Free Tier)
    gemini_reply = query_gemini_api(user_message, system_instruction)
    if gemini_reply:
        return gemini_reply

    # 2. Try Groq API (Fast Llama 3)
    groq_reply = query_groq_api(user_message, system_instruction)
    if groq_reply:
        return groq_reply

    # 3. Try OpenAI API
    client = get_openai_client()
    if client:
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=650,
                temperature=0.6,
                timeout=10
            )
            return resp.choices[0].message.content
        except Exception:
            pass

    # 4. Smart Local Career Engine (Runs reliably offline / 0 credits, with real links & search)
    return smart_local_career_engine(user_message)

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
    # Fallback to curated Somali IT jobs
    jobs = get_curated_somali_it_jobs()
    for j in jobs:
        j["is_applied"] = j.get("job_url") in applied_links
        ai_data = generate_tailored_materials(j)
        j["match_score"] = ai_data.get("match_score", "96%")
        j["match_reason"] = ai_data.get("match_reason", "")
        j["key_pitch"] = ai_data.get("key_pitch", "")
        j["cover_letter"] = ai_data.get("cover_letter", "")
    return jsonify({"status": "success", "jobs": jobs, "cached": False})

@app.route("/api/search", methods=["POST"])
def search_jobs():
    data = request.json or {}
    term = data.get("term", "IT Support")
    location = data.get("location", "Soomaaliya (Muqdisho & Hargeysa)")
    is_remote = bool(data.get("remote", False))
    limit = int(data.get("limit", 5))
    user_profile = data.get("user_profile")

    client = get_openai_client()
    applied_links = load_applied_links()
    loc_lower = location.lower()

    filtered_jobs = []

    # Scrape if Canada/USA or Remote is specified
    if any(c in loc_lower for c in ["canada", "edmonton", "toronto", "calgary", "usa"]):
        try:
            raw_jobs = scrape_jobs(
                site_name=["indeed", "zip_recruiter", "glassdoor"],
                search_term=term,
                location=location,
                results_wanted=limit * 2,
                hours_old=168,
                country_indeed="Canada" if "canada" in loc_lower or "edmonton" in loc_lower else "USA",
                is_remote=is_remote
            )
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
                        "job_type": str(row.get("job_type", "Full-time / Remote")),
                        "is_applied": job_url in applied_links
                    }
                    ai_data = generate_tailored_materials(job_item, client, user_profile)
                    job_item["match_score"] = ai_data.get("match_score", "95%")
                    job_item["match_reason"] = ai_data.get("match_reason", "")
                    job_item["key_pitch"] = ai_data.get("key_pitch", "")
                    job_item["cover_letter"] = ai_data.get("cover_letter", "")
                    filtered_jobs.append(job_item)
                    if len(filtered_jobs) >= limit:
                        break
        except Exception as e:
            print(f"Scraper notice: {e}")

    # For Somalia, East Africa, Remote, or as rich fallback, supply top verified Somali IT positions
    if len(filtered_jobs) < limit:
        curated = get_curated_somali_it_jobs(term=term, location=location, is_remote=is_remote)
        for c_job in curated:
            if any(j["title"].lower() == c_job["title"].lower() for j in filtered_jobs):
                continue
            c_job["is_applied"] = c_job.get("job_url") in applied_links
            ai_data = generate_tailored_materials(c_job, client, user_profile)
            c_job["match_score"] = ai_data.get("match_score", "96%")
            c_job["match_reason"] = ai_data.get("match_reason", "")
            c_job["key_pitch"] = ai_data.get("key_pitch", "")
            c_job["cover_letter"] = ai_data.get("cover_letter", "")
            filtered_jobs.append(c_job)
            if len(filtered_jobs) >= limit:
                break

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(filtered_jobs, f, indent=2)

    return jsonify({"status": "success", "jobs": filtered_jobs, "count": len(filtered_jobs)})

@app.route("/api/assess", methods=["POST"])
def assess_candidate():
    data = request.json or {}
    field = data.get("field", "Computer Science & IT Support")
    skills = data.get("skills", [])
    experience = data.get("experience", "Arday / Qalin-jebiye Cusub")
    location = data.get("location", "Soomaaliya (Muqdisho & Hargeysa)")
    resume_text = data.get("resume_text", "").strip()
    name = data.get("name", "").strip() or "Qalin-jebiye IT"

    score = 93
    if len(skills) >= 4:
        score += 3
    if resume_text:
        score = min(98, score + 3)

    keyword_map = {
        "Computer Science & IT Support": "IT Support",
        "Software & Web Development": "web developer",
        "Network Administration & Systems": "network technician",
        "AI Automation & Chatbot Engineering": "AI automation",
        "Database & Data Analysis": "database administrator",
        "Computer Instruction & Digital Literacy": "computer instructor"
    }
    recommended_search = keyword_map.get(field, "IT Support")

    skills_joined = ", ".join(skills[:3]) if skills else "Computer Hardware, Network & Systems"
    advice = f"Walaal {name}, waxaad leedahay awood aad u fiican xagga {field}. Xirfadahaaga sida {skills_joined} waxay si buuxda u waafaqsan yihiin shuruudaha shirkadaha IT-ga ee {location}, Bariga Afrika, iyo fursadaha Remote-ka caalamiga ah."

    return jsonify({
        "status": "success",
        "readiness_score": f"{score}%",
        "field": field,
        "recommended_keyword": recommended_search,
        "advice": advice,
        "skills_analyzed": skills,
        "location": location
    })

@app.route("/api/chat", methods=["POST"])
def chat_assistant():
    data = request.json or {}
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "").strip() or request.remote_addr or "anon_session"

    # 1. Anti-spam, media, and nonsense check (Only text allowed!)
    is_spam, spam_reason = is_spam_or_invalid(message)
    if is_spam:
        current_count = CHAT_SESSIONS.get(session_id, 0)
        return jsonify({
            "status": "spam_blocked",
            "reply": spam_reason,
            "remaining": max(0, MAX_SESSION_MESSAGES - current_count),
            "count": current_count
        }), 400

    # 2. Strict 30-message limit per session
    allowed, remaining, count = check_session_limit(session_id)
    if not allowed:
        return jsonify({
            "status": "limit_reached",
            "reply": "⚠️ Waxaad gaartay xadka 30-ka fariimood ee kulankan si loo ilaaliyo khayraadka nidaamka. Haddii aad buugaag doonayso, fadlan toos ugu biir warsidaha Dhegeyso Buug: https://dhegeysobuug.substack.com/ (waxaad helaysaa 2 buug oo bilaash ah oo si automatic ah inbox-kaaga ugu soo dhacaya marka aad subscribe gareyso). Haddii aad rabto ballan live ah ama caawin toos ah oo aad la yeelato Mohamed Yasin, isticmaal qeybta 'Ballan Live ah' ama WhatsApp: +1 (587) 306-4137.",
            "remaining": 0,
            "count": count
        }), 429

    # 3. Process reply
    reply = get_career_ai_response(message)
    return jsonify({
        "status": "success",
        "reply": reply,
        "remaining": remaining,
        "count": count
    })

@app.route("/api/telegram_webhook", methods=["GET", "POST"])
def telegram_webhook():
    if request.method == "GET":
        return jsonify({"status": "active", "service": "Telegram Webhook for @Baahiyebot"}), 200

    try:
        update = request.get_json(force=True, silent=True)
        if not update:
            return jsonify({"ok": False, "message": "No payload"}), 400

        from telegram_career_bot import process_message, process_callback_query
        if "message" in update:
            process_message(update["message"])
        elif "callback_query" in update:
            process_callback_query(update["callback_query"])

        return jsonify({"ok": True}), 200
    except Exception as e:
        print(f"[!] Error in telegram_webhook: {e}", flush=True)
        return jsonify({"ok": False, "error": str(e)}), 200

@app.route("/api/book_session", methods=["POST"])
def book_session():
    data = request.json or {}
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    service = data.get("service", "1-on-1 Mentorship / Consultation")
    preferred_date = data.get("date", "")
    preferred_time = data.get("time", "")
    notes = data.get("notes", "").strip()

    if not name or not phone:
        return jsonify({"status": "error", "message": "Fadlan soo geli magacaaga iyo taleefankaaga / WhatsApp-kaaga!"}), 400

    if notes:
        is_spam, reason = is_spam_or_invalid(notes)
        if is_spam:
            return jsonify({"status": "error", "message": reason}), 400

    booking_id = f"BK-{random.randint(10000, 99999)}"
    record = {
        "booking_id": booking_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "name": name,
        "phone": phone,
        "email": email,
        "service": service,
        "date": preferred_date,
        "time": preferred_time,
        "notes": notes,
        "status": "Confirmed"
    }
    save_booking(record)

    wa_msg = f"Salamaat Mohamed! Waxaan ahay {name}. Waxaan xaqiijinayaa Ballantayda Live-ka ah (#{booking_id}). Adeegga: {service}. Taariikhda: {preferred_date} {preferred_time}."
    wa_link = f"https://wa.me/15873064137?text={urllib.parse.quote(wa_msg)}"

    return jsonify({
        "status": "success",
        "booking_id": booking_id,
        "record": record,
        "whatsapp_link": wa_link,
        "message": f"Ballantaada (#{booking_id}) si guul leh ayaa loo diiwaangeliyey!"
    })

@app.route("/api/bookings")
def get_bookings():
    return jsonify({"status": "success", "bookings": load_bookings()})

@app.route("/api/mark_applied", methods=["POST"])
def mark_applied():
    data = request.json or {}
    job_url = data.get("job_url")
    if job_url:
        save_applied_link(job_url)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "No job_url provided"}), 400

def generate_resume_pdf(output_path: Path):
    """Generates a professional, complete 1-page ATS resume for Mohamed Yasin."""
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output_path), pagesize=letter, leftMargin=36, rightMargin=36, topMargin=32, bottomMargin=32)
    
    title_style = ParagraphStyle('RTitle', fontName='Helvetica-Bold', fontSize=16, leading=19, textColor=colors.HexColor('#0b132b'), alignment=1)
    sub_style = ParagraphStyle('RSub', fontName='Helvetica-Bold', fontSize=9.5, leading=12, textColor=colors.HexColor('#0284c7'), alignment=1)
    contact_style = ParagraphStyle('RContact', fontName='Helvetica', fontSize=8.5, leading=11, textColor=colors.HexColor('#475569'), alignment=1)
    sec_head = ParagraphStyle('RSecHead', fontName='Helvetica-Bold', fontSize=10.5, leading=13, textColor=colors.HexColor('#0b132b'), spaceBefore=5, spaceAfter=2)
    body_style = ParagraphStyle('RBody', fontName='Helvetica', fontSize=8.5, leading=11.5, textColor=colors.HexColor('#1e293b'))
    bullet_style = ParagraphStyle('RBullet', fontName='Helvetica', fontSize=8.2, leading=10.8, textColor=colors.HexColor('#334155'), leftIndent=12)
    job_head = ParagraphStyle('RJobHead', fontName='Helvetica-Bold', fontSize=9, leading=11, textColor=colors.HexColor('#0f172a'))

    elements = []
    elements.append(Paragraph('MOHAMED YASIN', title_style))
    elements.append(Spacer(1, 2))
    elements.append(Paragraph('Dynamic IT Educator &bull; Computer Systems Specialist &bull; AI Automation Trainer', sub_style))
    elements.append(Spacer(1, 2))
    elements.append(Paragraph('Edmonton, AB, Canada &bull; +1 (587) 306-4137 &bull; Suxufi34@gmail.com &bull; linkedin.com/in/mfaratoon', contact_style))
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#0284c7'), spaceAfter=5, spaceBefore=2))

    elements.append(Paragraph('PROFESSIONAL SUMMARY', sec_head))
    elements.append(Paragraph('Dedicated and results-driven IT Educator, Computer Support Specialist, and AI Automation Trainer with extensive international teaching and systems instruction experience. Proven track record in IT literacy instruction, technical troubleshooting, systems administration, and AI chatbot development, with an online reach exceeding 100,000 Somali students.', body_style))
    elements.append(Spacer(1, 4))

    elements.append(Paragraph('CORE TECHNICAL EXPERTISE', sec_head))
    skills_text = '<b>IT & Systems:</b> Hardware Diagnostics, Windows 11/10, MacOS, Linux, TCP/IP Networking, DNS/DHCP, IT Security Basics.<br/><b>AI & Automation:</b> Prompt Engineering, Custom Chatbots (Typebot, ManyChat, Botpress, Paal AI, N8n), Workflow Automation.<br/><b>Instruction & Productivity:</b> Microsoft Office 365, Google Workspace, Adobe Photoshop, OBS Studio, Bilingual Technical Training.'
    elements.append(Paragraph(skills_text, body_style))
    elements.append(Spacer(1, 4))

    elements.append(Paragraph('PROFESSIONAL EXPERIENCE', sec_head))
    elements.append(Paragraph('<b>Founder & AI Automation Lead</b> | <i>Somalibotmaster & Somali Library</i> &nbsp;&bull;&nbsp; 12/2023 &ndash; Present', job_head))
    elements.append(Paragraph('&bull; Architected conversational AI chatbots and automated workflow pipelines for Somali educational and job matching platforms.', bullet_style))
    elements.append(Paragraph('&bull; Author & Editor of modern tech publications including <i>Isbar Computer</i>, <i>Isbar Programming</i>, and <i>Isbar AI</i>.', bullet_style))
    elements.append(Paragraph('&bull; Conducted live remote training cohorts in AI tools, video editing, and chatbot deployment for 500+ participants.', bullet_style))
    elements.append(Spacer(1, 3))

    elements.append(Paragraph('<b>Computer Systems & Digital Literacy Instructor</b> | <i>International Community Education Center</i> &nbsp;&bull;&nbsp; 03/2017 &ndash; 01/2021', job_head))
    elements.append(Paragraph('&bull; Delivered foundational and advanced IT training (Computer Basics, MS Office, photo/video editing) to multicultural cohorts.', bullet_style))
    elements.append(Paragraph('&bull; Developed hands-on technical curriculum enabling students to gain essential employment-ready digital competencies.', bullet_style))
    elements.append(Paragraph('&bull; Mentored diverse learners in technology adoption, operating systems navigation, and hardware diagnostics.', bullet_style))
    elements.append(Spacer(1, 3))

    elements.append(Paragraph('<b>Website Content & Digital Media Coordinator</b> | <i>Somalinfo.com</i> &nbsp;&bull;&nbsp; 11/2014 &ndash; 05/2015', job_head))
    elements.append(Paragraph('&bull; Administered digital publishing workflows, site traffic analytics, and multimedia asset deployment.', bullet_style))
    elements.append(Spacer(1, 4))

    elements.append(Paragraph('EDUCATION & PROFESSIONAL CREDENTIALS', sec_head))
    elements.append(Paragraph('&bull; <b>Google IT Support Professional Certificate</b> &ndash; Google / Coursera (Networking, Security, OS, System Admin)', bullet_style))
    elements.append(Paragraph('&bull; <b>Bachelor of Arts in Media & Mass Communication</b> &ndash; African Virtual University (AVU), 2009', bullet_style))
    elements.append(Paragraph('&bull; <b>AI Automation & Conversational Bot Architect Credentials</b> &ndash; Industry Specialized Programs', bullet_style))

    doc.build(elements)
    return output_path

@app.route("/download/resume")
def download_resume():
    try:
        target_path = PDF_RESUME_PATH
        # Also check assets backup
        assets_backup = BASE_DIR / "assets" / "Mohamed_Yasin_Resume.pdf"
        
        if not target_path.exists() or target_path.stat().st_size < 3500:
            if assets_backup.exists() and assets_backup.stat().st_size >= 3500:
                target_path = assets_backup
            else:
                generate_resume_pdf(target_path)
                
        return send_file(
            target_path,
            as_attachment=True,
            download_name="Mohamed_Yasin_Resume.pdf",
            mimetype="application/pdf"
        )
    except Exception as e:
        fallback_path = OUTPUT_FOLDER / "Mohamed_Yasin_Resume.pdf"
        generate_resume_pdf(fallback_path)
        return send_file(
            fallback_path,
            as_attachment=True,
            download_name="Mohamed_Yasin_Resume.pdf",
            mimetype="application/pdf"
        )

@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory(BASE_DIR / "assets", filename)

def start_server():
    port = int(os.environ.get("PORT", 5050))
    print(f"\n=======================================================")
    print(f"   Shaqo Raadiyaha Dhalinyarada Soomaaliyeed ee IT-ga")
    print(f"   Listening on http://0.0.0.0:{port}...")
    print(f"=======================================================\n")
    if not os.environ.get("DOCKER") and not os.environ.get("VERCEL"):
        webbrowser.open(f"http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    start_server()
