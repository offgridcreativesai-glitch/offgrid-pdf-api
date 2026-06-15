"""
Multi-platform scraping engine.
Handles Apify API calls for Instagram, YouTube, LinkedIn, TikTok, and website crawling.
"""

import os
import re
import json
import time
import logging
import requests as http_requests

logger = logging.getLogger(__name__)

APIFY_ACTORS = {
    'instagram': 'apify/instagram-profile-scraper',
    'instagram_posts': 'apify/instagram-post-scraper',
    'youtube': 'streamers/youtube-channel-scraper',
    'linkedin': 'dev_fusion/Linkedin-Profile-Scraper',
    'tiktok': 'clockworks/tiktok-profile-scraper',
    'website': 'apify/website-content-crawler',
}


def apify_run_actor(actor_name, input_data, timeout_secs=120):
    """Run an Apify actor and return the dataset items."""
    token = os.environ.get('APIFY_TOKEN', '')
    if not token:
        return {'error': 'APIFY_TOKEN not set', 'platform': actor_name}

    actor_id = actor_name.replace('/', '~')
    run_url = f"https://api.apify.com/v2/acts/{actor_id}/runs?token={token}"

    try:
        resp = http_requests.post(run_url, json=input_data, timeout=30)
        resp.raise_for_status()
        run_data = resp.json()['data']
        run_id = run_data['id']
        dataset_id = run_data['defaultDatasetId']

        deadline = time.time() + timeout_secs
        while time.time() < deadline:
            time.sleep(5)
            status_resp = http_requests.get(
                f"https://api.apify.com/v2/actor-runs/{run_id}?token={token}", timeout=15
            )
            status = status_resp.json()['data']['status']
            if status == 'SUCCEEDED':
                items_resp = http_requests.get(
                    f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={token}", timeout=30
                )
                return items_resp.json()
            if status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                return {'error': f'Actor run {status}', 'run_id': run_id}

        return {'error': 'Actor run timed out waiting', 'run_id': run_id}
    except Exception as e:
        return {'error': str(e)}


def scrape_instagram(handle, posts_limit=30):
    """Scrape Instagram profile + recent posts (up to posts_limit)."""
    from .analyst import classify_hooks

    handle = handle.lstrip('@').strip()
    if not handle:
        return None

    data = apify_run_actor(APIFY_ACTORS['instagram'], {
        'usernames': [handle],
        'resultsLimit': 1
    }, timeout_secs=90)

    if not isinstance(data, list) or len(data) == 0:
        return {'platform': 'instagram', 'handle': handle, 'error': 'No data returned', 'raw': data}

    profile = data[0]
    posts = profile.get('latestPosts', [])
    followers = profile.get('followersCount', 0)

    if len(posts) < posts_limit:
        try:
            extra = apify_run_actor(APIFY_ACTORS['instagram_posts'], {
                'directUrls': [f"https://www.instagram.com/{handle}/"],
                'resultsLimit': posts_limit
            }, timeout_secs=120)
            if isinstance(extra, list) and len(extra) > len(posts):
                posts = extra
                logger.info(f"[SCRAPE] Extended posts for @{handle}: {len(posts)} posts via post scraper")
        except Exception as e:
            logger.warning(f"[SCRAPE] Post scraper supplement failed for @{handle}: {e}")

    post_count = len(posts)
    total_likes = sum(p.get('likesCount', 0) for p in posts)
    total_comments = sum(p.get('commentsCount', 0) for p in posts)
    avg_er = ((total_likes + total_comments) / max(followers, 1) / max(post_count, 1)) * 100 if post_count > 0 else 0

    format_counts = {}
    for p in posts:
        raw_type = p.get('type', 'Unknown')
        product_type = p.get('productType', '')
        has_video = bool(p.get('videoUrl'))

        if raw_type == 'Sidecar':
            fmt = 'Carousel'
        elif product_type == 'clips' or (raw_type == 'Video' and not product_type):
            fmt = 'Reel'
        elif has_video and raw_type == 'Image':
            fmt = 'Reel'
        elif raw_type == 'Video' and product_type and product_type != 'clips':
            fmt = 'Video'
        elif raw_type == 'Image':
            fmt = 'Image'
        else:
            fmt = raw_type
        p['_classified_format'] = fmt
        format_counts[fmt] = format_counts.get(fmt, 0) + 1

    total_video_views = sum(p.get('videoViewCount', 0) for p in posts if p.get('videoViewCount'))
    video_posts_with_views = sum(1 for p in posts if p.get('videoViewCount'))
    avg_video_views = round(total_video_views / max(video_posts_with_views, 1)) if video_posts_with_views else 0

    captions = [p.get('caption', '') or '' for p in posts]
    hook_types = classify_hooks(captions)

    timestamps = [p.get('timestamp', '') for p in posts if p.get('timestamp')]
    posting_freq = None
    if len(timestamps) >= 2:
        try:
            from datetime import datetime as _dt
            dates = sorted([_dt.fromisoformat(t.replace('Z', '+00:00')) for t in timestamps if t])
            if len(dates) >= 2:
                span_days = (dates[-1] - dates[0]).days or 1
                posting_freq = round(len(dates) / (span_days / 7), 1)
        except Exception:
            pass

    caption_lengths = [len(c) for c in captions if c]
    avg_caption_len = round(sum(caption_lengths) / max(len(caption_lengths), 1)) if caption_lengths else 0

    all_hashtags = {}
    for p in posts:
        for ht in (p.get('hashtags') or []):
            ht_lower = ht.lower().strip('#')
            all_hashtags[ht_lower] = all_hashtags.get(ht_lower, 0) + 1
    top_hashtags = sorted(all_hashtags.items(), key=lambda x: x[1], reverse=True)[:15]

    return {
        'platform': 'instagram',
        'handle': handle,
        'full_name': profile.get('fullName', ''),
        'bio': profile.get('biography', ''),
        'followers': followers,
        'following': profile.get('followsCount', 0),
        'total_posts': profile.get('postsCount', 0),
        'verified': profile.get('verified', False),
        'is_business': profile.get('isBusinessAccount', False),
        'category': profile.get('businessCategoryName', ''),
        'external_url': profile.get('externalUrl', ''),
        'highlights_count': profile.get('highlightReelCount', 0),
        'recent_posts_count': post_count,
        'avg_likes': round(total_likes / max(post_count, 1), 1),
        'avg_comments': round(total_comments / max(post_count, 1), 1),
        'avg_er_pct': round(avg_er, 4),
        'format_breakdown': format_counts,
        'hook_analysis': hook_types,
        'posting_frequency_per_week': posting_freq,
        'avg_caption_length': avg_caption_len,
        'top_hashtags': top_hashtags,
        'avg_video_views': avg_video_views,
        'total_video_views': total_video_views,
        'top_posts': sorted(posts, key=lambda p: p.get('likesCount', 0), reverse=True)[:5],
        'recent_posts': [{
            'type': p.get('_classified_format', p.get('type', '')),
            'likes': p.get('likesCount', 0),
            'comments': p.get('commentsCount', 0),
            'views': p.get('videoViewCount', 0),
            'caption': (p.get('caption', '') or '')[:300],
            'timestamp': p.get('timestamp', ''),
            'hashtags': p.get('hashtags', []),
        } for p in posts],
    }


def scrape_youtube(channel_url):
    """Scrape YouTube channel data."""
    if not channel_url or not channel_url.strip():
        return None
    channel_url = channel_url.strip()
    if not channel_url.startswith('http'):
        channel_url = f"https://www.youtube.com/@{channel_url}"
    data = apify_run_actor(APIFY_ACTORS['youtube'], {
        'channelUrls': [channel_url],
        'maxResults': 10,
        'maxResultsShorts': 5,
    }, timeout_secs=120)
    if isinstance(data, list) and len(data) > 0:
        return {
            'platform': 'youtube',
            'url': channel_url,
            'data': data[:15],
            'video_count': len(data),
        }
    return {'platform': 'youtube', 'url': channel_url, 'error': 'No data returned', 'raw': data}


def scrape_linkedin(linkedin_url):
    """Scrape LinkedIn profile/company data."""
    if not linkedin_url or not linkedin_url.strip():
        return None
    linkedin_url = linkedin_url.strip()
    if not linkedin_url.startswith('http'):
        linkedin_url = f"https://www.linkedin.com/in/{linkedin_url}"
    data = apify_run_actor(APIFY_ACTORS['linkedin'], {
        'profileUrls': [linkedin_url],
    }, timeout_secs=90)
    if isinstance(data, list) and len(data) > 0:
        return {
            'platform': 'linkedin',
            'url': linkedin_url,
            'data': data[0],
        }
    return {'platform': 'linkedin', 'url': linkedin_url, 'error': 'No data returned', 'raw': data}


def scrape_tiktok(handle):
    """Scrape TikTok profile data."""
    if not handle or not handle.strip():
        return None
    handle = handle.lstrip('@').strip()
    data = apify_run_actor(APIFY_ACTORS['tiktok'], {
        'profiles': [handle],
        'resultsPerPage': 10,
    }, timeout_secs=90)
    if isinstance(data, list) and len(data) > 0:
        return {
            'platform': 'tiktok',
            'handle': handle,
            'data': data[:15],
        }
    return {'platform': 'tiktok', 'handle': handle, 'error': 'No data returned', 'raw': data}


def scrape_website(url):
    """Crawl and audit a website."""
    if not url or not url.strip():
        return None
    url = url.strip()
    if not url.startswith('http'):
        url = f"https://{url}"
    data = apify_run_actor(APIFY_ACTORS['website'], {
        'startUrls': [{'url': url}],
        'maxCrawlPages': 5,
        'crawlerType': 'cheerio',
    }, timeout_secs=90)
    if isinstance(data, list) and len(data) > 0:
        return {
            'platform': 'website',
            'url': url,
            'pages_crawled': len(data),
            'data': [{
                'url': p.get('url', ''),
                'title': p.get('metadata', {}).get('title', '') if isinstance(p.get('metadata'), dict) else '',
                'description': p.get('metadata', {}).get('description', '') if isinstance(p.get('metadata'), dict) else '',
                'text': (p.get('text', '') or '')[:2000],
            } for p in data[:5]],
        }
    return {'platform': 'website', 'url': url, 'error': 'No data returned', 'raw': data}


def scrape_category_top_accounts(brand_category, max_accounts=25):
    """Scrape category hashtags to find top accounts in the niche."""
    from .analyst import classify_hooks

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return {'error': 'ANTHROPIC_API_KEY not set'}

    import anthropic as _anthropic
    prompt = (
        "Generate 8 Instagram hashtags for the brand category below. "
        "Mix of: 3 broad category hashtags (high volume, 100K+ posts), "
        "3 niche-specific hashtags (medium volume, used by real brands in this space), "
        "2 India-specific hashtags if the category is common in India. "
        "These should be hashtags that ACTIVE Instagram creators and brands in this niche use on their posts. "
        "Think about what hashtags a buyer or reseller would search for. "
        "Rules: lowercase, alphanumeric only, no spaces, no hyphens, no special characters, no hash symbol. "
        "Return ONLY a raw JSON array of strings. No markdown, no code fences, no explanation.\n\n"
        f"Brand category: {brand_category}\n"
        f"Example for 'Women ethnic wear': [\"ethnicwear\", \"indianfashion\", \"sareecollection\", \"kurtionline\", \"wholesalekurti\", \"designersaree\", \"suratsaree\", \"womensfashion\"]"
    )
    try:
        _client = _anthropic.Anthropic(api_key=api_key)
        _resp = _client.messages.create(
            model="claude-opus-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        text = _resp.content[0].text.strip().replace('```json', '').replace('```', '').strip()
        hashtags = json.loads(text)
        clean = [re.sub(r'[^a-z0-9]', '', h.lower()) for h in hashtags if isinstance(h, str)]
        clean = [h for h in clean if h and len(h) >= 4][:8]
    except Exception as e:
        logger.error(f"[CATEGORY] Hashtag generation failed: {e}")
        return {'error': f'Hashtag generation failed: {e}'}

    logger.info(f"[CATEGORY] Generated hashtags for '{brand_category}': {clean}")

    hashtag_data = apify_run_actor('apify/instagram-hashtag-scraper', {
        'hashtags': clean,
        'resultsLimit': 200,
        'resultsType': 'posts'
    }, timeout_secs=240)

    if not isinstance(hashtag_data, list) or len(hashtag_data) == 0:
        return {'error': 'No hashtag data returned', 'hashtags': clean}

    logger.info(f"[CATEGORY] Scraped {len(hashtag_data)} posts from hashtags")

    accounts = {}
    for post in hashtag_data:
        if not isinstance(post, dict):
            continue
        username = post.get('ownerUsername', '')
        if not username:
            continue
        if username not in accounts:
            accounts[username] = {
                'handle': username,
                'posts': [],
                'total_likes': 0,
                'total_comments': 0,
                'followers': post.get('followersCount', 0) or 0,
            }
        acc = accounts[username]
        likes = post.get('likesCount', 0) or 0
        comments = post.get('commentsCount', 0) or 0
        acc['posts'].append({
            'likes': likes,
            'comments': comments,
            'type': post.get('type', ''),
            'caption': (post.get('caption', '') or '')[:200],
            'hashtags': post.get('hashtags', []),
        })
        acc['total_likes'] += likes
        acc['total_comments'] += comments
        if (post.get('followersCount') or 0) > acc['followers']:
            acc['followers'] = post['followersCount']

    filtered = {}
    for username, acc in accounts.items():
        post_count = len(acc['posts'])
        followers = acc['followers']
        if post_count >= 2:
            avg_likes = acc['total_likes'] / max(post_count, 1)
            avg_comments = acc['total_comments'] / max(post_count, 1)
            er = ((avg_likes + avg_comments) / max(followers, 1)) * 100 if followers > 0 else 0
            if er > 25:
                continue
            format_counts = {}
            for p in acc['posts']:
                raw_type = p.get('type', 'Unknown')
                product_type = p.get('productType', '')
                has_video = bool(p.get('videoUrl'))
                if raw_type == 'Sidecar':
                    fmt = 'Carousel'
                elif product_type == 'clips' or (raw_type == 'Video' and not product_type):
                    fmt = 'Reel'
                elif has_video and raw_type == 'Image':
                    fmt = 'Reel'
                elif raw_type == 'Video' and product_type and product_type != 'clips':
                    fmt = 'Video'
                elif raw_type == 'Image':
                    fmt = 'Image'
                else:
                    fmt = raw_type
                format_counts[fmt] = format_counts.get(fmt, 0) + 1
            filtered[username] = {
                'handle': username,
                'followers': followers,
                'posts_in_data': post_count,
                'avg_likes': round(avg_likes, 1),
                'avg_comments': round(avg_comments, 1),
                'avg_er_pct': round(er, 4),
                'format_breakdown': format_counts,
                'hook_analysis': classify_hooks([p.get('caption', '') for p in acc['posts']]),
                'top_caption': max(acc['posts'], key=lambda p: p['likes']).get('caption', '') if acc['posts'] else '',
            }

    sorted_accounts = sorted(filtered.values(), key=lambda x: x['avg_er_pct'], reverse=True)[:max_accounts]

    all_ers = [a['avg_er_pct'] for a in sorted_accounts if a['avg_er_pct'] > 0]
    all_followers = [a['followers'] for a in sorted_accounts if a['followers'] > 0]
    category_avg_er = round(sum(all_ers) / max(len(all_ers), 1), 4) if all_ers else 0
    category_median_followers = sorted(all_followers)[len(all_followers) // 2] if all_followers else 0

    cat_formats = {}
    for acc in sorted_accounts:
        for fmt, cnt in acc.get('format_breakdown', {}).items():
            cat_formats[fmt] = cat_formats.get(fmt, 0) + cnt
    total_fmt = sum(cat_formats.values()) or 1
    cat_format_pct = {k: round(v / total_fmt * 100, 1) for k, v in cat_formats.items()}

    return {
        'hashtags_used': clean,
        'total_posts_scraped': len(hashtag_data),
        'total_accounts_found': len(accounts),
        'accounts_after_filter': len(filtered),
        'top_accounts': sorted_accounts,
        'category_benchmarks': {
            'avg_engagement_rate': category_avg_er,
            'median_followers': category_median_followers,
            'dominant_formats': cat_format_pct,
            'total_posts_analyzed': len(hashtag_data),
        }
    }
