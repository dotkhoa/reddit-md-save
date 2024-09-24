import os
import praw
import requests
from redvid import Downloader
import yt_dlp
import re
from datetime import datetime
import markdown2

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
    md = f"## Post\n\n"
    md += f"**Title:** {post.title}\n\n"
    md += f"**Subreddit:** /r/{str(post.subreddit)}\n\n"
    md += f"**Author:** {f'/u/{post.author.name}' if post.author else '[deleted]'}\n\n"
    md += f"**Link:** [Reddit](https://reddit.com{post.permalink}) | [Content]({post.url})\n\n"
    md += f"**ID:** {post.id}\n\n"
    md += f"**Body:**\n\n{post.selftext}\n\n"
    md += f"**Date:** {dt.strftime('%d %B, %Y')}\n\n"
    return md


def save_media(post, location):
    """Takes a post object and tries to download any image/video it might be
    associated with. If it can, it will return the filename."""

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
        if media_type.startswith("image") or media_type.startswith("video"):
            with open(os.path.join(location, "media", filename), "wb") as f:
                f.write(response.content)
                return filename

    # Is this a v.redd.it link?
    if domain == "redd.it":
        downloader = Downloader(max_q=True, log=False)
        downloader.url = url
        current = os.getcwd()
        try:
            name = downloader.download()
            extension = name.split(".")[-1]
            filename = f"{readable_name}_{post.id}.{extension}"
            os.rename(name, os.path.join(location, "media", filename))
            return filename
        except:
            os.chdir(current)
            return None

    # Is it a gfycat link that redirects? Update the URL if possible
    if domain == "gfycat.com":
        html = requests.get(post.url).content
        if len(html) < 50000:
            match = re.search(r"http([\dA-Za-z\+\:\/\.]+)\.mp4", html.decode())
            if match:
                url = match.group()
            else:
                return None

    # Is this an imgur image?
    if domain == "imgur.com" and extension != "gifv":
        for extension in IMAGE_EXTENSIONS:
            direct_url = f'https://i.{url[url.find("//") + 2:]}.{extension}'
            direct_url = direct_url.replace("i.imgur.com", "imgur.com")
            direct_url = direct_url.replace("m.imgur.com", "imgur.com")
            try:
                response = requests.get(direct_url)
            except: continue
            if response.status_code == 200:
                filename = f"{readable_name}_{post.id}.{extension}"
                with open(os.path.join(location, "media", filename), "wb") as f:
                    f.write(response.content)
                    return filename

    # Try to use youtube_dl if it's one of the possible domains
    if domain in PLATFORMS:
        options = {
            "nocheckcertificate": True, "quiet": True, "no_warnings": True,
            "ignoreerrors": True, "no-progress": True,
            "outtmpl": os.path.join(
                location, "media", f"{readable_name}_{post.id}" + ".%(ext)s"
            )
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            try:
                ydl.download([url])
            except:
                os.chdir(current)
                return
        for f in os.listdir(os.path.join(location, "media")):
            if f.startswith(f"{readable_name}_{post.id}"):
                return f


def add_media_preview_to_markdown(post_md, media):
    """Takes post markdown and returns a modified version with the preview
    inserted."""

    extension = media.split(".")[-1]
    location = f"media/{media}"
    if extension in IMAGE_EXTENSIONS:
        return post_md + f"![Preview]({location})\n\n"
    if extension in VIDEO_EXTENSIONS:
        return post_md + f"[Video]({location})\n\n"
    return post_md


def create_post_page_markdown(post, post_md):
    """Creates the markdown for a post's own page."""

    md = f"# {post.title}\n\n"
    md += post_md
    md += "\n## Comments\n\n"
    post.comments.replace_more(limit=0)
    for comment in post.comments:
        md += get_comment_markdown(comment, op=post.author.name if post.author else None)
    return md


def get_comment_markdown(comment, children=True, op=None, level=0):
    """Takes a post object and creates a markdown for it - it will get its children
    too unless you specify otherwise."""

    dt = datetime.utcfromtimestamp(comment.created_utc)
    author = "[deleted]"
    if comment.author:
        if comment.author == op:
            author = f'**/u/{comment.author.name} (OP)**'
        else:
            author = f"/u/{comment.author.name}"
    md = f"{'#' * (level + 3)} Comment\n\n"
    md += f"**Author:** {author}\n\n"
    md += f"**Body:**\n\n{comment.body}\n\n"
    md += f"**Score:** {comment.score}\n\n"
    md += f"**Link:** [Comment](https://reddit.com{comment.permalink})\n\n"
    md += f"**ID:** {comment.id}\n\n"
    md += f"**Date:** {dt.strftime('%H:%M - %d %B, %Y')}\n\n"
    if children:
        for child in comment.replies:
            md += get_comment_markdown(child, children=False, op=op, level=level+1)
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
