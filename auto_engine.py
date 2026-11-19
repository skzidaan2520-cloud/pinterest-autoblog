import os
import io
import json
import time
import random
import requests
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
from google import genai
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

os.makedirs("pins", exist_ok=True)

PIN_THEMES = [
    {"bg": (255, 248, 240), "box": (30, 41, 59), "text": (255, 255, 255), "accent": (245, 158, 11)},
    {"bg": (240, 253, 244), "box": (20, 83, 45), "text": (255, 255, 255), "accent": (134, 239, 172)},
    {"bg": (253, 242, 248), "box": (131, 24, 67), "text": (255, 255, 255), "accent": (249, 168, 212)},
    {"bg": (239, 246, 255), "box": (30, 58, 138), "text": (255, 255, 255), "accent": (147, 197, 253)},
    {"bg": (250, 250, 249), "box": (24, 24, 27), "text": (255, 255, 255), "accent": (251, 113, 133)},
]

def get_next_topic():
    if not os.path.exists("topics.txt"):
        return None
    with open("topics.txt", "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if not lines:
        return None
    topic = lines[0]
    with open("topics.txt", "w", encoding="utf-8") as f:
        for line in lines[1:]:
            f.write(line + "\n")
    return topic

def generate_content(gemini_key, topic, niche):
    client = genai.Client(api_key=gemini_key)
    prompt = f"""
    You are a viral Tier-1 (USA/UK) Pinterest & SEO Blogger in the '{niche}' niche.
    Topic: "{topic}"

    Return ONLY a valid JSON object (no markdown backticks) with these exact keys:
    1. "blog_title": Catchy SEO listicle title for USA audience.
    2. "blog_html": Complete, engaging 800-word HTML listicle article (use <h2>, <p>, <ul>, <li> tags only). Include 7-10 actionable tips.
    3. "image_prompt": A clean, aesthetic photography prompt (no text in image) related to '{topic}' for background visual.
    4. "pins": A list of 5 objects, each having:
       - "pin_headline": Short 4-7 words punchy text to put ON the Pinterest image.
       - "pin_title": SEO Pinterest title (max 90 chars).
       - "pin_description": Engaging Pinterest description with 4 relevant hashtags (max 300 chars).
    """

    response = None
    candidates = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-flash-latest"]
    for m_name in candidates:
        try:
            response = client.models.generate_content(model=m_name, contents=prompt)
            print(f"Used model: {m_name}")
            break
        except Exception as e:
            print(f"Skipped {m_name}: {e}")
            continue

    if not response:
        available = [
            m.name.replace("models/", "")
            for m in client.models.list()
            if "generateContent" in (m.supported_actions or [])
        ]
        print(f"Auto-detected available models: {available}")
        response = client.models.generate_content(model=available[0], contents=prompt)

    raw = response.text.strip()
    if raw.startswith("```json"):
        raw = raw[7:-3].strip()
    elif raw.startswith("```"):
        raw = raw[3:-3].strip()
    return json.loads(raw)

def create_5_pins(image_prompt, pins_data, slug):
    pin_files = []
    encoded_prompt = requests.utils.quote(f"{image_prompt}, aesthetic interior lifestyle photography, bright natural lighting, vertical")
    img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1000&height=1500&nologo=true&seed={random.randint(1,9999)}"
    
    base_img = None
    try:
        resp = requests.get(img_url, timeout=30)
        if resp.status_code == 200:
            base_img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((1000, 1500))
    except Exception:
        base_img = None

    for idx, pin_info in enumerate(pins_data[:5]):
        theme = PIN_THEMES[idx % len(PIN_THEMES)]
        canvas = base_img.copy() if base_img else Image.new("RGB", (1000, 1500), theme["bg"])
        draw = ImageDraw.Draw(canvas)
        
        if idx % 3 == 0:
            box_coords = [60, 520, 940, 980]
        elif idx % 3 == 1:
            box_coords = [60, 120, 940, 560]
        else:
            box_coords = [60, 920, 940, 1380]

        draw.rectangle(box_coords, fill=theme["box"], outline=theme["accent"], width=8)

        headline = pin_info["pin_headline"].upper()
        words = headline.split()
        lines, current = [], ""
        for w in words:
            if len(current + " " + w) <= 18:
                current = (current + " " + w).strip()
            else:
                lines.append(current)
                current = w
        if current:
            lines.append(current)

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()

        y_start = box_coords[1] + 70
        for line in lines[:4]:
            draw.text((110, y_start), line, fill=theme["text"], font=font)
            y_start += 75

        draw.text((110, box_coords[3] - 65), "READ FULL GUIDE ->", fill=theme["accent"], font=small_font)

        filename = f"pins/{slug}_pin_{idx+1}.jpg"
        canvas.save(filename, "JPEG", quality=92)
        pin_files.append(filename)

    return pin_files

def publish_blogger(blogger_token, blog_id, title, html_content):
    if not blogger_token or not blog_id:
        return f"https://demo-blog.blogspot.com/{int(time.time())}.html"
    creds = Credentials(token=blogger_token)
    service = build("blogger", "v3", credentials=creds)
    body = {"kind": "blogger#post", "blog": {"id": blog_id}, "title": title, "content": html_content}
    post = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
    return post.get("url")

def save_to_queue(pins_info, pin_files, blog_url, gap_hours):
    queue = []
    if os.path.exists("pin_queue.json"):
        with open("pin_queue.json", "r", encoding="utf-8") as f:
            queue = json.load(f)

    now = datetime.now(timezone.utc)
    for i, pin in enumerate(pins_info[:5]):
        sched_time = now if i == 0 else now + timedelta(hours=gap_hours * i)
        queue.append({
            "title": pin["pin_title"],
            "description": pin["pin_description"],
            "image_path": pin_files[i],
            "blog_url": blog_url,
            "scheduled_utc": sched_time.isoformat(),
            "posted": False
        })

    with open("pin_queue.json", "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)

def process_due_pins(pinterest_token, board_id, repo_owner, repo_name):
    if not os.path.exists("pin_queue.json"):
        return
    with open("pin_queue.json", "r", encoding="utf-8") as f:
        queue = json.load(f)

    now = datetime.now(timezone.utc)
    updated = False
    for item in queue:
        if not item["posted"] and datetime.fromisoformat(item["scheduled_utc"]) <= now:
            raw_img_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/main/{item['image_path']}"
            if pinterest_token and board_id:
                headers = {"Authorization": f"Bearer {pinterest_token}", "Content-Type": "application/json"}
                payload = {
                    "board_id": board_id,
                    "title": item["title"][:100],
                    "description": item["description"][:500],
                    "link": item["blog_url"],
                    "media_source": {"source_type": "image_url", "url": raw_img_url}
                }
                res = requests.post("https://api.pinterest.com/v5/pins", headers=headers, json=payload)
                if res.status_code in [200, 201]:
                    item["posted"] = True
                    updated = True
                    print(f"Posted Pin: {item['title']}")
                else:
                    print(f"Pinterest Error: {res.text}")
            else:
                item["posted"] = True
                updated = True
                print(f"[Demo Mode] Marked Pin as Posted: {item['title']}")

    if updated:
        with open("pin_queue.json", "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)

def update_dashboard():
    queue = []
    if os.path.exists("pin_queue.json"):
        with open("pin_queue.json", "r", encoding="utf-8") as f:
            queue = json.load(f)

    cards = ""
    for item in reversed(queue[-20:]):
        status = "✅ Live on Pinterest" if item["posted"] else f"⏰ Scheduled ({item['scheduled_utc'][:16]} UTC)"
        cards += f"""
        <div style="background:#1e293b;border-radius:10px;overflow:hidden;border:1px solid #334155;">
            <img src="{item['image_path']}" style="width:100%;height:260px;object-fit:cover;">
            <div style="padding:12px;">
                <div style="font-size:11px;color:#fbbf24;margin-bottom:4px;">{status}</div>
                <div style="font-size:14px;font-weight:bold;color:#fff;margin-bottom:6px;">{item['title']}</div>
                <a href="{item['blog_url']}" target="_blank" style="font-size:12px;color:#38bdf8;">View Blog Post →</a>
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>AutoBlog & Pinterest Dashboard</title></head>
    <body style="background:#0f172a;color:#f8fafc;font-family:sans-serif;padding:24px;max-width:1100px;margin:auto;">
        <h1 style="color:#fbbf24;">⚡ AutoBlog & 5-Pin Pinterest Dashboard</h1>
        <p style="color:#94a3b8;">Last Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;margin-top:24px;">
            {cards if cards else "<p>No pins generated yet. Run the workflow from GitHub Actions!</p>"}
        </div>
    </body></html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    blogger_token = os.getenv("BLOGGER_TOKEN", "").strip()
    blog_id = os.getenv("BLOG_ID", "").strip()
    pinterest_token = os.getenv("PINTEREST_TOKEN", "").strip()
    board_id = os.getenv("PINTEREST_BOARD_ID", "").strip()
    niche = os.getenv("NICHE", "Apartment & Renter-Friendly Decor")
    gap_hours = int(os.getenv("GAP_HOURS", "4"))
    repo_owner = os.getenv("GITHUB_REPOSITORY_OWNER", "skzidaan2520-cloud")
    repo_name = "pinterest-autoblog"

    if gemini_key:
        topic = get_next_topic()
        if topic:
            print(f"Generating content for topic: {topic}")
            data = generate_content(gemini_key, topic, niche)
            slug = f"post_{int(time.time())}"
            pin_files = create_5_pins(data["image_prompt"], data["pins"], slug)
            blog_url = publish_blogger(blogger_token, blog_id, data["blog_title"], data["blog_html"])
            save_to_queue(data["pins"], pin_files, blog_url, gap_hours)
            print(f"Blog published & 5 pins queued: {blog_url}")
        else:
            print("No new topics left in topics.txt")

    process_due_pins(pinterest_token, board_id, repo_owner, repo_name)
    update_dashboard()
