# reddit-md-save

A Python utility for backing up your Reddit upvoted/saved posts in Markdown.

Browsing through the stuff you've liked or saved on Reddit is really enjoyable and, depending on the reason you saved something, can be a great way to recap stuff you once thought important. It is a personalised feed of posts and comments by the one person guaranteed to know what you like - past you.

However over time more and more of the older posts will be deleted or missing, and the historical record atrophies. Use this tool to back up those posts and comments to your computer where you can browse them offline, and where they are safe forever.

reddit-md-save will backup saved posts, saved comments, and upvoted posts. It can't do upvoted comments because the Reddit API doesn't expose them. Crucially, when it is run again on the same location it will ignore any posts/comments previously archived - once something is saved, it's saved permanently.

## Installation

```bash
$ git clone https://github.com/dotkhoa/reddit-md-save .
$ cd reddit-md-save
$ pip install -r requirements.txt
```

If you get permission errors, try using `sudo` or using a virtual environment.

You will need [ffmpeg](https://ffmpeg.org/) installed somewhere too.

Rename the file `logindata.py.example` to `logindata.py`. You will need to add four things to this file, your Reddit username and password, and a Reddit client ID and secret. The latter two are obtained using [the instructions here](https://github.com/reddit-archive/reddit/wiki/OAuth2-Quick-Start-Example#first-steps). The file should look something like this:

```python
REDDIT_USERNAME = "spez"
REDDIT_PASSWORD = "myredditpassword123"
REDDIT_CLIENT_ID = "sadsU7-zfX"
REDDIT_SECRET = "687DDJSS&999d-hdkjK8h"
```

(If you have 2FA enabled, you will need to append that to the password, separated by a colon.)

## Useage

Create a folder that will contain your archive. Then run:

```bash
$ python save.py saved folder_name
$ python save.py upvoted folder_name
```

Each post will have its first ten top comments saved.

Linked media files (images, videos etc.) will by default be linked to their original source. You can optionally download and save media files locally by using the `--download-videos` argument. Note that imgur links are currently not well supported in all cases.

### Additional Arguments

- `--download-videos`: Download videos instead of just linking to them.
- `--use-id`: Use post ID as filename instead of title.

Example usage with arguments:
```bash
$ python save.py saved folder_name --download-videos --use-id
```

## Use with Docker

Rather than installing dependencies locally, you can use docker to create a local image and use that instead. First build the image:

```bash
$ docker build -t reddit-md-save .
```

Then run reddit-md-save within a container created from this image:

```bash
$ docker run \
-e REDDIT_USERNAME=spez \
-e REDDIT_PASSWORD="myredditpassword123" \
-e REDDIT_CLIENT_ID="sadsU7-zfX" \
-e REDDIT_SECRET="687DDJSS&999d-hdkjK8h" \
-v /Local/location/to/save/in:/opt/app/archive \
reddit-md-save saved
```

## Backing up a specific username

Rather than backing up your own saved/upvoted posts and comments, you can back up the submitted posts and comments of another user:

```bash
python save.py user:samirelanduk folder_name
```

You can also use the additional arguments mentioned above with this command.