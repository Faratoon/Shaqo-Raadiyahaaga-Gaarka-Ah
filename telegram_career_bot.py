import os
import sys
import time
import json
import urllib.parse
from pathlib import Path
import requests

# Ensure imports work from current project root
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

try:
    from portal_app import get_career_ai_response, get_curated_somali_it_jobs, is_spam_or_invalid
except ImportError:
    # Standalone fallbacks if needed
    def get_career_ai_response(msg):
        return "Salamaat! Waxaan ahay Kaaliyaha Somali Books & Shaqo Raadiyaha Dhalinyarada Soomaaliyeed ee IT-ga. Waxaan kaa caawin karaa buugaagta Isbar, shaqooyinka, iyo koorsooyinka."
    def get_curated_somali_it_jobs():
        return []
    def is_spam_or_invalid(msg):
        return False, ""

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or "6265456404:AAFjTFnJzBRb1xDvCNoT-EBLbmFl1JGw8yU"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
WEB_APP_URL = "https://auto-jobs-applier-aih-awk-live.vercel.app"

def configure_bot_menu_button():
    """Sets the Telegram Chat Menu Button to open the Mini App natively."""
    url = f"{API_URL}/setChatMenuButton"
    payload = {
        "menu_button": {
            "type": "web_app",
            "text": "📱 Mini App",
            "web_app": {"url": WEB_APP_URL}
        }
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        data = res.json()
        print(f"[*] Telegram Chat Menu Button set to Mini App: {data.get('ok')}")
    except Exception as e:
        print(f"[!] Error setting chat menu button: {e}")

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    url = f"{API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        res = requests.post(url, json=payload, timeout=15)
        data = res.json()
        if not data.get("ok") and parse_mode:
            # Fallback to plain text if HTML parsing failed
            payload.pop("parse_mode", None)
            res = requests.post(url, json=payload, timeout=15)
            return res.json()
        return data
    except Exception as e:
        print(f"[!] Error sending message to {chat_id}: {e}")
        return None

def answer_callback_query(callback_query_id, text=None):
    url = f"{API_URL}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

def get_main_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🚀 Fur Mini App (Shaqooyinka & Buugaagta)", "web_app": {"url": WEB_APP_URL}}
            ],
            [
                {"text": "💼 Shaqooyinka IT-ga Soomaalida", "callback_data": "menu_jobs"},
                {"text": "📚 Buugaagta Isbar ($5 - $7)", "callback_data": "menu_books"}
            ],
            [
                {"text": "🎓 Koorsooyinka Bilaashka ah", "callback_data": "menu_courses"},
                {"text": "📅 Qabso Ballan Live ah (1-on-1)", "callback_data": "menu_booking"}
            ],
            [
                {"text": "📄 Talooyinka CV ATS ah & STAR", "callback_data": "menu_cv"},
                {"text": "📬 Warsidaha Substack", "url": "https://somalilibrary.substack.com"}
            ]
        ]
    }

def handle_start(chat_id, first_name):
    welcome_text = f"""<b>Salamaat {first_name}! 👋</b>

Ku soo dhowow <b>Somali Books & Shaqo Raadiyaha Dhalinyarada Soomaaliyeed (@Somalibooksbot)</b>! 🦅

Waxaad hadda toos Telegram-ka dhexdiisa uga furi kartaa <b>Telegram Mini App-ka Casriga ah</b> adigoo gujinaya badhanka hoose ama midka Menu-ga!

<b>Adeegyada aad ka helayso Bot-kan:</b>
• 📱 <b>Telegram Mini App:</b> Bogga oo dhan oo toos Telegram ugu furmaya.
• 💼 <b>Shaqooyinka IT-ga:</b> Soomaaliya (Muqdisho, Hargeysa), Bariga Afrika, Remote, iyo Kanada.
• 📚 <b>Buugaagta Casriga ah ee Isbar:</b> Computer ($5), Programming ($5), AI ($7), iyo ChatGPT (Bilaash!).
• 🎓 <b>Koorsooyinka Bilaashka ah:</b> AI Video Editing, WhatsApp/Telegram Bots, Web Design.
• 📅 <b>Ballan Live ah:</b> 1-on-1 Mentorship la yeelashada <b>Mohamed Faratoon</b>.
• 🤖 <b>AI Career Advisor:</b> Ii soo qor su'aal kasta oo ku saabsan CV-gaaga ama teknoolajiyadda!

<i>Guji badhanka hoose si aad u furto Mini App-ka ama u dhex gasho adeegyada:</i>"""
    send_message(chat_id, welcome_text, get_main_keyboard())

def handle_jobs(chat_id):
    jobs = get_curated_somali_it_jobs()
    text = "<b>💼 Fursadaha Shaqo ee IT-ga ee Diyaarka ah:</b>\n\n"
    
    for idx, j in enumerate(jobs[:5], 1):
        text += f"<b>{idx}. {j['title']}</b>\n"
        text += f"🏢 Shirkadda: <i>{j['company']}</i>\n"
        text += f"📍 Goobta: <i>{j['location']}</i>\n"
        text += f"🔗 <a href='{j['job_url']}'>Guji halkan si aad u codsato</a>\n\n"

    text += "💡 <i>Talo: Mini App-ka dhexdiisa waxaad ka helaysaa Canadian & International Cover Letter diyaarsan oo hal guji lagu koobiyeeyo!</i>"
    
    markup = {
        "inline_keyboard": [
            [{"text": "📱 Ka Fur Mini App-ka Shaqooyinka", "web_app": {"url": f"{WEB_APP_URL}#jobsSection"}}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_books(chat_id):
    text = """<b>📚 Buugaagta Casriga ah ee 'Isbar' (Macallin La'aan):</b>

1. 💻 <b>ISBAR COMPUTER</b> (89 Pages | $5 Kaliya)
   • Qore: Yahye Cabdirahmaan • Editor: Mohamed Faratoon
   • Baro: Basics, Windows 11, Mac OS, Office, Photoshop, OBS.

2. 👨‍💻 <b>ISBAR PROGRAMMING</b> (177 Pages | $5 Kaliya)
   • Qore: Yahye Abdirahmaan • Editor: Mohamed Faratoon
   • Baro: Coding Basics, Web Development, Databases, IDEs.

3. 🧠 <b>ISBAR AI (Artificial Intelligence) BASIC</b> (189 Pages | $7 Kaliya)
   • Qore: Yahye Abdirahmaan / Mohamed Faratoon
   • Baro: Mustaqbalka AI, Waxbarashada, Graphic Design, Ganacsiga.

4. 🤖 <b>ISBAR ChatGPT Prompts</b> (87 Pages | <b>🎁 100% BILAASH!</b>)
   • Qore: Mohamed Faratoon • Editor: Yahya Abdirahman
   • Baro: Prompts, shaqooyinka, qorista ganacsiga.

🎉 <b>Dalab Gaar ah:</b> Qof kasta oo buug iibsada waxaa loogu darayaa Koorso Automation ah oo <b>BILAASH ah!</b>"""

    markup = {
        "inline_keyboard": [
            [{"text": "📱 Ka Fur Mini App-ka Buugaagta", "web_app": {"url": f"{WEB_APP_URL}#coursesHubSection"}}],
            [{"text": "📱 Ku Dalbo WhatsApp (+1 587-306-4137)", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20rabaa%20in%20aan%20iibsado%20buug%20Isbar"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_courses(chat_id):
    text = """<b>🎓 Koorsooyinka AI Automation & Dhisidda Chatbots-ka:</b>

🔹 <b>Paid Course (Qiimo-dhimista Ardayda):</b>
• <b>AI ChatGPT – Data Writing 📝:</b> Qorista ganacsiga, content creation, iyo CV/proposals.
  - Waqtiga: 4–5 Maalmood
  - Qiimaha: $24 (<b>Ardayda: $10 Kaliya!</b>)

🎓 <b>Free Courses (100% Bilaash Ardayda Sanadkan):</b>
• 🎥 <b>AI Video Editing:</b> Habaynta muuqaallada casriga ah adoo adeegsanaya AI tools.
• 📱 <b>WhatsApp Automation Business Bot:</b> Dhis bot ganacsi oo 24/7 shaqeeya.
• 📞 <b>Telegram Automation Business Bot:</b> Bot wata flowchart iyo database.
• 💬 <b>Messenger & Instagram Bots:</b> DM automation & iibka tooska ah.
• 🌐 <b>Web Design with AI Tools:</b> Dhis website casri ah adoo adeegsanaya HTML/CSS & AI.

🛠️ <b>Madallada aan wax ku barno:</b> Chatbase, Botfather, Chatfuel, Manychat, N8n, Botsail, Jotform, Botpress, Paal AI, Vibe Coding, Typebot."""

    markup = {
        "inline_keyboard": [
            [{"text": "📱 Ka Fur Mini App-ka Koorsooyinka", "web_app": {"url": f"{WEB_APP_URL}#coursesHubSection"}}],
            [{"text": "📅 Is-Diiwaangeli Hadda", "url": f"{WEB_APP_URL}#bookingSection"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_booking(chat_id):
    text = """<b>📅 Ballan Live ah & Mentorship 1-on-1 ah:</b>

Waxaad toos ballan la-talin ah ula yeelan kartaa <b>Mohamed Yasin Mohamoud (Faratoon)</b>:
• ✅ Dib-u-eegista & dhisidda CV ATS ah
• ✅ Tababarka wareysiyada IT-ga (STAR Method)
• ✅ Hagidda koorsooyinka AI Automation & Tech
• ✅ Helitaanka buugaagta Isbar

📍 <b>Xiriirka Tooska ah:</b>
• 📱 <b>WhatsApp:</b> <code>+1 (587) 306-4137</code>
• 📧 <b>Email:</b> <code>Suxufi34@gmail.com</code>
• 📍 <b>Goobta:</b> Edmonton, AB, Canada 🇨🇦 & Online Global (Google Meet / Zoom)"""

    markup = {
        "inline_keyboard": [
            [{"text": "📱 Ka Qabso Ballan Mini App-ka", "web_app": {"url": f"{WEB_APP_URL}#bookingSection"}}],
            [{"text": "💬 WhatsApp Toos ah Mohamed Faratoon", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20rabaa%20in%20aan%20ballan%20live%20ah%20qabsado"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_cv(chat_id):
    text = """<b>📄 Talooyinka Dahabiga ah ee Diyaarinta CV ATS ah & Wareysiga:</b>

1. <b>CV ATS-Friendly ah:</b>
   • Ka fogow sawirrada, jaantusyada adag iyo naqshadaha xad-dhaafka ah.
   • Xoogga saar: Summary cad (3 sadar), Core Technical Skills (Networking, Systems, AI), Mashaariicdii jaamacadda, iyo shahaadooyinka (Google IT Support, Coursera).

2. <b>Wareysiga Shaqada (STAR Method):</b>
   • <b>S (Situation):</b> Sharax xaaladdii jirtay.
   • <b>T (Task):</b> Maxaa lagaa rabay?
   • <b>A (Action):</b> Tallaabooyinkee ayaad qaadday?
   • <b>R (Result):</b> Maxaa ka dhashay (Natiijo dhab ah oo tiro wadata)?

<i>Guji link-ga hoose si aad Mini App-ka dhexdiisa ugu falanqeyso CV-gaaga!</i>"""

    markup = {
        "inline_keyboard": [
            [{"text": "📱 Ka Falanqee CV-gaaga Mini App-ka", "web_app": {"url": f"{WEB_APP_URL}#assessSection"}}],
            [{"text": "📄 Soo Degso Resume Template (PDF)", "url": f"{WEB_APP_URL}/download/resume"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def process_callback_query(callback_query):
    cq_id = callback_query.get("id")
    data = callback_query.get("data")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")

    answer_callback_query(cq_id)

    if data == "menu_main":
        send_message(chat_id, "<b>Dooro adeegga aad doonayso:</b>", get_main_keyboard())
    elif data == "menu_jobs":
        handle_jobs(chat_id)
    elif data == "menu_books":
        handle_books(chat_id)
    elif data == "menu_courses":
        handle_courses(chat_id)
    elif data == "menu_booking":
        handle_booking(chat_id)
    elif data == "menu_cv":
        handle_cv(chat_id)

def process_message(message):
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "").strip()
    first_name = chat.get("first_name", "Walaal")

    if not text:
        return

    text_lower = text.lower()

    if text_lower in ["/start", "start", "bilaaw", "menu", "hi", "halo"]:
        handle_start(chat_id, first_name)
    elif text_lower in ["/jobs", "shaqo", "shaqooyin"]:
        handle_jobs(chat_id)
    elif text_lower in ["/books", "buug", "buugaag", "isbar"]:
        handle_books(chat_id)
    elif text_lower in ["/courses", "koorso", "koorsooyin"]:
        handle_courses(chat_id)
    elif text_lower in ["/booking", "ballan"]:
        handle_booking(chat_id)
    elif text_lower in ["/cv", "resume", "wareysi"]:
        handle_cv(chat_id)
    elif text_lower in ["/app", "miniapp", "app"]:
        send_message(chat_id, "🚀 <b>Guji badhanka hoose si aad u furto Mini App-ka:</b>", {
            "inline_keyboard": [[{"text": "📱 Fur Mini App-ka", "web_app": {"url": WEB_APP_URL}}]]
        })
    else:
        # Check spam
        is_spam, reason = is_spam_or_invalid(text)
        if is_spam:
            send_message(chat_id, reason)
            return

        # AI Career response
        ai_reply = get_career_ai_response(text)
        # Convert markdown bold to HTML
        html_reply = ai_reply.replace("**", "<b>", 1)
        while "**" in html_reply:
            html_reply = html_reply.replace("**", "</b>", 1)
            html_reply = html_reply.replace("**", "<b>", 1)

        markup = {
            "inline_keyboard": [
                [{"text": "📱 Fur Mini App", "web_app": {"url": WEB_APP_URL}}],
                [{"text": "💼 Shaqooyinka IT-ga", "callback_data": "menu_jobs"}, {"text": "📚 Buugaagta Isbar", "callback_data": "menu_books"}],
                [{"text": "📅 Qabso Ballan Live ah", "callback_data": "menu_booking"}]
            ]
        }
        send_message(chat_id, html_reply, markup, parse_mode="HTML")

def run_bot_polling():
    print(f"\n=======================================================")
    print(f"   Somali Books & Jobs Telegram Mini App Bot")
    print(f"   Bot: @Somalibooksbot")
    print(f"   Configuring Menu Button & Connecting...")
    print(f"=======================================================\n")

    configure_bot_menu_button()

    offset = None
    while True:
        try:
            url = f"{API_URL}/getUpdates"
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset

            res = requests.get(url, params=params, timeout=40)
            if res.status_code == 200:
                data = res.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update.get("update_id") + 1
                        if "message" in update:
                            process_message(update["message"])
                        elif "callback_query" in update:
                            process_callback_query(update["callback_query"])
            else:
                print(f"[!] getUpdates response code {res.status_code}: {res.text}")
                time.sleep(5)
        except requests.exceptions.RequestException:
            # Network hiccup or telegram timeout
            time.sleep(4)
        except Exception as e:
            print(f"[!] Unexpected error in bot loop: {e}")
            time.sleep(4)

if __name__ == "__main__":
    run_bot_polling()
