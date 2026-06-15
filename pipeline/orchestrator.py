"""
Async pipeline orchestrator.
Runs scraping → analysis → PDF generation in a background thread with SSE progress updates.
"""

import json
import logging
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from .scraper import scrape_instagram, scrape_youtube, scrape_linkedin, scrape_website, scrape_category_top_accounts
from .strategist import run_claude_analysis
from .designer import build_agent_pdf

logger = logging.getLogger(__name__)

agent_jobs = {}


def emit_progress(job_id, step, message, status='active', data=None):
    """Update job progress store."""
    if job_id not in agent_jobs:
        agent_jobs[job_id] = {'steps': [], 'status': 'running', 'result': None}
    agent_jobs[job_id]['steps'].append({
        'step': step,
        'message': message,
        'status': status,
        'data': data,
        'timestamp': datetime.now().isoformat(),
    })
    logger.info(f"[JOB {job_id}] Step {step}: {message}")


def run_agent_pipeline(job_id, form_data):
    """Run the full agent pipeline in a background thread with progress updates."""
    try:
        agent_jobs[job_id] = {'steps': [], 'status': 'running', 'result': None}

        emit_progress(job_id, 1, f"Receiving form data: {form_data['brand_name']} — {form_data['brand_category']}, {form_data['target_market']}", 'done')

        # Step 2: Scrape all platforms
        emit_progress(job_id, 2, f"Starting multi-platform scrape for @{form_data.get('instagram_handle', '').lstrip('@')}", 'active')

        scraped_data = {}
        tasks = {}

        with ThreadPoolExecutor(max_workers=7) as executor:
            if form_data.get('instagram_handle'):
                tasks['brand_instagram'] = executor.submit(scrape_instagram, form_data['instagram_handle'], 200)
                emit_progress(job_id, 3, f"Deep-scraping full brand profile: @{form_data['instagram_handle'].lstrip('@')} (up to 200 posts)", 'active')

            if form_data.get('website_url'):
                tasks['brand_website'] = executor.submit(scrape_website, form_data['website_url'])

            for i, comp_handle in enumerate(form_data.get('competitor_handles', []), 1):
                if comp_handle and comp_handle.strip():
                    tasks[f'competitor_{i}_instagram'] = executor.submit(scrape_instagram, comp_handle, 20)
                    emit_progress(job_id, 3 + i, f"Scraping competitor: @{comp_handle.strip().lstrip('@')}", 'active')

            if form_data.get('brand_category'):
                tasks['category_data'] = executor.submit(
                    scrape_category_top_accounts, form_data['brand_category'], 25
                )
                emit_progress(job_id, 7, f"Scraping category hashtags for {form_data['brand_category']}", 'active')

            if form_data.get('youtube_channel'):
                tasks['brand_youtube'] = executor.submit(scrape_youtube, form_data['youtube_channel'])
            if form_data.get('linkedin_url'):
                tasks['brand_linkedin'] = executor.submit(scrape_linkedin, form_data['linkedin_url'])

            for key, future in tasks.items():
                try:
                    result = future.result(timeout=240)
                    if result is not None:
                        scraped_data[key] = result
                        if key == 'brand_instagram' and isinstance(result, dict) and not result.get('error'):
                            emit_progress(job_id, 8, f"Brand profile scraped: {result.get('followers', 0):,} followers, {result.get('post_count', 0)} posts, {result.get('avg_er_pct', 0)}% ER", 'done',
                                          {'type': 'brand_data', 'followers': result.get('followers', 0), 'posts': result.get('post_count', 0), 'er': result.get('avg_er_pct', 0), 'handle': result.get('handle', '')})
                        elif key.startswith('competitor_') and isinstance(result, dict) and not result.get('error'):
                            emit_progress(job_id, 9, f"Competitor scraped: @{result.get('handle', '')} — {result.get('followers', 0):,} followers, {result.get('avg_er_pct', 0)}% ER", 'done',
                                          {'type': 'competitor_data', 'handle': result.get('handle', ''), 'followers': result.get('followers', 0), 'er': result.get('avg_er_pct', 0)})
                        elif key == 'category_data' and isinstance(result, dict) and not result.get('error'):
                            n_accounts = len(result.get('top_accounts', []))
                            emit_progress(job_id, 10, f"Category scraped: {n_accounts} accounts found from hashtag data", 'done',
                                          {'type': 'category_data', 'accounts_found': n_accounts, 'benchmarks': result.get('category_benchmarks', {})})
                        elif key == 'brand_website' and isinstance(result, dict) and not result.get('error'):
                            emit_progress(job_id, 11, f"Website audited: {form_data.get('website_url', '')}", 'done')
                        else:
                            emit_progress(job_id, 11, f"Scraped: {key}", 'done')
                except Exception as e:
                    scraped_data[key] = {'error': str(e)}
                    emit_progress(job_id, 11, f"Failed: {key} — {str(e)}", 'done')

        # Phase 2: Auto-scrape category leaders
        cat_data = scraped_data.get('category_data')
        if isinstance(cat_data, dict) and not cat_data.get('error'):
            top_accounts = cat_data.get('top_accounts', [])
            already_scraped = set()
            brand_handle = (form_data.get('instagram_handle') or '').lstrip('@').strip().lower()
            if brand_handle:
                already_scraped.add(brand_handle)
            for ch in form_data.get('competitor_handles', []):
                if ch and ch.strip():
                    already_scraped.add(ch.strip().lstrip('@').lower())

            leaders_to_scrape = []
            for acc in top_accounts:
                handle = (acc.get('handle') or '').lower()
                if handle and handle not in already_scraped and acc.get('followers', 0) >= 1000:
                    leaders_to_scrape.append(handle)
                if len(leaders_to_scrape) >= 3:
                    break

            if leaders_to_scrape:
                emit_progress(job_id, 12, f"Auto-scraping top {len(leaders_to_scrape)} category leaders: {', '.join(['@' + h for h in leaders_to_scrape])}", 'active')
                with ThreadPoolExecutor(max_workers=3) as executor2:
                    leader_tasks = {}
                    for i, lh in enumerate(leaders_to_scrape, 1):
                        leader_tasks[f'category_leader_{i}_instagram'] = executor2.submit(scrape_instagram, lh, 20)
                    for key, future in leader_tasks.items():
                        try:
                            result = future.result(timeout=120)
                            if result is not None and not result.get('error'):
                                scraped_data[key] = result
                                emit_progress(job_id, 13, f"Category leader scraped: @{result.get('handle', '')} — {result.get('followers', 0):,} followers", 'done')
                        except Exception as e:
                            logger.warning(f"[SCRAPE] Category leader {key} failed: {e}")

        emit_progress(job_id, 14, "All scraping complete. Starting AI analysis...", 'done')

        # Step 3: Claude analysis
        emit_progress(job_id, 15, "Sending scraped data to Claude Opus for 11-section deep analysis...", 'active')

        report_data = run_claude_analysis(form_data, scraped_data)

        emit_progress(job_id, 16, f"Claude analysis complete: {len(report_data)} sections parsed", 'done')
        emit_progress(job_id, 17, "Generating branded PDF...", 'active')

        # Step 4: Generate PDF
        pdf_base64 = build_agent_pdf(report_data, form_data, scraped_data)
        emit_progress(job_id, 18, "Branded PDF generated successfully!", 'done')

        # Step 5: Done
        emit_progress(job_id, 19, f"Report ready! Delivering to {form_data.get('email', 'client')}", 'done')

        agent_jobs[job_id]['status'] = 'completed'
        agent_jobs[job_id]['result'] = {
            'pdf_base64': pdf_base64,
            'brand': form_data['brand_name'],
            'sections': len(report_data),
            'platforms_scraped': list(scraped_data.keys()),
        }

    except Exception as e:
        logger.error(f"[JOB {job_id}] Pipeline error: {traceback.format_exc()}")
        emit_progress(job_id, 99, f"Error: {str(e)}", 'error')
        agent_jobs[job_id]['status'] = 'failed'
        agent_jobs[job_id]['result'] = {'error': str(e)}
