"""Local test for /generate-pdf with a realistic large 18-section payload."""
import json
import requests
import sys

BASE_URL = "http://127.0.0.1:5000"

# Realistic large Claude API response matching the 18-section schema
TEST_PAYLOAD = {
    "brand_name": "TestBrand India",
    "brand_category": "Premium Skincare",
    "brand_market": "India",
    "claude_response": json.dumps({
        "keyword_universe": {
            "search_intent_keywords": ["best face serum india", "vitamin c serum for oily skin", "anti-aging skincare routine", "korean skincare india", "niacinamide serum benefits"],
            "emotional_trigger_keywords": ["glow up transformation", "confidence boost", "self-care ritual", "wedding ready skin", "glass skin goals"],
            "culture_keywords": ["ayurvedic beauty", "desi skincare", "monsoon skincare", "pollution protection", "turmeric alternatives"],
            "style_keywords": ["minimalist routine", "clean beauty", "luxury affordable", "dermat recommended", "clinic-grade at home"],
            "seasonal_keywords": ["summer skincare essentials", "monsoon face wash", "winter hydration", "festive glow kit", "holi skin protection"]
        },
        "market_saturation": {
            "category_maturity": "The Indian premium skincare market is in a rapid growth phase with 23% YoY growth. International brands like The Ordinary and domestic players like Minimalist have established strong footholds, but significant whitespace remains in the Rs. 800-1500 segment for clinically-backed formulations.",
            "content_fatigue": "UGC-style before/after content is approaching saturation. Dermatologist endorsement videos still perform well but are becoming commoditized. Ingredient education content (like explaining niacinamide percentages) is oversaturated.",
            "pricing_pressure": "Minimalist has anchored the category at Rs. 349-599. Brands pricing above Rs. 999 must justify with clear clinical evidence, premium packaging, or unique ingredient stories. The market tolerates premium pricing only with strong trust signals.",
            "differentiation_gaps": "Few brands effectively communicate formulation philosophy beyond ingredient lists. No major player owns the 'Indian skin science' positioning. Sustainability claims remain underexplored in the premium segment.",
            "audience_fragmentation": "The audience is split between ingredient-aware millennials (25-35) who research extensively and Gen Z (18-24) who discover through reels and influencer content. Male skincare is growing 40% YoY but underserved by premium brands."
        },
        "market_benchmarks": {
            "typical_cpm_range": "Rs. 80-250 (Meta), Rs. 40-120 (YouTube)",
            "typical_ctr_range": "1.2%-3.5% (varies by format)",
            "typical_cvr_range": "1.8%-4.2% (landing page dependent)",
            "typical_cac_range": "Rs. 350-800 (first purchase)",
            "typical_aov_range": "Rs. 899-1499",
            "average_roas_month1_2": "0.8x-1.2x (investment phase)",
            "average_roas_month3_4": "1.5x-2.5x (optimization phase)",
            "average_roas_month5_6": "2.5x-4.0x (scaling phase)"
        },
        "competitive_ad_intelligence": {
            "minimalist": {
                "ad_formats_running": "Static carousels, UGC testimonials, ingredient explainer reels",
                "primary_hook_style": "Problem-solution with clinical data points",
                "offer_strategy": "Combo discounts + free shipping above Rs. 499",
                "audience_targeting_style": "Interest-based (skincare enthusiasts, beauty buyers)",
                "creative_fatigue_score": 7,
                "scaling_signals": "High volume testing, 15-20 new creatives per week, heavy retargeting",
                "strategic_gap": "Weak emotional storytelling, over-reliance on ingredient education"
            },
            "dot_and_key": {
                "ad_formats_running": "Vibrant static, influencer UGC, product demo reels",
                "primary_hook_style": "Aesthetic-first with lifestyle aspirational hooks",
                "offer_strategy": "Bundle deals, seasonal limited editions",
                "audience_targeting_style": "Lookalike audiences from website purchasers",
                "creative_fatigue_score": 5,
                "scaling_signals": "Moderate spend, consistent but not aggressive scaling",
                "strategic_gap": "Low credibility signals, no clinical backing in ads"
            },
            "the_ordinary_india": {
                "ad_formats_running": "Minimal static, educational carousels, dermatologist collab reels",
                "primary_hook_style": "Authority/clinical with minimalist design",
                "offer_strategy": "Rarely discounts, relies on brand equity",
                "audience_targeting_style": "Broad awareness with retargeting funnel",
                "creative_fatigue_score": 3,
                "scaling_signals": "Low creative volume but high brand recall, organic-heavy strategy",
                "strategic_gap": "Pricing perception issues for India, limited localization"
            }
        },
        "hook_intelligence": {
            "scarcity_hooks": [
                "Only 200 units left of our bestselling Vitamin C — and we won't restock for 6 weeks",
                "This limited formulation uses high-altitude rosehip oil available only 3 months per year",
                "Our dermatologist slots for free skin consultations fill up in 4 hours. Book now."
            ],
            "social_proof_hooks": [
                "47,000 women switched to this serum this month. Here's what happened to their skin.",
                "Rated 4.8/5 by 12,000 verified buyers who tried everything else first",
                "Every 8 seconds, someone in India adds this to their cart"
            ],
            "problem_agitation_hooks": [
                "Your Rs. 2000 moisturizer is actually making your acne worse. Here's the science.",
                "Why Indian dermatologists are warning against the skincare routine you saw on Instagram",
                "That 'glow' from your current products? It's actually inflammation. Let us explain."
            ],
            "curiosity_gap_hooks": [
                "The one ingredient Korean skincare brands don't want Indian women to know about",
                "We tested 47 serums in our lab. Only 3 actually penetrated the skin barrier.",
                "A Mumbai dermatologist's 3-step routine that replaced 8 products"
            ],
            "direct_response_hooks": [
                "Get clinical-grade results at home for Rs. 599. 30-day money-back guarantee.",
                "Free skin analysis + personalized routine. Takes 2 minutes. No purchase required.",
                "Your first order ships free today. Use code GLOWUP for 20% off."
            ],
            "platform_native_variants": {
                "rank_1": {
                    "predicted_ctr_rank": 1,
                    "hook": "Your Rs. 2000 moisturizer is making your acne worse",
                    "reason": "Combines price anchoring with fear of wrong choice — high emotional trigger for Indian skincare buyers who've tried expensive products",
                    "reels_overlay": "POV: Your expensive moisturizer is actually breaking you out",
                    "feed_static": "YOUR MOISTURIZER IS LYING TO YOU [before/after visual]",
                    "caption_opening": "I spent Rs. 43,000 on skincare last year. My skin got worse. Then a dermatologist told me something that changed everything..."
                },
                "rank_2": {
                    "predicted_ctr_rank": 2,
                    "hook": "47,000 women switched this month",
                    "reason": "Massive social proof number creates bandwagon effect and FOMO — especially powerful in Indian collectivist culture",
                    "reels_overlay": "47,000 women can't be wrong",
                    "feed_static": "47,000 WOMEN SWITCHED THIS MONTH [product grid visual]",
                    "caption_opening": "When we launched 6 months ago, we expected maybe 500 orders. We got 12,000 in week one. Here's why..."
                },
                "rank_3": {
                    "predicted_ctr_rank": 3,
                    "hook": "Mumbai dermatologist's 3-step routine replacing 8 products",
                    "reason": "Authority + simplification promise — appeals to skincare overwhelm that most Indian women feel",
                    "reels_overlay": "A top dermatologist just simplified your entire routine",
                    "feed_static": "3 STEPS. 8 PRODUCTS REPLACED. [minimal product layout]",
                    "caption_opening": "Dr. Rashmi Shetty sees 40 patients a day. She told us that 90% of them are using too many products. Here's what she actually recommends..."
                }
            }
        },
        "narrative_landscape": {
            "competitor_narratives": {
                "minimalist": "We give you clinical ingredients at honest prices — transparency is our brand",
                "dot_and_key": "Skincare should be fun, colorful, and part of your self-expression",
                "the_ordinary": "Science-first, no-nonsense formulations that respect your intelligence",
                "mamaearth": "Natural, toxin-free products that are safe for you and the planet"
            },
            "market_whitespace": "No premium brand owns the 'made for Indian skin science' narrative — combining Ayurvedic wisdom with modern dermatology. This is the highest-impact positioning gap in the market.",
            "brand_positioning_opportunity": "Position as the bridge between ancient Indian skin wisdom and modern clinical dermatology. Own 'Indian Skin Science' as a category. This narrative is uncontested and deeply resonant with the target audience.",
            "storytelling_angles": [
                "The ingredient your grandmother used that modern science finally validated — and how we perfected the formulation",
                "We sent our team to 12 Indian cities to study how pollution, water quality, and climate affect skin differently — here's what we found",
                "Why Korean skincare doesn't work for Indian skin (and what does) — backed by 3 years of research",
                "The diary of a formulator: 847 failed batches before we got the texture right for Indian humidity",
                "From a cramped Mumbai lab to 47,000 happy customers — the real story behind our bestseller"
            ]
        },
        "creative_format": {
            "top_performing_formats": [
                "15-30 second UGC-style reels showing real before/after transformations",
                "Dermatologist talking head with on-screen text overlays",
                "Product texture ASMR close-ups (high save rate)",
                "Split-screen comparison: this product vs. competitor",
                "Carousel: ingredient education with swipe-worthy design"
            ],
            "emerging_opportunities": [
                "AI skin analysis filter → product recommendation funnel",
                "Day-in-my-life integration (morning routine focus)",
                "Micro-documentary: behind the lab / formulation process",
                "Interactive polls and quizzes in Stories for engagement"
            ],
            "format_recommendations": "Lead with 15-second reels for top-of-funnel reach. Use carousels for mid-funnel education. Deploy UGC testimonials for bottom-funnel conversion. Test ASMR texture videos as they show 3x save rates vs. standard product shots."
        },
        "creative_volume_requirements": {
            "creatives_per_month": "40-60 unique creatives",
            "weekly_creative_volume": {
                "static_images": "8-10",
                "video_concepts": "5-7"
            },
            "format_mix": {
                "reels_percentage": 50,
                "carousel_percentage": 25,
                "static_percentage": 25
            },
            "refresh_frequency": "Replace bottom 30% performers every 2 weeks. Full creative refresh every 6 weeks.",
            "minimum_viable_creative_set": "15 creatives minimum for ASC campaigns (5 video, 5 carousel, 5 static)",
            "creative_production_budget_estimate": "Rs. 80,000-1,50,000/month for in-house + UGC creator network"
        },
        "platform_intelligence": {
            "facebook_strategy": "Use Facebook primarily for retargeting and lookalike audiences of website visitors and purchasers. Focus on carousel and collection ads. Lower CPMs but higher intent when combined with Instagram prospecting.",
            "instagram_strategy": "Primary prospecting channel. Lead with Reels for reach, Stories for engagement, Feed for brand building. Instagram drives 70% of skincare discovery in India.",
            "reels_strategy": "Post 4-5 reels per week minimum. First 3 seconds determine 80% of performance. Use trending audio with original visuals. Optimal length: 15-22 seconds for ads, 30-60 seconds for organic.",
            "asc_campaign_structure": "Advantage+ Shopping Campaign with minimum 15 creatives. Set daily budget at Rs. 3,000-5,000 initially. Let the algorithm optimize for 7 days before making changes. Use cost cap bidding after initial learning phase.",
            "budget_allocation": "70% Meta (Instagram + Facebook), 20% YouTube Shorts, 10% experimentation (Pinterest, Google Discovery). Shift 5% to YouTube if CPMs exceed Rs. 200 on Meta.",
            "content_calendar": "Monday: Educational reel, Tuesday: UGC testimonial, Wednesday: Product feature static, Thursday: Behind-the-scenes, Friday: Dermatologist tip, Saturday: Community repost, Sunday: Self-care narrative"
        },
        "audience_intelligence": {
            "primary_segment": {
                "age_range": "25-34",
                "gender": "Female (85%)",
                "location": ["Mumbai", "Delhi NCR", "Bangalore", "Pune", "Hyderabad"],
                "income_level": "Rs. 5-15 LPA household income",
                "psychographics": "Ingredient-aware, research-driven, willing to invest in quality but needs justification",
                "buying_behavior": "Compares 3-4 brands before purchasing, reads reviews extensively, influenced by dermatologist recommendations",
                "content_preferences": "Educational reels, before/after transformations, ingredient breakdowns"
            },
            "secondary_segment": {
                "age_range": "18-24",
                "gender": "Female (75%), Male (25%)",
                "location": ["Tier 1 and Tier 2 cities"],
                "income_level": "Rs. 3-8 LPA or college students with parental support",
                "psychographics": "Trend-driven, influenced by Instagram aesthetics, price-sensitive but aspirational",
                "buying_behavior": "Impulse buyers when triggered by social proof, high cart abandonment, responds to limited offers",
                "content_preferences": "Aesthetic reels, influencer recommendations, GRWM content"
            },
            "geographic_nuance": {
                "metro_strategy": "Premium positioning, clinical credibility focus, same-day delivery USP",
                "tier_2_strategy": "Value packs, vernacular content, COD availability emphasis",
                "south_india": "Higher skincare awareness, receptive to clinical data, price-conscious comparison shoppers",
                "north_india": "Wedding/festive-driven purchasing spikes, stronger influencer impact, preference for visible results"
            }
        },
        "offer_architecture": {
            "recommended_price_point": "Rs. 799-1299 for hero SKU. This sits in the 'affordable premium' sweet spot — above Minimalist (Rs. 349-599) but below international brands (Rs. 1500+).",
            "first_order_hook": "Get your personalized skin analysis + 20% off your first order. Free shipping. 30-day money-back guarantee.",
            "bundle_strategy": {
                "starter_kit": "3-product routine at 25% off (Rs. 1499 → Rs. 1124) — lowest barrier to entry",
                "bestseller_duo": "Hero serum + moisturizer at 15% off — highest conversion rate bundle",
                "complete_routine": "5-product set at 35% off (Rs. 3999 → Rs. 2599) — highest AOV driver",
                "gift_set": "Premium packaging + mini sizes at Rs. 999 — festive/gifting occasions"
            },
            "price_justification": "Each product undergoes 847 formulation iterations, is tested on Indian skin types in Indian climate conditions, and uses ingredients sourced at pharmaceutical grade. Show the lab, show the process, show the results.",
            "discount_guardrails": "Never exceed 30% off on hero SKUs. Limit sitewide sales to 4x per year (Republic Day, Summer Sale, Festive Season, Year End). Use bundle savings instead of flat discounts to protect perceived value."
        },
        "unit_economics": {
            "target_cac": "Rs. 450-650 (blended across channels)",
            "break_even_roas": "1.8x (assuming 55% gross margin)",
            "recommended_aov": "Rs. 1,199 (push bundles to achieve this)",
            "realistic_roas_timeline": {
                "month_1_2_expectation": "0.8x-1.2x — This is the learning investment phase. You are buying data, not profits. Do not panic.",
                "month_3_4_expectation": "1.5x-2.5x — Algorithm optimization kicks in, winning creatives identified, retargeting pools built.",
                "month_5_6_expectation": "2.5x-4.0x — Scaling proven winners, LTV from repeat purchases starts compounding, organic amplifies paid."
            },
            "india_specific_factors": {
                "cod_impact": "30-40% of orders will be COD. Budget for 15-20% RTO (return to origin) rate. Prepaid incentives (extra 5% off) can shift ratio.",
                "payment_gateway_fees": "2-3% on prepaid orders. Factor into margin calculations.",
                "gst_considerations": "18% GST on cosmetics. Price your MRP to absorb GST without shocking the customer at checkout.",
                "seasonal_spikes": "Budget 2x during Oct-Nov (festive) and Mar-Apr (wedding season). These months drive 35% of annual revenue."
            }
        },
        "creative_test_matrix": {
            "testing_budget_percentage": "20-30% of total ad spend dedicated to testing",
            "validation_timeline": "7-10 days per test with minimum Rs. 5,000 spend per creative",
            "weekly_creative_volume_during_test": "10-12 new creatives per week during testing phase",
            "test_hypothesis_1": {
                "hook_angle": "Problem Agitation — Your moisturizer is making acne worse",
                "ad_format": "15-second UGC reel with dermatologist voiceover",
                "target_audience": "Women 25-34, skincare interest, competitor brand followers",
                "budget_allocation_percentage": "40% of test budget",
                "success_metric": "CTR > 2.5%, CPC < Rs. 15, 3-second video view rate > 45%",
                "kill_criteria": "If CTR < 1.5% after Rs. 5,000 spend or CPC > Rs. 25"
            },
            "test_hypothesis_2": {
                "hook_angle": "Social Proof — 47,000 women switched this month",
                "ad_format": "Static carousel with customer testimonials + product shots",
                "target_audience": "Women 18-34, online shopping behavior, beauty and wellness interest",
                "budget_allocation_percentage": "35% of test budget",
                "success_metric": "CTR > 2.0%, Add to Cart rate > 4%, ROAS > 1.0x",
                "kill_criteria": "If CTR < 1.2% after Rs. 5,000 spend or zero conversions after Rs. 8,000"
            },
            "test_hypothesis_3": {
                "hook_angle": "Authority — Mumbai dermatologist's 3-step routine",
                "ad_format": "30-second talking head reel with before/after overlay",
                "target_audience": "Women 28-40, health-conscious, follow dermatologist accounts",
                "budget_allocation_percentage": "25% of test budget",
                "success_metric": "CTR > 1.8%, Save rate > 3%, Comment rate > 0.5%",
                "kill_criteria": "If engagement rate < 1% after Rs. 4,000 spend"
            }
        },
        "creative_execution_briefs": {
            "brief_1": {
                "brief_number": 1,
                "brief_name": "The Moisturizer Exposé",
                "objective": "Drive awareness and clicks through problem agitation — challenge the viewer's current skincare routine",
                "format": "15-second vertical reel (9:16) for Instagram Reels and Stories",
                "audio_direction": "Trending audio bed (lo-fi or ambient) with voiceover overlay. VO tone: concerned friend, not preachy dermatologist.",
                "thumbnail_description": "Close-up of a woman touching her face with concerned expression. Bold white text overlay: 'YOUR MOISTURIZER IS LYING' on dark background.",
                "cta_and_offer": "Swipe up for free skin analysis → 20% off first order → Free shipping",
                "production_requirements": "1 female model (25-30, relatable Indian skin), ring light setup, clean bathroom/vanity background, 2 skincare products for comparison shot",
                "production_cost_estimate": "Rs. 8,000-12,000 (UGC creator) or Rs. 3,000-5,000 (in-house with team member)",
                "scene_breakdown": "Scene 1 (0-3s): Close-up of woman applying moisturizer, text overlay 'POV: Your expensive moisturizer is breaking you out'. Scene 2 (3-7s): Cut to phone screen showing ingredient list with red circles around problematic ingredients. Scene 3 (7-11s): Product reveal — our serum with clean ingredient list highlighted in green. Scene 4 (11-15s): Before/after split screen + CTA text overlay 'Free skin analysis — link in bio'.",
                "on_screen_text": "YOUR MOISTURIZER IS LYING → These ingredients are clogging your pores → Clean formula, real results → Free skin analysis + 20% off → Link in bio"
            },
            "brief_2": {
                "brief_number": 2,
                "brief_name": "The 47,000 Switch",
                "objective": "Drive conversions through massive social proof — create bandwagon effect and FOMO",
                "format": "Static carousel (1080x1080) — 5 slides for Instagram Feed",
                "audio_direction": "N/A (static format) — but if adapted to reel, use upbeat trending audio",
                "thumbnail_description": "Bold typography: '47,000 WOMEN SWITCHED THIS MONTH' in gold on black background. Subtle product silhouette in corner.",
                "cta_and_offer": "Shop now → Starter kit at 25% off → Free shipping on first order",
                "production_requirements": "Graphic designer for carousel creation, 8-10 real customer testimonial screenshots, product photography on clean background, brand template in Canva/Figma",
                "production_cost_estimate": "Rs. 3,000-5,000 (designer) or Rs. 500-1,000 (in-house with templates)",
                "scene_breakdown": "Slide 1: Bold stat — '47,000 women switched this month'. Slide 2: Grid of 6 customer selfies with star ratings. Slide 3: Before/after transformation (real customer, permission obtained). Slide 4: Product lineup with key ingredients called out. Slide 5: Offer card — 'Join them. Starter kit 25% off. Free shipping. 30-day guarantee.'",
                "on_screen_text": "47,000 WOMEN SWITCHED THIS MONTH → Real results from real women → See the transformation → Clean ingredients, clinical results → Starter Kit 25% OFF — Shop Now"
            },
            "brief_3": {
                "brief_number": 3,
                "brief_name": "The Dermatologist's Secret",
                "objective": "Build authority and trust through expert endorsement — drive saves and shares for mid-funnel nurturing",
                "format": "30-second vertical reel (9:16) for Instagram Reels",
                "audio_direction": "Clean, professional background music (think: wellness spa). Doctor speaks directly to camera. Subtitles mandatory.",
                "thumbnail_description": "Female dermatologist in white coat, text overlay: 'A DERMATOLOGIST'S HONEST OPINION' in clean sans-serif font.",
                "cta_and_offer": "Save this for your next skincare shopping trip → Link in bio for personalized routine",
                "production_requirements": "Female dermatologist (or credible medical professional), clinic or clean white background, professional lighting, teleprompter or well-rehearsed script, product placement in background",
                "production_cost_estimate": "Rs. 15,000-25,000 (if hiring dermatologist) or Rs. 5,000-8,000 (if brand advisor/in-house expert)",
                "scene_breakdown": "Scene 1 (0-5s): Doctor walks into frame, sits down. Text: 'I see 40 patients a day. 90% use too many products.' Scene 2 (5-15s): Doctor picks up 3 products. 'Here's all you actually need. A cleanser, this serum, and SPF. That's it.' Scene 3 (15-25s): Close-up of each product with ingredient callouts on screen. Scene 4 (25-30s): Doctor looks at camera: 'Stop overcomplicating your skin. Save this.' + CTA overlay.",
                "on_screen_text": "I see 40 patients a day → 90% use too many products → You only need 3 things → Cleanser + Serum + SPF → Stop overcomplicating your skin → Save this post"
            },
            "brief_4": {
                "brief_number": 4,
                "brief_name": "The Texture ASMR",
                "objective": "Drive saves and shares through sensory content — build brand desire and product curiosity",
                "format": "15-second vertical reel (9:16) — no talking, pure visual ASMR",
                "audio_direction": "ASMR audio: product dispensing sounds, gentle tapping, satisfying squeeze. No music, no voiceover. Let the texture sell itself.",
                "thumbnail_description": "Extreme close-up of serum droplet on fingertip, golden/amber color, bokeh background. Text: 'WATCH THIS TEXTURE' in minimal font.",
                "cta_and_offer": "Comment 'TEXTURE' to get the product link → Limited stock available",
                "production_requirements": "Macro lens or phone with macro mode, product samples, clean surface (marble or glass), good natural lighting, steady hands or tripod, ASMR-capable microphone",
                "production_cost_estimate": "Rs. 2,000-4,000 (in-house with phone) or Rs. 8,000-12,000 (professional macro videography)",
                "scene_breakdown": "Scene 1 (0-3s): Slow pour of serum from dropper — golden liquid catching light. Scene 2 (3-7s): Fingertip swirl showing texture and consistency. Close-up of absorption into skin. Scene 3 (7-11s): Side-by-side comparison with water-thin competitor serum vs. our rich texture. Scene 4 (11-15s): Product bottle hero shot with text overlay 'The texture that sold 47,000 units'.",
                "on_screen_text": "Watch this texture → Feel the difference → 47,000 units sold → Comment TEXTURE for the link"
            },
            "brief_5": {
                "brief_number": 5,
                "brief_name": "The Origin Story",
                "objective": "Build emotional brand connection through founder/brand narrative — drive follows and long-term loyalty",
                "format": "45-60 second vertical reel (9:16) for Instagram Reels — storytelling format",
                "audio_direction": "Emotional indie music (think: Prateek Kuhad style). Mix of voiceover narration and on-screen text. Cinematic feel.",
                "thumbnail_description": "Moody shot of lab with golden lighting. Text overlay: 'FROM A MUMBAI LAB TO 47,000 CUSTOMERS' in editorial font.",
                "cta_and_offer": "Follow for the full journey → New product dropping next month → Early access for followers",
                "production_requirements": "Lab footage (real or styled), product assembly/packaging shots, team working shots, founder or team member for narration, b-roll of Mumbai city, professional editing with color grading",
                "production_cost_estimate": "Rs. 20,000-35,000 (professional production) or Rs. 8,000-12,000 (phone-shot documentary style)",
                "scene_breakdown": "Scene 1 (0-10s): Moody lab shots. VO: 'It started with one question. Why doesn't any Indian skincare brand formulate specifically for Indian skin?' Scene 2 (10-25s): Montage of failed batches, late nights, testing. VO: '847 failed formulations. 3 years of research. 12 cities. One obsession.' Scene 3 (25-40s): First customer reaction, unboxing, testimonials rolling in. VO: '47,000 women later, we're just getting started.' Scene 4 (40-60s): Team shot, new product tease, follow CTA.",
                "on_screen_text": "Why doesn't any Indian brand formulate for Indian skin? → 847 failed formulations → 3 years of research → 12 Indian cities studied → 47,000 happy customers → We're just getting started → Follow for early access"
            }
        },
        "landing_page_intelligence": {
            "hero_section_strategy": "Lead with the problem ('Your skincare wasn't made for Indian skin') not the product. Show the hero product below the fold after establishing the problem. Use a real customer before/after as the hero image, not a product shot.",
            "offer_placement": "Sticky 'Add to Cart' bar that follows scroll. Price anchoring: show MRP crossed out with offer price. Trust badges (dermatologist approved, 30-day guarantee, free shipping) directly below CTA button.",
            "mobile_optimization_factors": "85% of Indian skincare buyers browse on mobile. Page must load in under 3 seconds on 4G. Use AMP or lightweight images. Accordion-style content sections. Thumb-friendly CTA buttons (minimum 48px). WhatsApp chat widget for instant queries.",
            "trust_signals_required": [
                "Dermatologist endorsement with name and credentials",
                "30-day money-back guarantee badge",
                "Verified customer review count (47,000+ reviews)",
                "Clinical test results or lab certification logos",
                "Secure payment icons (UPI, cards, COD available)",
                "Real customer before/after photos with testimonials"
            ],
            "conversion_killers": [
                "Slow page load (>3 seconds on mobile loses 53% of visitors)",
                "No COD option (kills 30-40% of potential orders in India)",
                "Hidden shipping costs revealed at checkout",
                "No WhatsApp support option (Indian buyers expect instant chat)",
                "Stock photos instead of real product/customer images"
            ],
            "recommended_page_structure": "Hero (problem statement + before/after) → Trust bar (badges) → Product reveal with ingredients → Social proof section (reviews + UGC) → How it works (3 steps) → Bundle offers → FAQ accordion → Final CTA with urgency"
        },
        "launch_recommendations": {
            "phase_1": {
                "budget": "Rs. 1,50,000-2,50,000/month",
                "success_metrics": "CTR > 2%, CPC < Rs. 15, 500+ add to carts, 100+ purchases, ROAS 0.8x-1.2x",
                "actions": [
                    "Launch 15 creatives across 3 ad sets in ASC campaign",
                    "Set up Meta Pixel + CAPI (Conversions API) for accurate tracking",
                    "Create 3 custom audiences: website visitors, Instagram engagers, video viewers",
                    "Test 3 hook angles simultaneously (problem, social proof, authority)",
                    "Set up automated rules: pause creatives with CPC > Rs. 25 after Rs. 3,000 spend",
                    "Launch email capture with 10% off first order for remarketing"
                ]
            },
            "phase_2": {
                "budget": "Rs. 3,00,000-5,00,000/month",
                "success_metrics": "ROAS > 1.5x, CAC < Rs. 600, 500+ purchases/month, email list > 5,000",
                "actions": [
                    "Scale winning creatives by 20% budget increase every 3 days",
                    "Launch lookalike audiences from purchasers (1%, 3%, 5%)",
                    "Introduce retargeting campaigns for cart abandoners and website visitors",
                    "Test YouTube Shorts ads with top-performing reel content",
                    "Launch influencer seeding program (20-30 micro-influencers)",
                    "Implement post-purchase review collection flow"
                ]
            },
            "phase_3": {
                "budget": "Rs. 5,00,000-10,00,000/month",
                "success_metrics": "ROAS > 2.5x, CAC < Rs. 500, 1500+ purchases/month, 20% repeat purchase rate",
                "actions": [
                    "Full ASC scaling with 30+ creatives in rotation",
                    "Launch branded content ads with top-performing influencer content",
                    "Introduce subscription/auto-replenishment model",
                    "Expand to Google Search ads for high-intent keywords",
                    "Launch referral program for existing customers",
                    "Test Pinterest and Google Discovery for incremental reach"
                ]
            }
        },
        "budget_deployment": {
            "total_monthly_budget": "Rs. 1,50,000-2,50,000 (Phase 1 recommendation)",
            "asc_campaign_structure": "Single ASC campaign with 15-20 creatives. Daily budget Rs. 5,000-8,000. Cost cap bidding after 50 conversions. No audience restrictions initially — let Advantage+ optimize.",
            "creative_refresh_cadence": "Replace bottom 30% performers every 2 weeks. Full creative refresh every 6 weeks. Always have 5 new creatives ready to launch when removing underperformers.",
            "scaling_triggers": "Scale budget by 20% when: ROAS exceeds 2x for 3 consecutive days, CPA is below target for 5 days, or a creative maintains CTR > 3% for 7 days. Never increase budget by more than 30% in a single day.",
            "scalability_ceiling": "At Rs. 10L/month spend, expect diminishing returns. Beyond this, diversify to YouTube, Google, and influencer marketing. Meta alone will plateau at approximately Rs. 8-12L/month for this category in India.",
            "expected_metrics": {
                "month_1": "ROAS 0.8x, CAC Rs. 700, 150 orders",
                "month_2": "ROAS 1.2x, CAC Rs. 550, 300 orders",
                "month_3": "ROAS 1.8x, CAC Rs. 480, 500 orders",
                "month_4": "ROAS 2.2x, CAC Rs. 420, 750 orders",
                "month_5": "ROAS 2.8x, CAC Rs. 380, 1000 orders",
                "month_6": "ROAS 3.5x, CAC Rs. 350, 1500 orders"
            }
        },
        "risk_factors": {
            "competitive_response_risk": "Minimalist and Dot & Key will likely respond with increased ad spend within 2-3 months of your entry. Prepare by building a content moat — 40+ creatives in rotation makes it expensive for competitors to match your testing velocity.",
            "creative_fatigue_timeline": "Expect winning creatives to fatigue within 3-4 weeks at scale. Budget for continuous creative production. The brands that win in Indian D2C are not the ones with the best single ad — they're the ones that produce the most variations fastest.",
            "pricing_war_risk": "If competitors drop prices, do NOT match. Instead, increase perceived value through bundling, loyalty rewards, and superior content. Price wars in Indian skincare always hurt margins without building lasting advantage.",
            "cod_rto_risk": "COD orders will have 15-20% RTO rate in India. Mitigate with: prepaid discount (extra 5% off), WhatsApp order confirmation within 1 hour, automated shipping updates via SMS. Target 60% prepaid ratio by month 3.",
            "platform_policy_risk": "Meta frequently updates ad policies for health and beauty claims. Avoid: before/after claims that imply medical results, percentage improvement claims without clinical backing, any language that promises to 'cure' skin conditions. Always have a dermatologist review ad copy.",
            "design_piracy_risk": "Successful ad creatives in India get copied within 1-2 weeks. Protect by: watermarking UGC content, building brand recognition through consistent visual identity, and producing volume that makes copying individual ads pointless."
        }
    })
}

def test_generate_pdf():
    print("Testing /generate-pdf with large realistic payload...")
    print(f"Payload size: {len(json.dumps(TEST_PAYLOAD)):,} bytes")

    try:
        resp = requests.post(f"{BASE_URL}/generate-pdf", json=TEST_PAYLOAD, timeout=60)
        print(f"Status: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            print(f"SUCCESS! Filename: {data.get('filename')}")
            pdf_bytes = len(data.get('pdf_base64', ''))
            print(f"PDF base64 size: {pdf_bytes:,} chars (~{pdf_bytes * 3 // 4:,} bytes)")
        else:
            print(f"FAILED! Response: {resp.text[:2000]}")
    except requests.ConnectionError:
        print("ERROR: Could not connect. Is the server running? (python app.py)")
    except Exception as e:
        print(f"ERROR: {e}")

def test_health():
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Health check: {resp.status_code} — {resp.json()}")
    except requests.ConnectionError:
        print("Health check FAILED: server not running")

if __name__ == '__main__':
    test_health()
    test_generate_pdf()
