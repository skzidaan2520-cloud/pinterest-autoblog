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
from google.auth.transport.requests import Request

os.makedirs("pins", exist_ok=True)
os.makedirs("blog_images", exist_ok=True)

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
    client = genai.Client(api_key=gemini_key, http_options={"timeout": 35000})
    prompt = f"""
    You are a viral Tier-1 (USA/UK) Pinterest & SEO Home Decor Blogger in the '{niche}' niche.
    Topic: "{topic}"

    Match the exact number of sections to the number mentioned in "{topic}" (if no number is mentioned, generate 10 sections).

    Return ONLY a valid JSON object (no markdown backticks) with these exact keys:
    1. "blog_title": Catchy SEO listicle title for USA audience.
    2. "hero_image_prompt": Wide editorial interior photography prompt (no text, no words) capturing the overall aesthetic of '{topic}'.
    3. "intro_html": Engaging 2-paragraph HTML introduction (<p> tags only).
    4. "sections": A list of objects (one for each idea), each having:
       - "heading": Numbered section heading (e.g., "1. Boucle Corner Chair with a Clip-On Reading Lamp")
       - "image_prompt": Detailed vertical interior design photography prompt (no text, no words, no watermarks) showing this exact cozy decor setup in warm natural sunlight, editorial magazine style.
       - "body_html": 2 detailed, practical paragraphs in HTML (<p> and <ul>/<li> tags) explaining how renters can recreate this look on a budget.
       - "pin_headline": Short, aesthetic 3 to 6 words Pinterest title (Title Case, NOT all caps, e.g., "The Coziest Corner" or "Cozy Bedroom Reading Nook").
       - "pin_title": SEO Pinterest title (max 90 chars).
       - "pin_description": Engaging Pinterest description with 4 relevant hashtags (max 300 chars).
    5. "conclusion_html": Short encouraging closing paragraph (<p> tag).
    """

    response = None
    candidates = [
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-pro-latest"
    ]
    for m_name in candidates:
        try:
            print(f"Trying model: {m_name}...", flush=True)
            response = client.models.generate_content(model=m_name, contents=prompt)
            print(f"Success with model: {m_name}", flush=True)
            break
        except Exception as e:
            print(f"Skipped {m_name}: {e}", flush=True)
            time.sleep(2)
            continue

    if not response:
        available = [
            m.name.replace("models/", "")
            for m in client.models.list()
            if "generateContent" in (m.supported_actions or [])
            and "2.5" not in m.name
            and "2.0" not in m.name
            and "1.5" not in m.name
            and "image" not in m.name
            and "tts" not in m.name
        ]
        print(f"Available filtered models: {available}", flush=True)
        for m_name in available:
            try:
                print(f"Trying fallback: {m_name}...", flush=True)
                response = client.models.generate_content(model=m_name, contents=prompt)
                print(f"Success with fallback: {m_name}", flush=True)
                break
            except Exception as e:
                print(f"Skipped fallback {m_name}: {e}", flush=True)
                continue

    if not response:
        raise RuntimeError("No working Gemini model responded within timeout.")

    raw = response.text.strip()
    if raw.startswith("```json"):
        raw = raw[7:-3].strip()
    elif raw.startswith("```"):
        raw = raw[3:-3].strip()
    return json.loads(raw)

def fetch_image(prompt_text, save_path, width=1000, height=1500):
    orientation = "wide horizontal framing" if width > height else "vertical 2:3 framing"
    encoded = requests.utils.quote(
        f"{prompt_text}, architectural digest interior photography, warm natural light, cozy aesthetic, 8k photorealistic, {orientation}, no text"
    )
    img_url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&seed={random.randint(1,99999)}"
    for attempt in range(2):
        try:
            resp = requests.get(img_url, timeout=18)
            if resp.status_code == 200 and len(resp.content) > 8000:
                img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
                img.save(save_path, "JPEG", quality=92)
                return True
        except Exception:
            time.sleep(1)
    return False

def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines, current = [], ""
    for w in words:
        test = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines[:3]

def create_editorial_pin(clean_img_path, headline, pin_save_path, style_index):
    base = Image.open(clean_img_path).convert("RGB").resize((1000, 1500), Image.Resampling.LANCZOS)
    try:
        font_xl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 62)
        font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 54)
        font_tag = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except Exception:
        font_xl = font_lg = font_md = font_tag = ImageFont.load_default()

    style = style_index % 5

    if style == 0:
        canvas = Image.new("RGB", (1000, 1500), (249, 246, 241))
        draw = ImageDraw.Draw(canvas)
        lines = wrap_text(headline, font_lg, 880, draw)
        header_h = 110 + (len(lines) * 80)
        photo_h = 1500 - header_h
        canvas.paste(base.resize((1000, photo_h), Image.Resampling.LANCZOS), (0, header_h))

        y = 55
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_lg)
            x = (1000 - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, fill=(43, 40, 37), font=font_lg)
            y += 80
        canvas.save(pin_save_path, "JPEG", quality=93)

    elif style == 1:
        rgba = base.convert("RGBA")
        overlay = Image.new("RGBA", (1000, 1500), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        for y in range(430):
            alpha = int(125 * (1 - (y / 430)))
            ov_draw.line([(0, y), (1000, y)], fill=(255, 250, 245, alpha))
        merged = Image.alpha_composite(rgba, overlay).convert("RGB")
        draw = ImageDraw.Draw(merged)

        lines = wrap_text(headline, font_xl, 860, draw)
        y = 65
        for line in lines:
            draw.text((70, y), line, fill=(43, 40, 37), font=font_xl)
            y += 88
        merged.save(pin_save_path, "JPEG", quality=93)

    elif style == 2:
        rgba = base.convert("RGBA")
        overlay = Image.new("RGBA", (1000, 1500), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)

        lines = wrap_text(headline, font_md, 760, ov_draw)
        card_h = 140 + (len(lines) * 72)
        y1 = (1500 - card_h) // 2
        y2 = y1 + card_h
        ov_draw.rounded_rectangle([90, y1, 910, y2], radius=24, fill=(252, 249, 244, 232))

        merged = Image.alpha_composite(rgba, overlay).convert("RGB")
        draw = ImageDraw.Draw(merged)

        tag_text = "HOME DECOR INSPIRATION"
        tbbox = draw.textbbox((0, 0), tag_text, font=font_tag)
        draw.text(((1000 - (tbbox[2] - tbbox[0])) // 2, y1 + 36), tag_text, fill=(140, 110, 88), font=font_tag)

        y = y1 + 85
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_md)
            x = (1000 - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, fill=(38, 35, 32), font=font_md)
            y += 72
        merged.save(pin_save_path, "JPEG", quality=93)

    elif style == 3:
        rgba = base.convert("RGBA")
        overlay = Image.new("RGBA", (1000, 1500), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        for y in range(950, 1500):
            alpha = int(190 * ((y - 950) / 550))
            ov_draw.line([(0, y), (1000, y)], fill=(20, 18, 16, alpha))
        merged = Image.alpha_composite(rgba, overlay).convert("RGB")
        draw = ImageDraw.Draw(merged)

        lines = wrap_text(headline, font_lg, 860, draw)
        y = 1420 - (len(lines) * 80)
        for line in lines:
            draw.text((70, y), line, fill=(255, 255, 255), font=font_lg)
            y += 80
        merged.save(pin_save_path, "JPEG", quality=93)

    else:
        canvas = Image.new("RGB", (1000, 1500), (246, 242, 235))
        draw = ImageDraw.Draw(canvas)
        lines = wrap_text(headline, font_md, 840, draw)
        footer_h = 110 + (len(lines) * 72)
        photo_h = 1500 - footer_h - 45
        canvas.paste(base.resize((910, photo_h), Image.Resampling.LANCZOS), (45, 45))

        y = 45 + photo_h + 38
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_md)
            x = (1000 - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, fill=(43, 40, 37), font=font_md)
            y += 72
        canvas.save(pin_save_path, "JPEG", quality=93)

def build_blog_and_pins(data, slug, repo_owner, repo_name):
    html_parts = []

    print("Generating Blog Hero Image...", flush=True)
    hero_file = f"blog_images/{slug}_hero.jpg"
    if data.get("hero_image_prompt") and fetch_image(data["hero_image_prompt"], hero_file, 1200, 675):
        hero_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/main/{hero_file}"
        html_parts.append(
            f'<div style="margin:20px 0;text-align:center;">'
            f'<img src="{hero_url}" alt="{data["blog_title"]}" style="width:100%;max-width:800px;border-radius:12px;box-shadow:0 4px 14px rgba(0,0,0,0.1);">'
            f'</div>'
        )

    html_parts.append(data.get("intro_html", ""))
    generated_pins = []

    sections = data.get("sections", [])
    for idx, sec in enumerate(sections, start=1):
        print(f"Processing Section {idx}/{len(sections)}: {sec['heading']}", flush=True)
        html_parts.append(f"<h2>{sec['heading']}</h2>")

        clean_img_file = f"blog_images/{slug}_sec_{idx}.jpg"
        img_ok = fetch_image(sec["image_prompt"], clean_img_file, 1000, 1500)

        if img_ok:
            clean_img_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/main/{clean_img_file}"
            html_parts.append(
                f'<div style="margin:18px 0;text-align:center;">'
                f'<img src="{clean_img_url}" alt="{sec["heading"]}" style="width:100%;max-width:620px;border-radius:12px;box-shadow:0 4px 14px rgba(0,0,0,0.08);">'
                f'</div>'
            )

            pin_file = f"pins/{slug}_pin_{idx}.jpg"
            create_editorial_pin(clean_img_file, sec["pin_headline"], pin_file, idx - 1)
            generated_pins.append({
                "pin_title": sec["pin_title"],
                "pin_description": sec["pin_description"],
                "image_path": pin_file
            })

        html_parts.append(sec.get("body_html", ""))

    html_parts.append(data.get("conclusion_html", ""))
    return "\n".join(html_parts), generated_pins

def publish_blogger(blogger_token, client_id, client_secret, refresh_token, blog_id, title, html_content):
    if not blog_id or (not blogger_token and not refresh_token):
        return f"https://demo-blog.blogspot.com/{int(time.time())}.html"

    if refresh_token and client_id and client_secret:
        creds = Credentials(
            token=blogger_token or None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/blogger"]
        )
        creds.refresh(Request())
        print("Auto-refreshed permanent Blogger token!", flush=True)
    else:
        creds = Credentials(token=blogger_token)

    service = build("blogger", "v3", credentials=creds)
    body = {"kind": "blogger#post", "blog": {"id": blog_id}, "title": title, "content": html_content}
    post = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
    return post.get("url")

def save_to_queue(generated_pins, blog_url, gap_hours):
    queue = []
    if os.path.exists("pin_queue.json"):
        with open("pin_queue.json", "r", encoding="utf-8") as f:
            queue = json.load(f)

    now = datetime.now(timezone.utc)
    for i, pin in enumerate(generated_pins):
        sched_time = now if i == 0 else now + timedelta(hours=gap_hours * i)
        queue.append({
            "title": pin["pin_title"],
            "description": pin["pin_description"],
            "image_path": pin["image_path"],
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
                res = requests.post("https://api.pinterest.com/v5/pins", headers=headers, json=payload, timeout=20)
                if res.status_code in [200, 201]:
                    item["posted"] = True
                    updated = True
                    print(f"Posted Pin: {item['title']}", flush=True)
                else:
                    print(f"Pinterest Error: {res.text}", flush=True)
            else:
                item["posted"] = True
                updated = True
                print(f"[Demo Mode] Marked Pin as Posted: {item['title']}", flush=True)

    if updated:
        with open("pin_queue.json", "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)

def update_dashboard():
    queue = []
    if os.path.exists("pin_queue.json"):
        with open("pin_queue.json", "r", encoding="utf-8") as f:
            queue = json.load(f)

    cards = ""
    for item in reversed(queue[-30:]):
        status = "✅ Live on Pinterest" if item["posted"] else f"⏰ Scheduled ({item['scheduled_utc'][:16]} UTC)"
        cards += f"""
        <div style="background:#1e293b;border-radius:10px;overflow:hidden;border:1px solid #334155;">
            <img src="{item['image_path']}" style="width:100%;height:320px;object-fit:cover;">
            <div style="padding:12px;">
                <div style="font-size:11px;color:#fbbf24;margin-bottom:4px;">{status}</div>
                <div style="font-size:14px;font-weight:bold;color:#fff;margin-bottom:6px;">{item['title']}</div>
                <a href="{item['blog_url']}" target="_blank" style="font-size:12px;color:#38bdf8;">View Blog Post →</a>
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>AutoBlog & Pinterest Dashboard</title></head>
    <body style="background:#0f172a;color:#f8fafc;font-family:sans-serif;padding:24px;max-width:1200px;margin:auto;">
        <h1 style="color:#fbbf24;">⚡ AutoBlog & Editorial Pinterest Dashboard</h1>
        <p style="color:#94a3b8;">Last Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px;margin-top:24px;">
            {cards if cards else "<p>No pins generated yet. Run the workflow from GitHub Actions!</p>"}
        </div>
    </body></html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    blogger_token = os.getenv("BLOGGER_TOKEN", "").strip()
    client_id = os.getenv("BLOGGER_CLIENT_ID", "").strip()
    client_secret = os.getenv("BLOGGER_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("BLOGGER_REFRESH_TOKEN", "").strip()
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
            print(f"Generating content for topic: {topic}", flush=True)
            data = generate_content(gemini_key, topic, niche)
            slug = f"post_{int(time.time())}"
            full_html, generated_pins = build_blog_and_pins(data, slug, repo_owner, repo_name)
            blog_url = publish_blogger(blogger_token, client_id, client_secret, refresh_token, blog_id, data["blog_title"], full_html)
            save_to_queue(generated_pins, blog_url, gap_hours)
            print(f"Blog published & {len(generated_pins)} editorial pins queued: {blog_url}", flush=True)
        else:
            print("No new topics left in topics.txt", flush=True)

    process_due_pins(pinterest_token, board_id, repo_owner, repo_name)
    update_dashboard()
