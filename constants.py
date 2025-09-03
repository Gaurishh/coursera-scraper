"""
Centralized constants file for the Coursera Scraper project.
All configuration variables are organized by file for easy maintenance.
"""

import os

# =============================================================================
# SHARED VARIABLES (Used by multiple files)
# =============================================================================

# API Configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "YOUR_API_KEY_HERE")

# API URLs
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

# Common Timeouts (in seconds)
DEFAULT_REQUEST_TIMEOUT = 10
API_REQUEST_TIMEOUT = 60
LONG_API_REQUEST_TIMEOUT = 90

# Common Retry Configuration
DEFAULT_MAX_RETRIES = 5

# Common Threading Configuration
DEFAULT_MAX_WORKERS = 6
MAX_CONSECUTIVE_ERRORS = 5

# Common Rate Limiting
DEFAULT_REQUEST_DELAY = 0.1
PAGINATION_DELAY = 2

# Common User Agent
DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# Common Content Validation
MIN_CONTENT_LENGTH = 100

# Common File Extensions
ALLOWED_WEB_EXTENSIONS = ['.html', '.htm', '.php', '.asp', '.aspx', '.jsp']

# Common URL Patterns to Skip
SKIP_URL_PATTERNS = ['javascript:', 'mailto:', 'tel:', '#']

# =============================================================================
# 1_institutions_list_fetcher.py
# =============================================================================

# Search Configuration
CITIES_TO_SEARCH = ["Bangalore", "Delhi"]
INSTITUTION_TYPES = ["Corporates", "Schools"]
MAX_PAGES_PER_QUERY = 3

# Location Categorization
BANGALORE_KEYWORDS = ["bangalore", "bengaluru", "karnataka"]
DEFAULT_LOCATION = "Delhi"

# Google Places API Configuration
GOOGLE_PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
GOOGLE_PLACES_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

# Google Places API Fields
PLACE_DETAILS_FIELDS = "name,website,formatted_phone_number,formatted_address,types"

# Rate Limiting for Google Places API
GOOGLE_PLACES_RATE_LIMIT_DELAY = 0.1  # 100ms delay between requests

# Output File
INITIAL_LEADS_OUTPUT_FILE = "1_discovered_leads.csv"

# =============================================================================
# 2_website_crawler.py
# =============================================================================

# Input/Output Configuration
WEBSITE_CRAWLER_INPUT_CSV = '1_discovered_leads.csv'
WEBSITE_CRAWLER_OUTPUT_DIR = 'websites'

# Threading Configuration
WEBSITE_CRAWLER_MAX_WORKERS = 10
MAX_WEBSITES_LIMIT = 1000  # Limit for testing (set to None for all websites)

# Crawling Limits
MAX_URLS_PER_WEBSITE = 100
MAX_CONSECUTIVE_FAILURES = 5  # Stop crawling after 5 consecutive failures

# Request Configuration
WEBSITE_CRAWLER_TIMEOUT = 5  # Shorter timeout for better performance
WEBSITE_CRAWLER_DELAY = 0.1  # Small delay to be respectful to the server

# Backoff Configuration
MAX_BACKOFF_TIME = 10  # Maximum backoff time in seconds

# =============================================================================
# 3_top_5_urls_for_recommendation_extractor.py
# =============================================================================

# Input/Output Configuration
RECOMMENDATION_INPUT_DIR = "websites"
RECOMMENDATION_OUTPUT_DIR = "top_5_urls_for_recommendation"

# Threading Configuration
RECOMMENDATION_MAX_WORKERS = 3

# URL Validation Configuration
RECOMMENDATION_MAX_CONSECUTIVE_ERRORS = 5

# =============================================================================
# 4_leads_classified_generator.py
# =============================================================================

# Input/Output Configuration
CLASSIFICATION_INITIAL_LEADS_FILE = "1_discovered_leads.csv"
CLASSIFICATION_WEBSITES_DIR = "websites"
CLASSIFICATION_URL_FILES_DIR = "top_5_urls_for_recommendation"
CLASSIFICATION_OUTPUT_FILE = "2_leads_classified.csv"

# Threading Configuration
CLASSIFICATION_MAX_WORKERS = 6

# =============================================================================
# 5_top_5_urls_for_contact_info_extractor.py
# =============================================================================

# Input/Output Configuration
CONTACT_INFO_INPUT_CSV = "2_leads_classified.csv"
CONTACT_INFO_INPUT_DIR = "websites"
CONTACT_INFO_OUTPUT_DIR = "top_5_urls_for_contact_info"
CONTACT_INFO_ERROR_LOG_FILE = "llm_failure_log.json"

# Threading Configuration
CONTACT_INFO_MAX_WORKERS = 6
CONTACT_INFO_MAX_CONSECUTIVE_ERRORS = 5

# =============================================================================
# 6_final_data_gatherer.py
# =============================================================================

# Input/Output Configuration
FINAL_GATHERER_INPUT_CSV = "2_leads_classified.csv"
FINAL_GATHERER_CONTACT_URLS_DIR = "top_5_urls_for_contact_info"
FINAL_GATHERER_OUTPUT_DIR = "contact_info"

# Threading Configuration
FINAL_GATHERER_MAX_WORKERS = 6

# =============================================================================
# 7_final_output_generator.py
# =============================================================================

# Input/Output Configuration
FINAL_OUTPUT_FILE = "output.json"

# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

# 3_top_5_urls_for_recommendation_extractor.py
MASTER_PROMPT_TEMPLATE = """
Persona:
You are an expert data analyst specializing in website structure. Your task is to identify the most informative URLs from a given list that will help a sales team understand an institution's focus.

Primary Goal:
Select the most informative URLs from the list below that will help a sales team understand an institution's focus. Choose up to 5 URLs (or all available URLs if there are fewer than 5) that are most likely to contain information about the institution's core purpose, courses offered, industry partnerships, or team structure. This information will be used to recommend either a 'Programming' course or a 'Sales' course. Use your own expert judgment to determine the most relevant URLs from the list.

IMPORTANT: If any URLs contain "/about" or "/about-us" in their path, prioritize these URLs as they are most likely to contain information about the institution's core purpose and focus.

List of URLs to Analyze:
{url_list_json}

Required Output Format:
Your response MUST be a valid JSON object and nothing else. The JSON object should contain a single key, 'selected_urls', with a list of the most relevant URLs you have chosen (up to 5, or all available if fewer than 5).
Example: {{"selected_urls": ["url_1", "url_2", "url_3"]}}
"""

# 4_leads_classified_generator.py
CLASSIFICATION_PROMPT_TEMPLATE = """
Persona: 
You are an expert B2B sales analyst for Coursera.

Context: 
Your goal is to analyze the provided text from an institution's website and recommend either a 'Programming' or 'Sales' course. The institution is a '{institution_type}'.

Rules:
1. Base your decision on the content from the following web pages.
2. A high score (90+) for Programming is warranted for engineering colleges or companies with a strong tech focus.
3. A high score (90+) for Sales is warranted for business schools or companies in sales-driven industries.
4. Provide a confidence score from 0 to 100 representing how strongly you recommend the course.
5. Provide a brief one-sentence justification for your choice.

Website Content:
{website_content}

Your Task:
Respond ONLY with a valid JSON object in the following format: {{"recommended_course": "<Programming or Sales>", "confidence_score": <number>, "reasoning": "<your_one_sentence_reason>"}}
"""

# 5_top_5_urls_for_contact_info_extractor.py
PROGRAMMING_MASTER_PROMPT_TEMPLATE = """
Persona:
You are an expert data analyst specializing in website structure and contact information discovery for technology companies. Your task is to identify the most informative URLs from a given list that will help a sales team find contact information, key personnel, and communication channels for programming course sales.

Primary Goal:
Select the most informative URLs from the list below that are most likely to contain contact information, key personnel details, or communication channels relevant to programming course sales. Choose up to 5 URLs (or all available URLs if there are fewer than 5) that are most likely to contain:
- Contact information (phone numbers, email addresses, physical addresses)
- Key personnel (CTO, technical directors, IT managers, decision makers)
- Communication channels (contact forms, inquiry pages, support)
- Company/organization details (about us, leadership, team)
- Technical departments (IT, software development, engineering)
- Training or education departments
- Business development or partnership information

IMPORTANT: If any URLs contain "/contact" or "/contact-us" in their path, prioritize these URLs as they are most likely to contain direct contact information.

This information will be used for programming course sales outreach and lead generation. Use your own expert judgment to determine the most relevant URLs from the list.

List of URLs to Analyze:
{url_list_json}

Required Output Format:
Your response MUST be a valid JSON object and nothing else. The JSON object should contain a single key, 'selected_urls', with a list of the most relevant URLs you have chosen (up to 5, or all available if fewer than 5).
Example: {{"selected_urls": ["url_1", "url_2", "url_3"]}}
"""

SALES_MASTER_PROMPT_TEMPLATE = """
Persona:
You are an expert data analyst specializing in website structure and contact information discovery for business organizations. Your task is to identify the most informative URLs from a given list that will help a sales team find contact information, key personnel, and communication channels for sales course sales.

Primary Goal:
Select the most informative URLs from the list below that are most likely to contain contact information, key personnel details, or communication channels relevant to sales course sales. Choose up to 5 URLs (or all available URLs if there are fewer than 5) that are most likely to contain:
- Contact information (phone numbers, email addresses, physical addresses)
- Key personnel (sales managers, business development directors, marketing managers, decision makers)
- Communication channels (contact forms, inquiry pages, support)
- Company/organization details (about us, leadership, team)
- Business departments (sales, marketing, business development)
- Training or HR departments
- Business development or partnership information

IMPORTANT: If any URLs contain "/contact" or "/contact-us" in their path, prioritize these URLs as they are most likely to contain direct contact information.

This information will be used for sales course sales outreach and lead generation. Use your own expert judgment to determine the most relevant URLs from the list.

List of URLs to Analyze:
{url_list_json}

Required Output Format:
Your response MUST be a valid JSON object and nothing else. The JSON object should contain a single key, 'selected_urls', with a list of the most relevant URLs you have chosen (up to 5, or all available if fewer than 5).
Example: {{"selected_urls": ["url_1", "url_2", "url_3"]}}
"""

# 6_final_data_gatherer.py
CONTACT_EXTRACTION_PROMPT_TEMPLATE = """
Persona:
You are an expert data extraction specialist specializing in contact information discovery from website content.

Context:
Your goal is to analyze the provided text from an institution's website and extract all relevant and actionable contact information, including names, titles/positions, phone numbers, and email addresses.

Rules:

Extract ALL potential contact information found in the provided website content.

Look for names of people, their titles/positions, phone numbers, and email addresses.

Focus on key personnel such as directors, managers, coordinators, heads of departments, etc.

Include both individual contacts and general contact information.

Inclusion Criteria: A contact must only be included in the final list if it contains at least one phone number OR at least one email address. Discard any entries that only have a name and/or title.

If you find multiple contact details for the same person, combine them into one entry.

Be thorough but accurate - only extract information that is clearly present in the text.

Website Content:
{website_content}

Your Task:
Respond ONLY with a valid JSON object containing an array of contact objects. Each contact object should have the following structure (include only the fields that are available):
{{
"contacts": [
{{
"name": "Full Name",
"title": "Job Title/Position",
"phone": "Phone Number",
"email": "Email Address"
}},
{{
"name": "Another Person",
"title": "Another Title",
"phone": "Another Phone"
}},
...
]
}}

Note: Only include the fields that are available in the source text. If a field is not available, simply omit it from the contact object.
If no actionable contact information is found, return: {{"contacts": []}}
"""

# =============================================================================
# KEYWORD SCORING DICTIONARIES
# =============================================================================

# 3_top_5_urls_for_recommendation_extractor.py
GENERAL_CLASSIFICATION_SCORES = {
    # Tier 1 (Score 10): Core Offerings, Departments & Academic Programs
    'services': 10, 'solutions': 10, 'products': 10, 'courses': 10, 'programmes': 10,
    'academics': 10, 'curriculum': 10, 'syllabus': 10, 'departments': 10,
    'computer-science': 10, 'engineering': 10, 'technology': 10, 'software': 10, 'development': 10,
    'b-tech': 10, 'mca': 10, 'mba': 10, 'bba': 10, 'pgdm': 10,
    'marketing': 9, 'sales': 9, 'digital-marketing': 9, 'data-science': 9, 'ai-ml': 9,

    # Tier 2 (Score 8): People, Placements & High-Level Company Info
    'faculty': 8, 'placements': 8, 'tpo': 8, 'corporate-training': 8,
    'about': 8, 'about-us': 8, 'company': 8, 'profile': 8,

    # Tier 3 (Score 6): Supporting Information & Activities
    'training': 6, 'portfolio': 6, 'our-work': 6, 'research': 6, 'innovation': 6,
    'team': 6, 'leadership': 6, 'careers': 6, 'jobs': 6,

    # Tier 4 (Score 3): General Content & Administrative Pages
    'blog': 3, 'news': 3, 'events': 3, 'admissions': 3,

    # Tier 5 (Score 1): Utility/Noise Pages
    'contact': 1, 'contact-us': 1, 'gallery': 1, 'alumni': 1, 'sitemap': 1,

    # Negative Keywords (heavily penalized to filter them out)
    'privacy': -50, 'terms': -50, 'login': -50, 'cart': -50, 'author': -50,
    'category': -50, 'tag': -50, 'wp-login': -50, 'admin': -50
}

# 5_top_5_urls_for_contact_info_extractor.py
PROGRAMMING_KEYWORD_SCORES = {
    # Tier 1 (Score 10): Direct Contact & High-Value Departments
    'contact': 10, 'contact-us': 10, 'contactus': 10, 'reachus': 10, 'enquiry': 10,
    'placements': 10, 'tpo': 10, 'training-placements': 10, 'corporate-training': 10, 'recruiters': 10,
    
    # Tier 2 (Score 9): Key Technical Leadership & Departments
    'cto': 9, 'engineering': 9, 'technology': 9, 'software-development': 9, 'it': 9, 'development': 9,
    'computer-science': 9, 'information-science': 9, 'data-science': 9, 'ai-ml': 9, 'artificial-intelligence': 9,
    'hod': 9, 'faculty': 9, 'corporate-relations': 9,

    # Tier 3 (Score 8): General Leadership & Company Information
    'about': 8, 'about-us': 8, 'team': 8, 'leadership': 8, 'ceo': 8, 'founder': 8, 'company': 8, 'profile': 8,
    
    # Tier 4 (Score 7): Related Technical Fields & Services
    'devops': 7, 'cloud': 7, 'full-stack': 7, 'cyber-security': 7, 'blockchain': 7, 'iot': 7,
    'services': 7, 'solutions': 7, 'portfolio': 7, 'our-work': 7,

    # Tier 5 (Score 6): Education & Training Context
    'training': 6, 'courses': 6, 'education': 6, 'academics': 6, 'admission': 6, 'syllabus': 6,
    'internship': 6, 'projects': 6,
    
    # Tier 6 (Score 5): Career & Job Opportunities
    'careers': 5, 'jobs': 5, 'career': 5, 'hiring': 5,

    # Tier 7 (Score 2): Low Priority / General Content
    'blog': 2, 'news': 2, 'events': 2, 'gallery': 2, 'media': 2,

    # Negative Keywords (heavily penalized to push them to the bottom)
    'privacy': -50, 'terms': -50, 'sitemap': -50, 'alumni': -20, 'login': -50, 'cart': -50,
    'author': -50, 'category': -50, 'tag': -50, 'wp-login': -50, 'admin': -50
}

SALES_KEYWORD_SCORES = {
    # Tier 1 (Score 10): Direct Contact & Admissions
    'contact': 10, 'contact-us': 10, 'contactus': 10, 'enquiry': 10, 'reachus': 10,
    'admissions': 10, 'admission': 10, 'apply-now': 10,

    # Tier 2 (Score 9): Key Business Leadership & Departments
    'sales': 9, 'marketing': 9, 'business-development': 9, 'partnerships': 9, 'b2b': 9,
    'ceo': 9, 'founder': 9, 'leadership': 9, 'management': 9,

    # Tier 3 (Score 8): Relevant Business Programs & Client Info
    'mba': 8, 'bba': 8, 'pgdm': 8, 'clients': 8, 'clientele': 8, 'partners': 8,
    'digital-marketing': 8, 'ppc': 8, 'seo': 8, 'advertising': 8,

    # Tier 4 (Score 7): General Company & Course Information
    'about': 7, 'about-us': 7, 'company': 7, 'team': 7, 'profile': 7,
    'courses': 7, 'programs': 7, 'education': 7, 'academics': 7, 'fee-structure': 7,

    # Tier 5 (Score 6): Broader Services & Training
    'services': 6, 'solutions': 6, 'corporate-training': 6, 'training': 6,
    'consultancy': 6, 'portfolio': 6,
    
    # Tier 6 (Score 5): Career & Job Opportunities
    'careers': 5, 'jobs': 5, 'career': 5, 'hiring': 5,

    # Tier 7 (Score 2): Low Priority / General Content
    'blog': 2, 'news': 2, 'events': 2, 'gallery': 2, 'media': 2,

    # Negative Keywords (heavily penalized)
    'privacy': -50, 'terms': -50, 'sitemap': -50, 'alumni': -20, 'login': -50, 'cart': -50,
    'author': -50, 'category': -50, 'tag': -50, 'wp-login': -50, 'admin': -50
}
