#!/usr/bin/env python 

import argparse
import os
import re
from tqdm import tqdm
from utilities import *

# Get arguments
def validate_mode(mode):
    if mode not in ["saved", "upvoted"] and not mode.startswith("user:"):
        raise argparse.ArgumentTypeError(f"Invalid mode: {mode}")
    return mode
parser = argparse.ArgumentParser(description="Save reddit posts to file.")
parser.add_argument("mode", type=validate_mode, nargs=1, help="The file to convert.")
if os.getenv("DOCKER", "0") != "1":
    parser.add_argument("location", type=str, nargs=1, help="The path to save to.")
# Optional page size argument
parser.add_argument("--page-size", type=int, nargs=1, default=[0], help="The number of posts to save per page.")
# Add new argument for video download toggle
parser.add_argument("--download-videos", action="store_true", help="Download videos instead of just linking to them.")
args = parser.parse_args()
mode = args.mode[0]
page_size = args.page_size[0]
location = "./archive/" if os.getenv("DOCKER", "0") == "1" else args.location[0]
download_videos = args.download_videos

# Create the location directory if it doesn't exist
if not os.path.exists(location):
    os.makedirs(location)
    print(f"Created directory: {location}")
elif not os.path.isdir(location):
    print(f"Error: {location} exists but is not a directory")
    exit(1)

# Make a client object
client = make_client()

# Saved posts or upvoted posts?
if mode == "saved":
    html_file = "saved.html"
    get_posts = get_saved_posts
    get_comments = get_saved_comments
elif mode == "upvoted":
    html_file = "upvoted.html"
    get_posts = get_upvoted_posts
    get_comments = lambda client: []
elif mode.startswith("user:"):
    username = mode.split(":")[-1]
    html_file = f"{username}.html"
    get_posts = lambda client: get_user_posts(client, username)
    get_comments = lambda client: get_user_comments(client, username)

# Make directory for media and posts
if not os.path.exists(os.path.join(location, "Attachments")):
    os.mkdir(os.path.join(location, "Attachments"))
if not os.path.exists(os.path.join(location, "Posts")):
    os.mkdir(os.path.join(location, "Posts"))

# Get files to search through
print("Getting previously saved posts and comments...")
existing_ids, existing_posts_md, existing_comments_md = get_previous(location, f"{html_file.replace('.html', '.md')}")
print(len(existing_posts_md), "previous posts.")
print(len(existing_comments_md), "previous comments.")

# Get posts markdown
posts_md = []
posts = [p for p in get_posts(client) if p.id not in existing_ids]
if not posts:
    print("No new posts")
else:
    for post in tqdm(posts):
        post_md = get_post_markdown(post)
        media = save_media(post, location, download_videos)
        if media:
            post_md = add_media_preview_to_markdown(post_md, media, download_videos)
        posts_md.append(post_md)
        page_md = create_post_page_markdown(post, post_md)
        with open(os.path.join(location, "Posts", f"{post.id}.md"), "w", encoding="utf-8") as f:
            f.write(page_md)
posts_md += existing_posts_md

# Get comments markdown
comments_md = []
comments = [c for c in get_comments(client) if c.id not in existing_ids]
if not comments:
    print("No new comments")
else:
    for comment in tqdm(comments):
        comment_md = get_comment_markdown(comment)
        comments_md.append(comment_md)
comments_md += existing_comments_md

# Save overall markdown
print("Saving markdown...")
if page_size:
    length = max(len(posts_md), len(comments_md))
    page_count = (length // page_size) + 1
    for i in range(page_count):
        posts_on_page = posts_md[i*page_size:(i+1)*page_size]
        comments_on_page = comments_md[i*page_size:(i+1)*page_size]
        has_next = i < page_count - 1
        save_markdown(posts_on_page, comments_on_page, location, f"{html_file.replace('.html', '.md')}", i, has_next, username=html_file.split(".")[0])
save_markdown(posts_md, comments_md, location, f"{html_file.replace('.html', '.md')}", None, False, username=html_file.split(".")[0])
