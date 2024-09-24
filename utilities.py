import os
import praw
import requests
from redvid import Downloader
import yt_dlp
import re
from datetime import datetime
import markdown2
import yaml

try:
    from logindata import REDDIT_USERNAME, REDDIT_PASSWORD
    from logindata import REDDIT_CLIENT_ID, REDDIT_SECRET
except ImportError:
    REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
    REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
    REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
    REDDIT_SECRET = os.getenv("REDDIT_SECRET")

IMAGE_EXTENSIONS = ["gif", "gifv", "jpg", "jpeg", "png"]
VIDEO_EXTENSIONS = ["mp4"]
PLATFORMS = ["redgifs.com", "gfycat.com", "imgur.com", "youtube.com"]


def make_client():
    """Creates a PRAW client with the details in the secrets.py file."""

    print(REDDIT_USERNAME)

    return praw.Reddit(
        username=REDDIT_USERNAME,
        password=REDDIT_PASSWORD,
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_SECRET,
        user_agent="reddit-save",
    )


def get_previous(location, md_file):
    md_files = [f for f in os.listdir(location) if f.endswith(".md")]
    pattern = md_file.replace(".md", r"\.(\d+)?\.md")
    matches = [re.match(pattern, f) for f in md_files]
    matches = [m[0] for m in matches if m]
    matches.sort(key=lambda x: int(x.split(".")[1]))
    existing_ids = []
    existing_posts_md = []
    existing_comments_md = []
    if md_file in md_files: matches.append(md_file)
    for match in matches:
        with open(os.path.join(location, match), encoding="utf-8") as f:
            current_md = f.read()
            for id in re.findall(r'\n\*\*ID:\*\* (.+?)\n', current_md):
                if id not in existing_ids:
                    existing_ids.append(id)
            posts = re.findall(
                r'(## Post[\S\n\t\v ]+?(?=\n## Post|\Z))',
                current_md
            )
            comments = re.findall(
                r'(### Comment[\S\n\t\v ]+?(?=\n### Comment|\Z))',
                current_md
            )
            existing_posts_md.extend(posts)
            existing_comments_md.extend(comments)
    return existing_ids, existing_posts_md, existing_comments_md


def get_saved_posts(client):
    """Gets a list of posts that the user has saved."""

    return [
        saved for saved in client.user.me().saved(limit=None)
        if saved.__class__.__name__ == "Submission"
    ]


def get_upvoted_posts(client):
    """Gets a list of posts that the user has upvoted."""

    return [
        upvoted for upvoted in client.user.me().upvoted(limit=None)
        if upvoted.__class__.__name__ == "Submission"
    ]


def get_saved_comments(client):
    """Gets a list of comments that the user has saved."""

    return [
        saved for saved in client.user.me().saved(limit=None)
        if saved.__class__.__name__ != "Submission"
    ]


def get_user_posts(client, username):
    """Gets a list of posts that the user has made."""

    return [
        post for post in client.redditor(username).submissions.new(limit=None)
    ]


def get_user_comments(client, username):
    """Gets a list of comments that the user has made."""

    return [
        comment for comment in client.redditor(username).comments.new(limit=None)
    ]


def get_post_markdown(post):
    dt = datetime.utcfromtimestamp(post.created_utc)
    
    # Prepare the front matter data in the specified order
    front_matter = {
        'title': post.title,
        'author': post.author.name if post.author else "[deleted]",
        'subreddit': str(post.subreddit),
        'upvotes': post.score,
        'created': dt.strftime("%Y-%m-%d %H:%M:%S"),
        'published': dt.strftime("%Y-%m-%d %H:%M:%S"),
        'source': f"https://www.reddit.com{post.permalink}",
        'id': post.id,
        'tags': ["reddit"]
    }
    
    # Convert to YAML and handle any parsing errors
    try:
        yaml_content = yaml.safe_dump(front_matter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except yaml.YAMLError as e:
        print(f"Error creating YAML for post {post.id}: {e}")
        # Fallback to a simpler front matter if YAML creation fails
        yaml_content = f"""---
title: "{post.title}"
author: "{front_matter['author']}"
subreddit: "{front_matter['subreddit']}"
upvotes: {front_matter['upvotes']}
created: "{front_matter['created']}"
published: "{front_matter['published']}"
source: "{front_matter['source']}"
id: {post.id}
tags:
  - reddit
---
"""
    
    md = f"---\n{yaml_content}---\n\n"
    
    # Add description after front matter
    if post.selftext:
        md += f"{post.selftext}\n\n"
    
    return md


def save_media(post, location, download_videos=False):
    """Takes a post object and tries to download any image/video it might be
    associated with. If it can, it will return the filename or URL."""

    url = post.url
    stripped_url = url.split("?")[0]
    if url.endswith(post.permalink): return None

    # What is the key information?
    extension = stripped_url.split(".")[-1].lower()
    domain = ".".join(post.url.split("/")[2].split(".")[-2:])
    readable_name = list(filter(bool, post.permalink.split("/")))[-1]

    # If it's an imgur gallery, forget it
    if domain == "imgur.com" and "gallery" in url: return None

    # Can the media be obtained directly?
    if extension in IMAGE_EXTENSIONS + VIDEO_EXTENSIONS:
        filename = f"{readable_name}_{post.id}.{extension}"
        try:
            response = requests.get(post.url)
        except:
            return
        media_type = response.headers.get("Content-Type", "")
        if media_type.startswith("image") or (media_type.startswith("video") and download_videos):
            with open(os.path.join(location, "Attachments", filename), "wb") as f:
                f.write(response.content)
            return filename
        elif media_type.startswith("video"):
            return post.url

    # Is this a v.redd.it link?
    if domain == "redd.it" and download_videos:
        downloader = Downloader(max_q=True, log=False)
        downloader.url = url
        try:
            filename = downloader.download()
            new_filename = f"{readable_name}_{post.id}.{filename.split('.')[-1]}"
            os.rename(filename, os.path.join(location, "Attachments", new_filename))
            return new_filename
        except:
            return url

    # Is it a gfycat link that redirects? Update the URL if possible
    if domain == "gfycat.com":
        html = requests.get(post.url).content
        if len(html) < 50000:
            match = re.search(r"http([\dA-Za-z\+\:\/\.]+)\.mp4", html.decode())
            if match:
                url = match.group()

    # Is this an imgur image?
    if domain == "imgur.com" and extension != "gifv":
        for ext in IMAGE_EXTENSIONS:
            direct_url = f'https://i.{url[url.find("//") + 2:]}.{ext}'
            direct_url = direct_url.replace("i.imgur.com", "imgur.com")
            direct_url = direct_url.replace("m.imgur.com", "imgur.com")
            try:
                response = requests.get(direct_url)
            except: continue
            if response.status_code == 200:
                filename = f"{readable_name}_{post.id}.{ext}"
                with open(os.path.join(location, "Attachments", filename), "wb") as f:
                    f.write(response.content)
                return filename

    # Try to use youtube_dl if it's one of the possible domains and we're downloading videos
    if domain in PLATFORMS and download_videos:
        options = {
            "nocheckcertificate": True, "quiet": True, "no_warnings": True,
            "ignoreerrors": True, "no-progress": True,
            "outtmpl": os.path.join(location, "Attachments", f"{readable_name}_{post.id}.%(ext)s")
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            try:
                ydl.download([url])
                for f in os.listdir(os.path.join(location, "Attachments")):
                    if f.startswith(f"{readable_name}_{post.id}"):
                        return f
            except:
                return url

    return url if not download_videos else None


def add_media_preview_to_markdown(post_md, media, download_videos=False):
    """Takes post markdown and returns a modified version with the preview
    inserted."""

    if media.startswith("http"):
        preview = f"[Video]({media})\n\n"
    else:
        extension = media.split(".")[-1]
        location = f"Attachments/{media}"
        if extension in IMAGE_EXTENSIONS:
            preview = f"![Preview]({location})\n\n"
        elif extension in VIDEO_EXTENSIONS:
            preview = f"[Video]({location})\n\n"
    
    if preview:
        parts = post_md.split("---\n", 2)
        if len(parts) == 3:
            # Insert preview after front matter and description
            return f"{parts[0]}---\n{parts[1]}---\n\n{parts[2]}{preview}"
    
    return post_md


def create_post_page_markdown(post, post_md):
    """Creates the markdown for a post's own page, including only the top 10 parent comments."""

    md = post_md  # This now includes the front matter
    md += "\n## Comments:\n\n"
    
    # Sort comments by score and get top 10 parent comments
    top_comments = sorted(
        [comment for comment in post.comments if not isinstance(comment, praw.models.MoreComments)],
        key=lambda x: x.score,
        reverse=True
    )[:10]
    
    for comment in top_comments:
        md += get_comment_markdown(comment, op=post.author.name if post.author else None)
    
    return md


def get_comment_markdown(comment, op=None):
    """Creates markdown for a single comment without its children."""

    dt = datetime.utcfromtimestamp(comment.created_utc)
    author = "[deleted]"
    if comment.author:
        if comment.author == op:
            author = f'**/u/{comment.author.name}** (OP)'
        else:
            author = f'**/u/{comment.author.name}**'
    
    md = f"* {author} - {dt.strftime('%H:%M - %d %B, %Y')} - Score: {comment.score}\n\n"
    md += f"  {comment.body.replace(chr(10), chr(10) + '  ')}\n\n"
    
    return md


def save_markdown(posts, comments, location, md_file, page, has_next, username=None):
    md = f"# {'Saved' if 'saved' in md_file else 'Upvoted' if 'upvoted' in md_file else username + '\'s'} Posts and Comments\n\n"
    if page is not None:
        if page > 0:
            md += f"[Previous]({md_file.replace('.md', f'.{page-1}.md')}) | "
        if has_next:
            md += f"[Next]({md_file.replace('.md', f'.{page+1}.md')})"
        md += "\n\n"
    md += "## Posts\n\n"
    md += "\n".join(posts)
    md += "\n\n## Comments\n\n"
    md += "\n".join(comments)
    file_name = md_file if page is None else md_file.replace(".md", f".{page}.md")
    with open(os.path.join(location, file_name), "w", encoding="utf-8") as f:
        f.write(md)
