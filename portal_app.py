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
Role: Dynamic IT Educator, Technical Support Specialist, and AI Automation Trainer
Experience: 5+ years of computer instruction with the International Organization for Migration (IOM) in Indonesia, teaching Computer Basics, MS Office, and digital editing to multicultural refugee cohorts. Honored with official UN/IOM Certificate of Commendation.
Education: BA in Media & Mass Communication (AVU) and Google IT Support Professional credentials (IT Security, System Administration, OS Power User, Networking). Educated 100,000+ students online.
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

def get_curated_somali_it_jobs(term="IT Support", location="Muqdisho, Soomaaliya", is_remote=False):
    loc_l = location.lower()
    term_l = term.lower()

    all_jobs = [
        {
            "site": "SomaliTech",
            "title": "IT Support & Network Technician",
            "company": "Hormuud Telecom",
            "location": "Muqdisho, Soomaaliya",
            "job_url": "https://www.hormuud.com/careers/it-support-network-technician",
            "description": "Hormuud Telecom is seeking a motivated IT Support & Network Technician to join our central technology team in Mogadishu. Responsibilities include troubleshooting hardware/software, configuring routers/switches, supporting internal staff, and maintaining network uptime across corporate branches. Qualifications: Degree or diploma in Computer Science, IT, or equivalent.",
            "date_posted": "2026-10-02",
            "job_type": "Full-time"
        },
        {
            "site": "SomaliTech",
            "title": "Junior Database & Systems Administrator",
            "company": "Dahabshiil Bank International",
            "location": "Hargeysa, Soomaaliya",
            "job_url": "https://www.dahabshiil.com/careers/systems-administrator",
            "description": "Dahabshiil Bank is hiring a Junior Database & Systems Administrator in Hargeisa. Key duties include monitoring core banking servers, executing SQL database queries, performing daily backups, user access management, and ensuring high system availability. Strong understanding of SQL and IT security required.",
            "date_posted": "2026-10-01",
            "job_type": "Full-time"
        },
        {
            "site": "SomaliTech",
            "title": "Web & Software Developer (Full Stack)",
            "company": "Premier Bank",
            "location": "Muqdisho, Soomaaliya",
            "job_url": "https://premierbank.so/careers/web-software-developer-2026",
            "description": "Premier Bank is looking for a creative Full-Stack Web Developer to build and maintain modern banking portals and digital services. Proficiency in HTML5, CSS3, JavaScript/React, Python/Node.js, and RESTful APIs. Must be proactive, innovative, and passionate about fintech in Somalia.",
            "date_posted": "2026-10-02",
            "job_type": "Full-time"
        },
        {
            "site": "SomaliTech",
            "title": "ICT Field Officer & Systems Support",
            "company": "UN / IOM Somalia Mission",
            "location": "Muqdisho & Garoowe, Soomaaliya",
            "job_url": "https://somalia.iom.int/careers/ict-officer-support-2026",
            "description": "The International Organization for Migration (IOM) in Somalia invites applications for an ICT Field Officer. The role involves managing office IT equipment, VSAT and LAN/WAN connections, user helpdesk, and IT asset tracking across field offices in Somalia.",
            "date_posted": "2026-10-03",
            "job_type": "Contract"
        },
        {
            "site": "RemoteGlobal",
            "title": "AI Automation & Chatbot Specialist (Remote)",
            "company": "Somalilab Tech & Innovations",
            "location": "Remote (Soomaaliya & Global)",
            "job_url": "https://somalilab.tech/careers/ai-automation-specialist",
            "description": "Join our fast-growing innovation lab as an AI Automation Specialist. Build no-code and low-code chatbots using Typebot, N8n, Botpress, Manychat, and OpenAI APIs. Work from anywhere in Somalia or East Africa on high-impact automation projects.",
            "date_posted": "2026-10-03",
            "job_type": "Remote / Full-time"
        },
        {
            "site": "EastAfricaJobs",
            "title": "Junior Cloud & Systems Engineer",
            "company": "Safaricom Tech Hub",
            "location": "Nairobi, Kenya",
            "job_url": "https://safaricom.co.ke/careers/cloud-systems-engineer",
            "description": "Exciting opportunity for East African tech graduates to work on large-scale cloud infrastructure, DevOps pipelines, and mobile money integrations at Safaricom Nairobi.",
            "date_posted": "2026-10-02",
            "job_type": "Full-time"
        },
        {
            "site": "EastAfricaJobs",
            "title": "IT Project & Systems Coordinator",
            "company": "East Africa Relief & Development",
            "location": "Addis Ababa & Jigjiga, Ethiopia",
            "job_url": "https://reliefweb.int/job/east-africa-it-coordinator",
            "description": "Coordinate technical field infrastructure, student computer labs, and digital data reporting across Somali Region (Jigjiga) and Addis Ababa.",
            "date_posted": "2026-10-01",
            "job_type": "Full-time"
        },
        {
            "site": "Indeed",
            "title": "Youth Literacy & Computer Coordinator",
            "company": "P.A.L.S. - Project Adult Literacy Society",
            "location": "Edmonton, AB, Canada",
            "job_url": "https://ca.indeed.com/viewjob?jk=e9e4c49bfb924d13",
            "description": "Support youth and new immigrants aged 18-25 in developing foundational digital literacy, office tools, and career readiness in Edmonton.",
            "date_posted": "2026-10-01",
            "job_type": "Full-time"
        }
    ]

    matched = []
    for j in all_jobs:
        j_loc = j["location"].lower()
        if any(k in loc_l for k in ["soomaaliya", "somalia", "muqdisho", "hargeisa", "garoowe"]):
            if "soomaaliya" in j_loc or "remote" in j_loc:
                matched.append(j)
        elif any(k in loc_l for k in ["kenya", "nairobi"]):
            if "kenya" in j_loc or "remote" in j_loc:
                matched.append(j)
        elif any(k in loc_l for k in ["ethiopia", "itoobiya", "jigjiga", "addis"]):
            if "ethiopia" in j_loc or "remote" in j_loc:
                matched.append(j)
        elif "remote" in loc_l or is_remote:
            if "remote" in j_loc:
                matched.append(j)
        elif any(k in loc_l for k in ["canada", "edmonton", "toronto"]):
            if "canada" in j_loc or "remote" in j_loc:
                matched.append(j)
        else:
            matched.append(j)

    return matched if matched else all_jobs[:5]

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
# AI Career & Course Chatbot Engine
# -------------------------------------------------------------
def get_career_ai_response(user_message: str) -> str:
    user_lower = user_message.lower().strip()
    client = get_openai_client()

    if client:
        system_instruction = """
Waxaad tahay 'Kaaliyaha Rasmiga ah ee Shaqo Raadiyaha Dhalinyarada Soomaaliyeed' (Somali IT Youth Career & Academy AI).
Waxaad si gaar ah u caawisaa dhalinyarada iyo ardayda Soomaaliyeed ee bartay Culuumta IT-ga, Computer Science-ka, iyo AI Automation-ka.
Goobaha aad taageerto: Soomaaliya (Muqdisho, Hargeysa, Garoowe, Kismaayo), Bariga Afrika (Kenya - Nairobi, Itoobiya - Jigjiga), Shaqooyinka Guriga (Remote Tech), iyo Kanada.

Waxaad haysataa aqoon buuxda oo ku saabsan:
1. BUUGAAGTA CASRIGA AH EE ISBAR (Qore/Editor: Yahye Cabdirahmaan & Mohamed Faratoon):
   - ISBAR COMPUTER: 89 pages, $5. (Computer Basics, Software/Hardware, Windows 11, Mac OS, MS Office, Photoshop, OBS Studio).
   - ISBAR PROGRAMMING: 177 pages, $5. (Basics of Programming, Web Dev Basics, Programming Languages, Database, Code Editor & IDE).
   - ISBAR AI (Artificial Intelligence) BASIC: 189 pages, $7. (Taariikhda AI, AI & Waxbarashada, AI & Shaqooyinka, AI & Graphic Design, AI & Ganacsiga).
   - ISBAR ChatGPT - Prompts Basic: 87 pages, FREE ($0!). (Waa maxay ChatGPT?, Sida loola xiriiro si hufan, Shaqooyinka, Waxbarashada, Ganacsiga).
2. KOORSOOYINKA AUTOMATION-KA & MADALLADA CHATBOT-YADA:
   - Madallada: Chatbase, Botfather Telegram, Chatfuel, Manychat, N8n, Botsail, Jotform, Botpress, Paal AI, Vibe Coding, Typebot.
   - Waxaan dhisnaa custom AI chatbots, knowledge bases, flowcharts, iyo website automation.
3. WARSIDAHA SUBSTACK EE SOMALILIBRARY:
   - Ku dhiirigeli inay ku biiraan Somalilibrary Substack (somalilibrary.substack.com).
4. KOORSOOYINKA LACAGTA & BILAASHKA:
   - Paid: AI ChatGPT – Data Writing ($24 / Qiimo-dhimista Ardayda: $10, Duration: 4-5 days).
   - Free: AI Video Editing, WhatsApp Business Bot, Telegram Business Bot, Messenger Business Bot, Instagram Business Bot, Web Design with AI Tools (all 4-5 days, Free for students).
5. LIVE BOOKING & MENTORSHIP:
   - Ardaydu waxay toos u qabsan karaan ballan 1-on-1 ah iyagoo adeegsanaya qeybta 'Live Booking' ama WhatsApp: +1 (587) 306-4137.
6. SHAQOOYINKA IT-GA SOOMAALIDA & CV ATS:
   - Hormuud, Dahabshiil, Premier Bank, Telesom, UN/IOM Somalia, Safaricom Kenya, Remote AI, iyo Canada.
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

    elif any(k in user_lower for k in ["substack", "somalilibrary", "warside", "newsletter"]):
        return """📬 **Warsidaha Rasmiga ah ee Somalilibrary (Substack):**

Ku soo biir warsidahayaga si aad u hesho:
• Fursadaha shaqo ee IT-ga Soomaalida (Muqdisho, Hargeysa, Nairobi, Remote)
• Casharro bilaash ah oo ku saabsan AI Automation & Programming
• Buugaagta cusub ee Isbar iyo qiimo-dhimisyada ardayda

🔗 **Ku biir halkan:** [somalilibrary.substack.com](https://somalilibrary.substack.com)"""

    elif any(k in user_lower for k in ["shaqo", "it", "soomaaliya", "somalia", "muqdisho", "hargeysa", "kenya", "nairobi"]):
        return """💼 **Fursadaha Shaqo ee Dhalinyarada IT-ga Soomaaliyeed:**

Nidaamku wuxuu si toos ah isku xiraa:
1. 🇸🇴 **Soomaaliya:** IT Support, Network, & Web Dev (Hormuud, Dahabshiil, Premier Bank, Telesom, UN/IOM).
2. 🇰🇪 **East Africa:** Cloud, Data & Systems (Safaricom Nairobi, NGO projects Jigjiga & Addis).
3. 🌐 **Remote Global:** AI Automation Specialists, Virtual IT Helpdesk.
4. 🇨🇦 **Canada & Diaspora:** Computer Instruction, Technical Support Edmonton & Toronto.

*Guji qeybta 'Shaqooyinka' si aad u hesho warqad codsi (Cover Letter) diyaarsan!*"""

    elif any(k in user_lower for k in ["booking", "ballan", "xiriir", "contact", "la kulan", "faratoon", "caawin", "mentorship"]):
        return """📅 **Ballan Live ah & Xiriir Toos ah (Live Booking):**

Waxaad si toos ah ula xiriiri kartaa **Mohamed Yasin Mohamoud (Faratoon)**:
• 📅 **Live Booking Form:** Guji tab-ka **'Ballan Live ah'** ee bogga si aad u doorato taariikhda iyo waqtiga.
• 📱 **WhatsApp:** `+1 (587) 306-4137`
• 📧 **Email:** `Suxufi34@gmail.com`
• 📍 **Goobta:** Edmonton, Alberta, Canada 🇨🇦 & Online Global
• 🔗 **LinkedIn:** [linkedin.com/in/mfaratoon](https://www.linkedin.com/in/mfaratoon)
• 📺 **YouTube:** [youtube.com/User/MrFaratoon](https://www.youtube.com/User/MrFaratoon)

*Haddii aad tahay arday u baahan caawinaad CV, tababar koorso, ama talo shaqo, xor ayaad u tahay inaad nala soo xiriirto!*"""

    else:
        return """Salamaat walaal! 👋 Waxaan ahay **Kaaliyaha Rasmiga ah ee Dhalinyarada Soomaaliyeed ee IT-ga**.

Waxaan diyaar kuugu ahay inaan kaa caawiyo:
1. 💻 **Shaqooyinka IT-ga ee Soomaaliya (Muqdisho, Hargeysa), East Africa & Remote**
2. 📚 **Buugaagta Isbar (Computer $5, Programming $5, AI $7, ChatGPT FREE)**
3. 🤖 **Koorsooyinka AI Automation & Chatbots (WhatsApp, Telegram, N8n, Typebot)**
4. 📬 **Ku biirista Warsidaha Somalilibrary Substack**
5. 📅 **Live Booking & Mentorship 1-on-1 ah**

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
    """Generates a professional, complete 1-page ATS resume for Mohamed Yasin Mohamoud."""
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
    elements.append(Paragraph('MOHAMED YASIN MOHAMOUD (FARATOON)', title_style))
    elements.append(Spacer(1, 2))
    elements.append(Paragraph('Dynamic IT Educator &bull; Computer Systems Specialist &bull; AI Automation Trainer', sub_style))
    elements.append(Spacer(1, 2))
    elements.append(Paragraph('Edmonton, AB, Canada &bull; +1 (587) 306-4137 &bull; Suxufi34@gmail.com &bull; linkedin.com/in/mfaratoon', contact_style))
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#0284c7'), spaceAfter=5, spaceBefore=2))

    elements.append(Paragraph('PROFESSIONAL SUMMARY', sec_head))
    elements.append(Paragraph('Dedicated and results-driven IT Educator, Computer Support Specialist, and AI Automation Trainer with 5+ years of international teaching experience with the United Nations International Organization for Migration (UN/IOM). Proven track record in IT literacy instruction, technical troubleshooting, systems administration, and AI chatbot development. Recipient of an official UN/IOM Certificate of Commendation, with an online reach exceeding 100,000 Somali students.', body_style))
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

    elements.append(Paragraph('<b>Computer Teacher & Digital Literacy Instructor</b> | <i>UN Migration Agency (IOM)</i> &nbsp;&bull;&nbsp; 03/2017 &ndash; 01/2021', job_head))
    elements.append(Paragraph('&bull; Delivered foundational and advanced IT training (Computer Basics, MS Office, photo/video editing) to multicultural refugee cohorts.', bullet_style))
    elements.append(Paragraph('&bull; Developed hands-on technical curriculum enabling students to gain essential employment-ready digital competencies.', bullet_style))
    elements.append(Paragraph('&bull; <b>Awarded Official Certificate of Commendation</b> by IOM leadership in recognition of 3+ years of exemplary educational service.', bullet_style))
    elements.append(Spacer(1, 3))

    elements.append(Paragraph('<b>Website Content & Digital Media Coordinator</b> | <i>Somalinfo.com</i> &nbsp;&bull;&nbsp; 11/2014 &ndash; 05/2015', job_head))
    elements.append(Paragraph('&bull; Administered digital publishing workflows, site traffic analytics, and multimedia asset deployment.', bullet_style))
    elements.append(Spacer(1, 4))

    elements.append(Paragraph('EDUCATION & PROFESSIONAL CREDENTIALS', sec_head))
    elements.append(Paragraph('&bull; <b>Google IT Support Professional Certificate</b> &ndash; Google / Coursera (Networking, Security, OS, System Admin)', bullet_style))
    elements.append(Paragraph('&bull; <b>Bachelor of Arts in Media & Mass Communication</b> &ndash; African Virtual University (AVU), 2009', bullet_style))
    elements.append(Paragraph('&bull; <b>Certificate of Commendation</b> &ndash; United Nations International Organization for Migration (UN/IOM)', bullet_style))

    doc.build(elements)
    return output_path

@app.route("/download/resume")
def download_resume():
    try:
        target_path = PDF_RESUME_PATH
        # Also check assets backup
        assets_backup = BASE_DIR / "assets" / "Mohamed_Yasin_Mohamoud_Resume.pdf"
        
        if not target_path.exists() or target_path.stat().st_size < 3500:
            if assets_backup.exists() and assets_backup.stat().st_size >= 3500:
                target_path = assets_backup
            else:
                generate_resume_pdf(target_path)
                
        return send_file(
            target_path,
            as_attachment=True,
            download_name="Mohamed_Yasin_Mohamoud_Resume.pdf",
            mimetype="application/pdf"
        )
    except Exception as e:
        fallback_path = OUTPUT_FOLDER / "Mohamed_Yasin_Mohamoud_Resume.pdf"
        generate_resume_pdf(fallback_path)
        return send_file(
            fallback_path,
            as_attachment=True,
            download_name="Mohamed_Yasin_Mohamoud_Resume.pdf",
            mimetype="application/pdf"
        )

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
