import json
import re
import os
import tempfile
import base64
import threading
import logging
import traceback
import time
import uuid
import hashlib
import hmac
import requests as http_requests
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv(override=True)
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ── Pipeline imports (modular agent code) ──
from pipeline import (
    scrape_instagram, scrape_youtube, scrape_linkedin, scrape_tiktok,
    scrape_website, scrape_category_top_accounts,
    classify_hooks,
    run_claude_analysis,
    build_agent_pdf,
    run_agent_pipeline, agent_jobs, emit_progress,
)

# ── Legacy endpoints (Make.com-compatible Report 1 & 2) ──
from legacy import register_legacy_routes
register_legacy_routes(app)


# ════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ════════════════════════════════════════════════════════════════════

@app.route('/health', methods=['GET'])
def health():
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    env_names = [k for k in os.environ if 'ANTH' in k.upper() or 'API' in k.upper() or 'KEY' in k.upper()]
    return jsonify({"status": "ok", "api_key_set": bool(key), "api_key_length": len(key), "related_env_vars": env_names}), 200


# ════════════════════════════════════════════════════════════════════
# SYNC AGENT SCRAPER (used by /agent-report and /agent-scrape-only)
# ════════════════════════════════════════════════════════════════════

def scrape_all_platforms(form_data):
    """Scrape all platforms in parallel based on provided handles, plus category top accounts."""
    results = {}
    tasks = {}

    with ThreadPoolExecutor(max_workers=7) as executor:
        if form_data.get('instagram_handle'):
            tasks['brand_instagram'] = executor.submit(scrape_instagram, form_data['instagram_handle'], 200)
        if form_data.get('youtube_channel'):
            tasks['brand_youtube'] = executor.submit(scrape_youtube, form_data['youtube_channel'])
        if form_data.get('linkedin_url'):
            tasks['brand_linkedin'] = executor.submit(scrape_linkedin, form_data['linkedin_url'])
        if form_data.get('tiktok_handle'):
            market = (form_data.get('target_market') or '').lower()
            if market not in ('india',):
                tasks['brand_tiktok'] = executor.submit(scrape_tiktok, form_data['tiktok_handle'])
        if form_data.get('website_url'):
            tasks['brand_website'] = executor.submit(scrape_website, form_data['website_url'])

        for i, comp_handle in enumerate(form_data.get('competitor_handles', []), 1):
            if comp_handle and comp_handle.strip():
                tasks[f'competitor_{i}_instagram'] = executor.submit(scrape_instagram, comp_handle, 20)

        if form_data.get('brand_category'):
            tasks['category_data'] = executor.submit(
                scrape_category_top_accounts, form_data['brand_category'], 25
            )

        for key, future in tasks.items():
            try:
                result = future.result(timeout=240)
                if result is not None:
                    results[key] = result
            except Exception as e:
                results[key] = {'error': str(e)}
                logger.error(f"[SCRAPE] {key} failed: {e}")

    # Phase 2: Auto-scrape top 3 category leaders
    cat_data = results.get('category_data')
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
            logger.info(f"[SCRAPE] Auto-scraping top {len(leaders_to_scrape)} category leaders: {leaders_to_scrape}")
            with ThreadPoolExecutor(max_workers=3) as executor2:
                leader_tasks = {}
                for i, lh in enumerate(leaders_to_scrape, 1):
                    leader_tasks[f'category_leader_{i}_instagram'] = executor2.submit(scrape_instagram, lh, 20)
                for key, future in leader_tasks.items():
                    try:
                        result = future.result(timeout=120)
                        if result is not None and not result.get('error'):
                            results[key] = result
                            logger.info(f"[SCRAPE] Category leader scraped: @{result.get('handle')} — {result.get('followers',0):,} followers, {result.get('avg_er_pct',0)}% ER")
                    except Exception as e:
                        logger.warning(f"[SCRAPE] Category leader {key} failed: {e}")

    return results


# ════════════════════════════════════════════════════════════════════
# SYNC AGENT ENDPOINT (legacy — prefer /agent-report-async)
# ════════════════════════════════════════════════════════════════════

@app.route('/agent-report', methods=['POST'])
def agent_report():
    """Full agent pipeline (sync): scrape → analyze → PDF → return base64."""
    try:
        body = request.get_json(force=True)
        logger.info(f"[AGENT] Request for brand: {body.get('brand_name', 'unknown')}")

        form_data = {
            'brand_name': body.get('brand_name', ''),
            'brand_category': body.get('brand_category', ''),
            'brand_description': body.get('brand_description', ''),
            'target_market': body.get('target_market', ''),
            'report_type': body.get('report_type', 'Brand Audit + Competitor Research'),
            'instagram_handle': body.get('instagram_handle', ''),
            'youtube_channel': body.get('youtube_channel', ''),
            'linkedin_url': body.get('linkedin_url', ''),
            'tiktok_handle': body.get('tiktok_handle', ''),
            'website_url': body.get('website_url', ''),
            'competitor_handles': [
                body.get('competitor_1', ''),
                body.get('competitor_2', ''),
                body.get('competitor_3', ''),
            ],
            'full_name': body.get('full_name', ''),
            'email': body.get('email', ''),
            'whatsapp': body.get('whatsapp', ''),
        }

        scraped_data = scrape_all_platforms(form_data)
        report_data = run_claude_analysis(form_data, scraped_data)
        pdf_base64 = build_agent_pdf(report_data, form_data, scraped_data)

        return jsonify({
            'status': 'success',
            'pdf_base64': pdf_base64,
            'sections': len(report_data),
            'platforms_scraped': list(scraped_data.keys()),
        }), 200

    except Exception as e:
        logger.error(f"[AGENT] Error: {traceback.format_exc()}")
        return jsonify({'status': 'error', 'message': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/agent-scrape-only', methods=['POST'])
def agent_scrape_only():
    """Scrape all platforms and return raw data — for frontend live preview."""
    try:
        body = request.get_json(force=True)
        form_data = {
            'brand_name': body.get('brand_name', ''),
            'instagram_handle': body.get('instagram_handle', ''),
            'youtube_channel': body.get('youtube_channel', ''),
            'linkedin_url': body.get('linkedin_url', ''),
            'tiktok_handle': body.get('tiktok_handle', ''),
            'website_url': body.get('website_url', ''),
            'competitor_handles': [
                body.get('competitor_1', ''),
                body.get('competitor_2', ''),
                body.get('competitor_3', ''),
            ],
        }
        scraped_data = scrape_all_platforms(form_data)
        return jsonify({'status': 'success', 'data': scraped_data}), 200
    except Exception as e:
        logger.error(f"[AGENT-SCRAPE] Error: {traceback.format_exc()}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ════════════════════════════════════════════════════════════════════
# RAZORPAY PAYMENT INTEGRATION
# ════════════════════════════════════════════════════════════════════

RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_placeholder')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')

PRICING = {
    'early_access': 250000,   # Rs. 2,500
    'standard': 699900,       # Rs. 6,999
    'agency': 2400000,        # Rs. 24,000
}


@app.route('/create-order', methods=['POST'])
def create_order():
    """Create a Razorpay order for payment."""
    try:
        body = request.get_json(force=True)
        plan = body.get('plan', 'standard')
        amount = PRICING.get(plan, PRICING['standard'])

        if not RAZORPAY_KEY_SECRET:
            return jsonify({'status': 'error', 'message': 'Razorpay not configured'}), 500

        import razorpay
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        order = client.order.create({
            'amount': amount,
            'currency': 'INR',
            'receipt': f'offgrid_{uuid.uuid4().hex[:12]}',
            'notes': {
                'brand_name': body.get('brand_name', ''),
                'email': body.get('email', ''),
                'plan': plan,
            }
        })

        return jsonify({
            'status': 'success',
            'order_id': order['id'],
            'amount': amount,
            'currency': 'INR',
            'key_id': RAZORPAY_KEY_ID,
        }), 200

    except Exception as e:
        logger.error(f"[RAZORPAY] Create order error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    """Verify Razorpay payment signature."""
    try:
        body = request.get_json(force=True)
        razorpay_order_id = body.get('razorpay_order_id', '')
        razorpay_payment_id = body.get('razorpay_payment_id', '')
        razorpay_signature = body.get('razorpay_signature', '')

        if not RAZORPAY_KEY_SECRET:
            return jsonify({'status': 'error', 'message': 'Razorpay not configured'}), 500

        message = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected_signature = hmac.new(
            RAZORPAY_KEY_SECRET.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if expected_signature == razorpay_signature:
            return jsonify({'status': 'success', 'message': 'Payment verified'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Invalid signature'}), 400

    except Exception as e:
        logger.error(f"[RAZORPAY] Verify error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ════════════════════════════════════════════════════════════════════
# ASYNC AGENT PIPELINE + SSE
# ════════════════════════════════════════════════════════════════════

@app.route('/agent-report-async', methods=['POST'])
def agent_report_async():
    """Start the agent pipeline asynchronously. Returns a job_id for SSE tracking."""
    try:
        body = request.get_json(force=True)
        job_id = uuid.uuid4().hex[:16]

        form_data = {
            'brand_name': body.get('brandName', body.get('brand_name', '')),
            'brand_category': body.get('category', body.get('brand_category', '')),
            'brand_description': body.get('brandDescription', body.get('brand_description', '')),
            'target_market': body.get('targetMarket', body.get('target_market', '')),
            'report_type': body.get('reportType', body.get('report_type', 'Brand Audit + Competitor Research')),
            'instagram_handle': body.get('instagramHandle', body.get('instagram_handle', '')),
            'youtube_channel': body.get('youtubeChannel', body.get('youtube_channel', '')),
            'linkedin_url': body.get('linkedinUrl', body.get('linkedin_url', '')),
            'tiktok_handle': body.get('tiktokHandle', body.get('tiktok_handle', '')),
            'website_url': body.get('websiteUrl', body.get('website_url', '')),
            'competitor_handles': [
                body.get('competitor1', body.get('competitor_1', '')),
                body.get('competitor2', body.get('competitor_2', '')),
                body.get('competitor3', body.get('competitor_3', '')),
            ],
            'full_name': body.get('fullName', body.get('full_name', '')),
            'email': body.get('email', ''),
            'whatsapp': body.get('whatsapp', ''),
            'payment_id': body.get('payment_id', ''),
        }

        form_data['competitor_handles'] = [h for h in form_data['competitor_handles'] if h and h.strip()]

        logger.info(f"[AGENT-ASYNC] Starting job {job_id} for brand: {form_data['brand_name']}")
        agent_jobs[job_id] = {'steps': [], 'status': 'starting', 'result': None}

        thread = threading.Thread(target=run_agent_pipeline, args=(job_id, form_data), daemon=True)
        thread.start()

        return jsonify({
            'status': 'success',
            'job_id': job_id,
            'message': f'Agent pipeline started for {form_data["brand_name"]}',
        }), 200

    except Exception as e:
        logger.error(f"[AGENT-ASYNC] Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/agent-status/<job_id>', methods=['GET'])
def agent_status_sse(job_id):
    """SSE endpoint to stream real-time agent progress."""
    def generate():
        last_index = 0
        while True:
            job = agent_jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break

            steps = job.get('steps', [])
            while last_index < len(steps):
                step = steps[last_index]
                yield f"data: {json.dumps(step)}\n\n"
                last_index += 1

            if job['status'] in ('completed', 'failed'):
                yield f"data: {json.dumps({'type': 'complete', 'status': job['status'], 'result': job.get('result', {})})}\n\n"
                break

            time.sleep(1)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
            'Access-Control-Allow-Origin': '*',
        }
    )


@app.route('/agent-result/<job_id>', methods=['GET'])
def agent_result(job_id):
    """Get the final result of a completed agent job (including PDF)."""
    job = agent_jobs.get(job_id)
    if not job:
        return jsonify({'status': 'error', 'message': 'Job not found'}), 404
    if job['status'] == 'running':
        return jsonify({'status': 'running', 'steps_completed': len(job.get('steps', []))}), 202
    if job['status'] == 'failed':
        return jsonify({'status': 'failed', 'error': job.get('result', {}).get('error', 'Unknown error')}), 500

    return jsonify({
        'status': 'completed',
        'result': job.get('result', {}),
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
