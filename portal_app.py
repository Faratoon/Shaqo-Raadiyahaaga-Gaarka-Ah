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
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
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

def get_curated_somali_it_jobs(term="Dhammaan", location="Muqdisho, Soomaaliya", is_remote=False):
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
# AI Career & Course Chatbot Engine
# -------------------------------------------------------------
def get_career_ai_response(user_message: str) -> str:
    user_lower = user_message.lower().strip()
    client = get_openai_client()

    if client:
        system_instruction = """
Waxaad tahay 'Kaaliyaha AI ee Shaqo Baahiye' (Dhammaan Fursadaha Shaqo & Akadeemiyada Casriga ah).

MUHIIMADDA KOOWAAD: Shaqo Baahiye KUMA KOOBNA IT-GA KALIYA!
Wuxuu u heellan yahay DHAMMAAN NOOCYADA SHAQOOYINKA ee Soomaaliya, Bariga Afrika (Kenya, Itoobiya), Shaqooyinka Guriga (Remote), iyo Dibadda:
1. Maamulka, Maaliyadda & Xisaabaadka (Finance, HR, Accounting, Banking, Management).
2. Caafimaadka, Nafaqada & NGO-yada (Public Health, Nutrition, Humanitarian Aid, Community Development).
3. Suuqgeynta, Iibka & Customer Service (Sales, Marketing, Call Center, Telesales).
4. Waxbarashada & Tababarka (Teaching, Education, Schools, Training).
5. Gaadiidka, Logistics & Procurement (Supply Chain, Warehouse, Fleet).
6. Farsamada & IT-ga (Computer Support, Software, Web Dev, Networking, AI Automation).
7. Shaqooyinka Guriga (Remote Jobs).

HADDII QOFKU SHAQO RAADSANAYO AMA GARAN WAAYO:
U soo bandhig doorashooyin cadcad ama qaab Quiz fudud ah (Xirfaddiisa, Magaalada uu joogo, iyo Khibraddiisa) si loogu helo fursadda ku habboon!

Aasaasaha: Mohamed Yasin (Dynamic Career Educator, AI Automation Trainer).

Waxaad haysataa aqoon buuxda oo ku saabsan:
1. BUUGAAGTA CASRIGA AH EE ISBAR (Qore/Editor: Yahye Cabdirahmaan & Mohamed Yasin):
   - ISBAR COMPUTER: 89 pages, $5. (Computer Basics, Software/Hardware, Windows 11, Mac OS, MS Office, Photoshop, OBS Studio).
   - ISBAR PROGRAMMING: 177 pages, $5. (Basics of Programming, Web Dev Basics, Programming Languages, Database, Code Editor & IDE).
   - ISBAR AI (Artificial Intelligence) BASIC: 189 pages, $7. (Taariikhda AI, AI & Waxbarashada, AI & Shaqooyinka, AI & Graphic Design, AI & Ganacsiga).
   - ISBAR ChatGPT - Prompts Basic: 87 pages, FREE ($0!). (Waa maxay ChatGPT?, Sida loola xiriiro si hufan, Shaqooyinka, Waxbarashada, Ganacsiga).

2. HELITAANKA BUUGAAGTA & BADBAADINTA CREDITS-KA:
   - Haddii qofku buug weydiiyo, rabo in buug loo diro, ama hadalka baddiyo (si credit-ku uusan u khasaarin):
     Toos ugu dir warsidaha Dhegeyso Buug: https://dhegeysobuug.substack.com/
     Qof kasta oo ku biira (subscribe gareeya) wuxuu helayaa 2 buug oo bilaash ah (free) oo si automatic ah ugu soo dhacaya inbox-kiisa (email-kiisa)!

3. SIDEE LOO SAMEEYAY / OPEN SOURCE REPO:
   - Haddii qofku weydiiyo 'sida loo sameeyay', 'repo', ama 'koodhka':
     U sheeg in mashruucu yahay 100% Free / Open Source GitHub-ka (https://github.com/Faratoon/Shaqo-Raadiyahaaga-Gaarka-Ah).
     Qofkii raba inuu barto sida nidaamkan oo kale loogu shubo loona dhiso iyadoo AI la isticmaalayo wuxuu dooran karaa 'Ballan Qabso' (Live 1-on-1 Mentorship oo toos ah oo uu la yeelanayo Mohamed Yasin).

4. KOORSOOYINKA AUTOMATION-KA:
   - Paid: AI ChatGPT – Data Writing ($24 / Ardayda: $10, 4-5 days).
   - Free: AI Video Editing, WhatsApp Business Bot, Telegram Business Bot, Messenger & IG Bots, Web Design with AI Tools (Free for students).

5. LIVE BOOKING & MENTORSHIP:
   - Ardaydu waxay toos u qabsan karaan ballan 1-on-1 ah iyagoo adeegsanaya qeybta 'Ballan Live ah' ama WhatsApp: +1 (587) 306-4137.

6. XOGTA XIRIIRKA:
   - YouTube: https://www.youtube.com/@Mfaratoon
   - Substack: https://dhegeysobuug.substack.com/ & https://somalilibrary.substack.com

U jawaab si kooban, xushmad leh, oo qoraal kaliya ah.
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
    if any(k in user_lower for k in ["buug", "book", "isbar", "qiimaha", "pages", "bogag", "soo dir", "dhegeyso"]):
        return """📚 **Buugaagta Casriga ah ee 'Isbar' (Macallin La'aan):**

1. 💻 **ISBAR COMPUTER** ($5 Kaliya | 89 Pages) • Qore: Yahye Cabdirahmaan • Editor: Mohamed Yasin
2. 👨‍💻 **ISBAR PROGRAMMING** ($5 Kaliya | 177 Pages) • Qore: Yahye Abdirahmaan • Editor: Mohamed Yasin
3. 🧠 **ISBAR AI BASIC** ($7 Kaliya | 189 Pages) • Qore: Yahye Abdirahmaan / Mohamed Yasin
4. 🤖 **ISBAR ChatGPT Prompts** (🎁 FREE / 100% Bilaash! | 87 Pages) • Qore: Mohamed Yasin • Editor: Yahye Abdirahman

📬 **Sidee ku helaysaa Buugaagta?**
Qof kasta oo ku biira (subscribe gareeya) warsidaha **Dhegeyso Buug** wuxuu helayaa **2 Buug oo Bilaash ah (Free)** oo si toos ah (automatic ah) ugu soo dhacaya inbox-kaaga (email-kaaga)!
👉 **Is-diiwaangeli halkan si aad 2-da buug u hesho:** [dhegeysobuug.substack.com](https://dhegeysobuug.substack.com/)"""

    elif any(k in user_lower for k in ["sida loo", "sidee loo", "sameeyaa", "repo", "source code", "shubo", "deploy", "dhis", "github"]):
        return """⭐ **Madashan waa 100% Open Source (Bilaash):**

Repository-ga rasmiga ah ee mashruucan waa bilaash qof kasta ayaana ka faa'iideysan kara:
🔗 **GitHub:** [github.com/Faratoon/Shaqo-Raadiyahaaga-Gaarka-Ah](https://github.com/Faratoon/Shaqo-Raadiyahaaga-Gaarka-Ah)

🚀 **Ma rabtaa inaad barato sida nidaamkan oo kale loogu shubo loona dhiso iyadoo AI la adeegsanayo?**
Qofkii raba inuu barto sida loo dhiso loona shubo (deploy) codsiyada casriga ah ee AI-ga:
• Waxaad dooran kartaa **'Ballan Qabso'** (Live 1-on-1 Mentorship oo toos ah oo aad la yeelanayso **Mohamed Yasin**).
• 📅 Qabso Ballan Live ah bogga ama toos WhatsApp: `+1 (587) 306-4137`."""

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
        return """📬 **Warsidayaasha Rasmiga ah:**

1. 📚 **Dhegeyso Buug Substack (Hel 2 Buug oo Bilaash ah):**
   Qof kasta oo subscribe gareeya wuxuu helayaa 2 buug oo bilaash ah oo si automatic ah inbox-kiisa ugu soo dhacaya:
   🔗 [dhegeysobuug.substack.com](https://dhegeysobuug.substack.com/)

2. 📰 **Somalilibrary Substack (Fursadaha Shaqada & AI-ga):**
   🔗 [somalilibrary.substack.com](https://somalilibrary.substack.com/)"""

    elif any(k in user_lower for k in ["quiz", "quize", "xirfad", "ii raadi", "dooro"]):
        return """🎯 **Quiz: Ii Raadi Shaqada Ku Habboon (Career Matching Quiz) 🧭**

Si aan kuugu helo shaqada kugu habboon, fadlan ka dooro 3-dan su'aalood:

1. 💼 **Qeybta aad rabto:**
   • 📊 Maamul & Xisaabaad
   • 📞 Customer Care & Iib
   • 🏥 Caafimaad & NGO
   • 📚 Waxbarasho & Macallin
   • 💻 IT & Farsamo
   • 📦 Logistics & Gaadiid

2. 📍 **Goobta aad joogto:**
   • 🇸🇴 Muqdisho | 🇸🇴 Hargeysa & Puntland
   • 🇰🇪 Nairobi | 🌐 Remote (Guriga)

3. 🎓 **Khibraddaada:**
   • 🌱 Ku cusub (Entry/Graduate) | 💼 1-3 Sano | 🏆 3+ Sano

*Ii soo qor tusaale: "Maamul, Muqdisho, Ku cusub", waxaana si toos ah kuugu soo saari doonaa shaqooyinka bannaan!* 🚀"""

    elif any(k in user_lower for k in ["shaqo", "jobs", "soomaaliya", "somalia", "muqdisho", "hargeysa", "kenya", "nairobi"]):
        return """💼 **Fursadaha Shaqo ee Dhammaan Qeybaha (All Careers in Somalia & East Africa):**

Shaqo Baahiye wuxuu kuu raadinayaa dhammaan noocyada shaqooyinka:
1. 📊 **Maamulka & Xisaabaadka:** Finance Officer, HR Assistant, Accountant (Dahabshiil, Salaam Somali Bank).
2. 📞 **Customer Care & Iibka:** Call Center & EVC Plus Support (Hormuud Telecom, Telesom).
3. 🏥 **Caafimaadka & NGO-yada:** Health Field Officer, Project Assistant (Save the Children, SRCS, UN).
4. 📚 **Waxbarashada:** Macallimiinta Dugsiyada & Jaamacadaha (English, Math, Science).
5. 💻 **IT-ga & Farsamada:** IT Support, Web Developer, AI Automation, Junior Cloud Engineer.
6. 🌐 **Shaqooyinka Guriga (Remote):** Customer Support, Digital Marketing, Data Entry.

🎯 **Ma hubtid shaqada kugu habboon?** Qor `quiz` si aad uga jawaabto 3 su'aalood oo kooban oo shaqo kugu habboon lagugu helo!"""

    elif any(k in user_lower for k in ["booking", "ballan", "xiriir", "contact", "la kulan", "caawin", "mentorship"]):
        return """📅 **Ballan Live ah & Xiriir Toos ah (Live Booking):**

Waxaad si toos ah ula xiriiri kartaa **Mohamed Yasin**:
• 📅 **Live Booking Form:** Guji tab-ka **'Ballan Live ah'** ee bogga si aad u doorato taariikhda iyo waqtiga.
• 📱 **WhatsApp:** `+1 (587) 306-4137`
• 📧 **Email:** `Suxufi34@gmail.com`
• 📍 **Goobta:** Edmonton, Alberta, Canada 🇨🇦 & Online Global
• 🔗 **LinkedIn:** [linkedin.com/in/mfaratoon](https://www.linkedin.com/in/mfaratoon)
• 📺 **YouTube:** [youtube.com/@Mfaratoon](https://www.youtube.com/@Mfaratoon)

*Haddii aad tahay arday u baahan caawinaad CV, tababar koorso, ama talo shaqo, xor ayaad u tahay inaad nala soo xiriirto!*"""

    else:
        return """Salamaat walaal! 👋 Waxaan ahay **Kaaliyaha AI ee Shaqo Baahiye**.

Waxaan diyaar kuugu ahay inaan kaa caawiyo:
1. 💼 **Dhammaan Fursadaha Shaqo (Maamul, Caafimaad, Iib, NGO, IT & Remote)**
2. 🎯 **Quiz: Ii Raadi Shaqadayda (Hagaha shaqo-helidda oo kooban)**
3. 📚 **Buugaagta Isbar** (Subscribe dheh [dhegeysobuug.substack.com](https://dhegeysobuug.substack.com/) waxaad helaysaa 2 buug oo bilaash ah oo si automatic ah inbox-kaaga ugu soo dhacaya!)
4. 🤖 **Koorsooyinka AI Automation & Chatbots (WhatsApp, Telegram, N8n, Typebot)**
5. ⭐ **Open Source Repo** (100% Free & Open Source)
6. 📅 **Live Booking & Mentorship 1-on-1 ah la yeelo Mohamed Yasin**

*Ii soo qor su'aashaada gaarka ah ama qor 'quiz' si aad shaqo u raadsato!* 🚀"""

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
