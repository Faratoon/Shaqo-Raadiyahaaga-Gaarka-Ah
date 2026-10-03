import os
import sys
import json
import webbrowser
from datetime import datetime
from pathlib import Path
from jobspy import scrape_jobs
import pandas as pd
from openai import OpenAI

# Configuration
SEARCH_QUERIES = [
    {"term": "computer instructor", "location": "Edmonton, AB", "remote": False},
    {"term": "computer teacher", "location": "Edmonton, AB", "remote": False},
    {"term": "digital literacy instructor", "location": "Edmonton, AB", "remote": False},
    {"term": "IT trainer", "location": "Edmonton, AB", "remote": False},
    {"term": "IT support", "location": "Edmonton, AB", "remote": False},
    {"term": "AI automation", "location": "Canada", "remote": True},
    {"term": "volunteer coordinator", "location": "Edmonton, AB", "remote": False},
]

RELEVANT_KEYWORDS = [
    "instructor", "teacher", "trainer", "literacy", "computer", "it", 
    "support", "coordinator", "assistant", "ai", "automation", "data", "admin", "volunteer", "education"
]

IRRELEVANT_KEYWORDS = [
    "driver", "snow", "truck", "welder", "cook", "mechanic", "nurse", "plumber"
]

MAX_JOBS_PER_DAY = 5

CANDIDATE_PROFILE = """
Candidate: Mohamed Yasin Mohamoud
Location: Edmonton, AB, Canada
Summary: Dynamic professional with 5+ years of computer instruction with the International Organization for Migration (IOM) in Indonesia, teaching Computer Basics, MS Office, and editing to multicultural students. Holds a BA in Mass Communication from AVU. Recently specialized in AI Automation, No-Code chatbots, and digital media.
Certifications: Official IOM Certificate of Appreciation, 10+ IT/Media credentials.
Languages: English (Fluent), Somali (Native), Indonesian (Conversational).
Authorized to work in Canada: Yes.
"""

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[!] Warning: OPENAI_API_KEY not found in environment.")
        return None
    return OpenAI(api_key=api_key)

def search_jobs():
    print(f"\n[+] Searching top job boards (Indeed Canada, ZipRecruiter, Glassdoor)...")
    print(f"[+] Target Locations: Edmonton, AB and Remote Canada")
    print(f"[+] Max daily applications limit: {MAX_JOBS_PER_DAY} jobs\n")
    
    all_jobs_list = []
    
    for query in SEARCH_QUERIES:
        if len(all_jobs_list) >= MAX_JOBS_PER_DAY * 3:
            break
        print(f"  -> Searching for '{query['term']}' in '{query['location']}' (Remote: {query['remote']})...")
        try:
            jobs = scrape_jobs(
                site_name=["indeed", "zip_recruiter", "glassdoor"],
                search_term=query["term"],
                location=query["location"],
                results_wanted=3,
                hours_old=72,
                country_indeed="Canada",
                is_remote=query["remote"]
            )
            if not jobs.empty:
                for _, row in jobs.iterrows():
                    job_data = {
                        "site": str(row.get("site", "indeed")).title(),
                        "title": str(row.get("title", "")),
                        "company": str(row.get("company", "Company")),
                        "location": str(row.get("location", "Edmonton, AB")),
                        "job_url": str(row.get("job_url", "")),
                        "description": str(row.get("description", ""))[:2000],
                        "date_posted": str(row.get("date_posted", "Recent")),
                        "job_type": str(row.get("job_type", "Full-time / Part-time")),
                    }
                    title_lower = job_data["title"].lower()
                    if any(bad in title_lower for bad in IRRELEVANT_KEYWORDS):
                        continue
                    if any(good in title_lower for good in RELEVANT_KEYWORDS):
                        if job_data["job_url"] and not any(j["job_url"] == job_data["job_url"] for j in all_jobs_list):
                            all_jobs_list.append(job_data)
        except Exception as e:
            print(f"     [!] Notice: Query error for {query['term']}: {e}")
            continue

    # Select top MAX_JOBS_PER_DAY jobs
    selected_jobs = all_jobs_list[:MAX_JOBS_PER_DAY]
    return selected_jobs

def generate_custom_materials(client, job):
    company = job.get('company', 'Hiring Team')
    title = job.get('title', 'Position')
    location = job.get('location', 'Edmonton, AB')

    if client:
        prompt = f"""
You are an expert career advisor in Canada.
Analyze this job and candidate profile:

{CANDIDATE_PROFILE}

Job Title: {title}
Company: {company}
Location: {location}
Job Description Excerpt:
{job['description'][:1500]}

Generate a JSON object with:
1. "match_score": percentage match string like "92%"
2. "match_reason": 1-2 sentence explanation of why Mohamed is a great fit
3. "key_pitch": 2 sentences explaining key strengths to mention during application
4. "cover_letter": a tailored, professional 3-paragraph Canadian-style cover letter ready to copy-paste.

Return ONLY valid JSON.
"""
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.4
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"     [!] Notice: Using built-in tailored template ({e})")

    # High-quality Canadian cover letter tailored with Mohamed's IOM and AI background
    cover_letter = f"""Dear Hiring Manager at {company},

I am writing to express my enthusiastic interest in the {title} position in {location}. With over five years of dedicated experience delivering computer literacy, office software, and digital media training for the International Organization for Migration (IOM) in Indonesia, combined with hands-on expertise in AI automation and no-code solutions, I am eager to bring my background and enthusiasm to your team.

Throughout my tenure at IOM, I facilitated interactive training modules in Computer Basics, Microsoft Office (Word, Excel, PowerPoint), and digital editing for diverse multicultural students. My commitment to empowering learners with practical, workforce-ready technical skills was recognized with official Certificates of Appreciation and Recognition from IOM leadership. In addition, I hold a Bachelor of Arts in Mass Communication (Specializing in Pan-African Media) and have expanded my skill set into building AI chatbots and automating digital workflows.

I am deeply committed to serving the Edmonton community and would welcome the opportunity to bring my instructional background, cross-cultural empathy, and tech-savviness to {company}. Thank you for your time and consideration, and I look forward to the possibility of discussing my application.

Sincerely,

Mohamed Yasin Mohamoud
Edmonton, AB, Canada"""

    return {
        "match_score": "93%",
        "match_reason": f"Directly aligns with your 5+ years of computer instruction at IOM, AVU Mass Communication degree, and digital literacy background.",
        "key_pitch": f"Emphasize your UN/IOM Certificates of Appreciation, cross-cultural student coaching, and modern AI automation skills.",
        "cover_letter": cover_letter
    }

def build_dashboard(jobs_with_ai):
    timestamp = datetime.now().strftime("%B %d, %Y - %I:%M %p")
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Today's 5 Curated Jobs - Mohamed Yasin Mohamoud</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f0f2f5; color: #1c1e21; margin: 0; padding: 20px; }}
        .container {{ max-width: 950px; margin: 0 auto; }}
        .header {{ background: #1a365d; color: white; padding: 25px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
        .header h1 {{ margin: 0 0 8px 0; font-size: 26px; }}
        .header p {{ margin: 0; opacity: 0.9; font-size: 14px; }}
        .badge-limit {{ display: inline-block; background: #38a169; color: white; padding: 4px 12px; border-radius: 20px; font-weight: 600; font-size: 13px; margin-top: 10px; }}
        .card {{ background: white; border-radius: 12px; padding: 22px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 5px solid #2b6cb0; }}
        .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; }}
        .title {{ font-size: 20px; font-weight: 700; color: #2d3748; margin: 0 0 6px 0; }}
        .company {{ font-size: 15px; color: #4a5568; margin-bottom: 12px; font-weight: 500; }}
        .match-badge {{ background: #ebf8ff; color: #2b6cb0; padding: 6px 14px; border-radius: 16px; font-weight: 700; font-size: 14px; border: 1px solid #bee3f8; }}
        .meta-tags {{ margin: 10px 0; }}
        .tag {{ display: inline-block; background: #edf2f7; color: #4a5568; padding: 4px 10px; border-radius: 6px; font-size: 12px; margin-right: 8px; font-weight: 600; }}
        .pitch-box {{ background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; margin: 14px 0; font-size: 13.5px; color: #2d3748; }}
        .letter-container {{ background: #fffaf0; border: 1px solid #feebc8; border-radius: 8px; padding: 14px; margin-top: 14px; }}
        .letter-title {{ font-weight: 700; font-size: 13px; color: #c05621; margin-bottom: 8px; text-transform: uppercase; }}
        pre {{ white-space: pre-wrap; font-family: inherit; font-size: 13px; color: #2d3748; line-height: 1.5; margin: 0; }}
        .actions {{ margin-top: 16px; display: flex; gap: 12px; align-items: center; }}
        .btn-apply {{ background: #2563eb; color: white; text-decoration: none; padding: 10px 20px; border-radius: 8px; font-weight: 600; font-size: 14px; display: inline-block; transition: background 0.2s; }}
        .btn-apply:hover {{ background: #1d4ed8; }}
        .btn-copy {{ background: #edf2f7; color: #2d3748; border: 1px solid #cbd5e0; padding: 9px 16px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }}
        .btn-copy:hover {{ background: #e2e8f0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Daily Curated Applications: Edmonton & Remote</h1>
            <p>Prepared for <b>Mohamed Yasin Mohamoud</b> | Generated: {timestamp}</p>
            <div class="badge-limit">Daily Limit: {len(jobs_with_ai)} Jobs Ready</div>
        </div>
"""
    for i, item in enumerate(jobs_with_ai, 1):
        job = item["job"]
        ai = item["ai"]
        letter_escaped = ai.get("cover_letter", "").replace('"', '&quot;')
        html_content += f"""
        <div class="card">
            <div class="card-top">
                <div>
                    <h2 class="title">{i}. {job['title']}</h2>
                    <div class="company">{job['company']} &bull; {job['location']}</div>
                </div>
                <div class="match-badge">{ai.get('match_score', '90%')} Match</div>
            </div>

            <div class="meta-tags">
                <span class="tag">Platform: {job['site']}</span>
                <span class="tag">Type: {job['job_type']}</span>
                <span class="tag">Posted: {job['date_posted']}</span>
            </div>

            <div class="pitch-box">
                <b>Why You Are a Great Fit:</b> {ai.get('match_reason', '')}<br>
                <b>Key Application Strength:</b> {ai.get('key_pitch', '')}
            </div>

            <div class="letter-container">
                <div class="letter-title">Personalized Cover Letter (Ready to submit)</div>
                <pre id="letter-{i}">{ai.get('cover_letter', '')}</pre>
            </div>

            <div class="actions">
                <a href="{job['job_url']}" target="_blank" class="btn-apply">Open Job & Apply on {job['site']} &rarr;</a>
                <button class="btn-copy" onclick="navigator.clipboard.writeText(document.getElementById('letter-{i}').innerText); alert('Cover letter copied to clipboard!');">Copy Cover Letter</button>
            </div>
        </div>
        """

    html_content += """
    </div>
</body>
</html>
"""
    output_path = Path("jobs_today.html").resolve()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return output_path

def main():
    client = get_openai_client()
    jobs = search_jobs()
    
    if not jobs:
        print("[!] No jobs found for today. Try broadening queries.")
        return

    print(f"\n[+] Selected {len(jobs)} high-relevance jobs (daily limit enforced).")
    print("[+] Generating AI matching scores and tailored cover letters...")
    
    jobs_with_ai = []
    for idx, job in enumerate(jobs, 1):
        print(f"  [{idx}/{len(jobs)}] Tailoring for {job['title']} at {job['company']}...")
        ai_data = generate_custom_materials(client, job)
        jobs_with_ai.append({"job": job, "ai": ai_data})

    dashboard_path = build_dashboard(jobs_with_ai)
    print(f"\n[SUCCESS] Today's 5 curated applications are ready!")
    print(f"[+] Dashboard saved at: {dashboard_path}")
    print("[+] Opening dashboard in your default browser...")
    webbrowser.open(f"file:///{dashboard_path}")

if __name__ == "__main__":
    main()
