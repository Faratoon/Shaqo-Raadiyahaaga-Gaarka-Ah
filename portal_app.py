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
from flask import Flask, render_template, request, jsonify, send_file
from jobspy import scrape_jobs
from openai import OpenAI

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent

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
Candidate: Mohamed Yasin Mohamoud (Faratoon)
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
        return True, "⚠️ Fadlan soo qor su'aal ama codsi cad oo dhab ah, ka fogow xarfaha isku xiga ee spam-ka ah."

    # 3. Gibberish / keyboard mash detection
    words = text_clean.split()
    for w in words:
        if len(w) > 35 and not w.startswith("http"):
            return True, "⚠️ Qoraalkaaga waxaa ku jira ereyo aad u dhaadheer oo aan la fahmi karin. Fadlan soo qor hadal macno leh."
        if len(w) >= 9 and not re.search(r"[aeiouy]", w, re.IGNORECASE) and not w.isdigit():
            return True, "⚠️ Fadlan soo qor fariin macno leh oo la fahmi karo. Hadallada bilaa micnaha ah (spam) lama ogola."

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

def generate_tailored_materials(job, client=None, user_profile=None):
    company = job.get('company', 'Hiring Team')
    title = job.get('title', 'Position')
    location = job.get('location', 'Edmonton, AB')

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
# AI Career & Course Chatbot Engine
# -------------------------------------------------------------
def get_career_ai_response(user_message: str) -> str:
    user_lower = user_message.lower().strip()
    client = get_openai_client()

    if client:
        system_instruction = """
Waxaad tahay 'Kaaliyaha Rasmiga ah ee Mohamed Yasin Mohamoud' (Shaqo Raadiyaha & Koorsooyinka AI).
Waxaad ku hadashaa af-Soomaali aad u qurux badan, dhiirigelin leh, xirfadaysan.
Waxaad haysataa aqoon buuxda oo ku saabsan:
1. BUUGAAGTA CASRIGA AH EE ISBAR (Qore/Editor: Yahye Cabdirahmaan & Mohamed Faratoon):
   - ISBAR COMPUTER: 89 pages, $5. (Computer Basics, Software/Hardware, Windows 11, Mac OS, MS Office, Photoshop, OBS Studio).
   - ISBAR PROGRAMMING: 177 pages, $5. (Basics of Programming, Web Dev Basics, Programming Languages, Database, Code Editor & IDE).
   - ISBAR AI (Artificial Intelligence) BASIC: 189 pages, $7. (Taariikhda AI, AI & Waxbarashada, AI & Shaqooyinka, AI & Graphic Design, AI & Ganacsiga).
   - ISBAR ChatGPT - Prompts Basic: 87 pages, FREE ($0!). (Waa maxay ChatGPT?, Sida loola xiriiro si hufan, Shaqooyinka, Waxbarashada, Ganacsiga).
2. KOORSOOYINKA AUTOMATION-KA & MADALLADA CHATBOT-YADA:
   - Madallada: Chatbase, Botfather Telegram, Chatfuel, Manychat, N8n, Botsail, Jotform, Botpress, Paal AI, Vibe Coding, Typebot.
   - Waxaan dhisnaa custom AI chatbots, knowledge bases, flowcharts, iyo website automation.
3. HAD DIYADDA GAARKA AH (SPECIAL OFFER):
   - Qof kasta oo buugaagta iibsada waxaan ugu raacinaynaa Mid ka mid ah Koorsooyinka Automation-ka oo BILAASH ah!
4. KOORSOOYINKA LACAGTA & BILAASHKA:
   - Paid: AI ChatGPT – Data Writing ($24 / Qiimo-dhimista Ardayda: $10, Duration: 4-5 days).
   - Free: AI Video Editing, WhatsApp Business Bot, Telegram Business Bot, Messenger Business Bot, Instagram Business Bot, Web Design with AI Tools (all 4-5 days, Free for students).
5. LIVE BOOKING & MENTORSHIP:
   - Ardaydu waxay toos u qabsan karaan ballan 1-on-1 ah iyagoo adeegsanaya qeybta 'Live Booking' ama WhatsApp: +1 (587) 306-4137.
6. SHAQO RAADINTA KANADA:
   - ATS-friendly CV, STAR interview method, iyo Canadian Cover Letters.
U jawaab si kooban oo faahfaahsan. Kaliya qoraal ayaa la ogol yahay.
"""
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=650,
                temperature=0.6,
                timeout=12
            )
            return resp.choices[0].message.content
        except Exception:
            pass

    # Built-in Knowledge Base (Fast Local Fallback)
    if any(k in user_lower for k in ["buug", "book", "isbar", "qiimaha", "pages", "bogag"]):
        return """📚 **Buugaagta Casriga ah ee 'Isbar' (Macallin La'aan):**

1. 💻 **ISBAR COMPUTER** ($5 Kaliya | 89 Pages):
   • Qore: Yahye Cabdirahmaan • Editor: Mohamed Faratoon
   • Waxa ku jira: Computer Basics, Software & Hardware, Windows 11, Mac OS, MS Office, Adobe Photoshop, OBS Studio.

2. 👨‍💻 **ISBAR PROGRAMMING** ($5 Kaliya | 177 Pages):
   • Qore: Yahye Abdirahmaan • Editor: Mohamed Faratoon
   • Waxa ku jira: Basics of Programming, Web Dev Basics, Programming Languages, Database, Code Editor & IDE.

3. 🧠 **ISBAR AI (Artificial Intelligence) BASIC** ($7 Kaliya | 189 Pages):
   • Qore: Yahye Abdirahmaan / Mohamed Faratoon
   • Waxa ku jira: Taariikhda AI, AI & Waxbarashada, AI & Shaqooyinka, AI & Graphic Design, AI & Ganacsiga.

4. 🤖 **ISBAR ChatGPT - Prompts Basic** (🎁 FREE / 100% Bilaash! | 87 Pages):
   • Qore: Mohamed Faratoon • Editor: Yahya Abdirahman
   • Waxa ku jira: Waa maxay ChatGPT?, Sida loola xiriiro si hufan, Shaqooyinka, Waxbarashada, Ganacsiga.

🎉 **Fursad Gaar ah:** Qof kasta oo buug iibsada wuxuu ku helayaa Mid ka mid ah Koorsooyinka Automation-ka oo **BILAASH** ah!"""

    elif any(k in user_lower for k in ["koorso", "course", "automation", "data writing", "video editing", "whatsapp", "telegram", "free", "bilaash"]):
        return """🎓 **Koorsooyinka AI Automation & Xirfadaha Casriga ah:**

🔹 **Paid Course (Qiimo-dhimis Gaar ah):**
• **AI ChatGPT – Data Writing 📝**: Baro curinta nuxurka, ganacsiga, iyo qorista shaqooyinka.
  - Waqtiga: 4–5 Maalmood
  - Qiimaha: $24 (Qiimo-dhimista Ardayda: **$10 Kaliya!**)

🎓 **Free Courses (100% Bilaash Ardayda Sanadkan):**
• 🎥 **AI Video Editing**: Baro habaynta video-yada adoo adeegsanaya AI tools (4–5 Maalmood).
• 📱 **WhatsApp Automation Business Bot**: Dhis chatbot ganacsi oo 24/7 shaqeeya.
• 📞 **Telegram Automation Business Bot**: Bot wata flowchart iyo database.
• 💬 **Messenger Automation Business Bot**: Adeegga macaamiisha Facebook.
• 📸 **Instagram Automation Business Bot**: DM automation & leads.
• 🌐 **Web Design with AI Tools**: Dhis website casri ah adoo adeegsanaya HTML, CSS, & AI (Free!).

📅 *Dooro koorsadaada oo ku dhufo 'Ballan Qabso' si aad toos ugu biirto!*"""

    elif any(k in user_lower for k in ["platform", "chatbase", "botfather", "chatfuel", "manychat", "n8n", "botpress", "paal", "vibe coding", "typebot"]):
        return """🛠️ **Madallada Chatbot-yada & Automation-ka aan ku Tababarno:**

Waxaan bixinnaa aqoon aasaasi iyo mid sare oo ku saabsan dhisidda knowledge bases, flowcharts, iyo website automation:
• **Chatbase & Botpress**: Dhisida AI Chatbot aqoon buuxda u leh shirkadda/website-ka.
• **Botfather Telegram & Manychat**: Isku xirka bots-ka iibka iyo wada sheekeysiga macaamiisha.
• **N8n & Botsail**: Isku xirka APIs iyo otomaatigga shaqada (Workflows).
• **Jotform & Typebot**: Forms casri ah oo interactive ah oo xogta qaada.
• **Paal AI & Vibe Coding**: AI coding degdeg ah iyo nidaamyada mustaqbalka.

*Ma rabtaa inaan chatbot ganacsigaaga kuu dhisno ama aan ku barno? Qabso ballan live ah!*"""

    elif any(k in user_lower for k in ["booking", "ballan", "xiriir", "contact", "la kulan", "faratoon", "caawin", "mentorship"]):
        return """📅 **Ballan Live ah & Xiriir Toos ah (Live Booking):**

Waxaad si toos ah ula xiriiri kartaa **Mohamed Yasin Mohamoud (Faratoon)**:
• 📅 **Live Booking Form:** Guji tab-ka **'Ballan Live ah'** ee bogga si aad u doorato taariikhda iyo waqtiga.
• 📱 **WhatsApp:** `+1 (587) 306-4137`
• 📧 **Email:** `Suxufi34@gmail.com`
• 📍 **Goobta:** Edmonton, Alberta, Canada 🇨🇦
• 🔗 **LinkedIn:** [linkedin.com/in/mfaratoon](https://www.linkedin.com/in/mfaratoon)
• 📺 **YouTube:** [youtube.com/User/MrFaratoon](https://www.youtube.com/User/MrFaratoon)

*Haddii aad tahay arday u baahan caawinaad CV, tababar koorso, ama talo shaqo, xor ayaad u tahay inaad nala soo xiriirto!*"""

    elif any(k in user_lower for k in ["cv", "resume", "warqad", "habeeyo", "ats"]):
        return """📄 **Talooyinka Dahabiga ah ee Diyaarinta CV Casri ah (ATS-Friendly):**

1. **Qaab-dhismeedka Toosan (Clean Layout):**
   * Ka fogow sawirrada iyo naqshadaha xad-dhaafka ah sababtoo ah ATS ma akhrin karaan.
2. **Qeybaha Ugu Muhiimsan:**
   * **Professional Summary:** 3-4 sadar oo qeexaya qiimahaaga.
   * **Core Skills:** Xirfadahaaga farsamo iyo kuwa maamul.
   * **Projects / Volunteering:** Gaar ahaan ardayda, ku dar mashaariicdii jaamacadda iyo tabarruca.
   * **Education & Certifications:** Shahaadooyinka rasmiga ah (Jaamacad, Google IT Support).
3. **Keywords:** Ku dar ereyada xayeysiiska shaqada si score-kaagu u sarreeyo."""

    elif any(k in user_lower for k in ["wareysi", "interview", "su'aal", "suaal", "star"]):
        return """🎯 **Sida Loogu Guuleysto Wareysiga Shaqada (STAR Method):**

* **S (Situation):** Sharax xaaladdii ama caqabaddii jirtay.
* **T (Task):** Maxaa lagaa rabay inaad xalliso?
* **A (Action):** Tallaabooyinkee ayaad adigu shakhsiyan qaadday?
* **R (Result):** Maxaa ka dhashay? (Adeegso tirooyin iyo guulo dhab ah).

💡 *Talo: Muuji kalsooni, xiriir wanaagsan, iyo sida aad dhibaatada u xalliso.*"""

    else:
        return """Salamaat walaal! 👋 Waxaan ahay **Kaaliyaha Rasmiga ah ee Mohamed Yasin (Faratoon)**.

Waxaan diyaar kuugu ahay inaan kaa caawiyo:
1. 📚 **Buugaagta Isbar (Computer $5, Programming $5, AI $7, ChatGPT FREE)**
2. 🤖 **Koorsooyinka AI Automation & Chatbots (WhatsApp, Telegram, N8n, Typebot)**
3. 🎁 **Koorsooyinka Bilaashka ah & Qiimo-dhimista Ardayda ($10)**
4. 📅 **Live Booking & Mentorship 1-on-1 ah**
5. 💼 **Shaqo Raadinta Kanada, CV ATS ah, iyo Wareysiyada**

*Ii soo qor su'aashaada gaarka ah! (Fadlan qoraal kaliya soo dir - sawirrada lama ogola)* 🚀"""

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
            "reply": "⚠️ Waxaad gaartay xadka 30-ka fariimood ee kulankan. Si aad u hesho caawin toos ah ama ballan gaar ah la yeelato Mohamed Faratoon, fadlan isticmaal qeybta 'Live Booking' ama toos ugala xiriir WhatsApp: +1 (587) 306-4137.",
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

    # Check for spam in notes
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
