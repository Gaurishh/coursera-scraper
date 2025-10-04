import os
import json
import requests
import time
import re
from urllib.parse import urlparse

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, continue without it
    pass

# Import constants
from constants import (
    GEMINI_API_KEY, RECOMMENDATION_INPUT_DIR, RECOMMENDATION_OUTPUT_DIR,
    RECOMMENDATION_MAX_WORKERS, RECOMMENDATION_MAX_CONSECUTIVE_ERRORS,
    DEFAULT_REQUEST_TIMEOUT, DEFAULT_MAX_RETRIES,
    MASTER_PROMPT_TEMPLATE, GENERAL_CLASSIFICATION_SCORES
)

# Import LLM utilities
from llm_utils import call_gemini_with_params, parse_llm_response

# --- LLM Master Prompt ---
# This detailed prompt guides the LLM to make a reliable and informed decision.
# (Prompt template is now imported from constants.py)

# --- Enhanced Gemini 2.5 Flash API Function ---
def generate_content_with_gemini(prompt, max_retries=DEFAULT_MAX_RETRIES):
    """
    Generate content using enhanced Gemini 2.5 Flash with task-specific parameters.
    
    Args:
        prompt (str): The prompt to send to Gemini
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        str: Generated content or None if failed
    """
    response_text, error_details = call_gemini_with_params(
        prompt=prompt,
        task_type="url_selection",
        max_retries=max_retries
    )
    
    if error_details:
        print(f"❌ LLM call failed: {error_details}")
        return None
    
    return response_text

# --- URL Normalization Function ---
def normalize_url_for_processing(url):
    """
    Normalize URL for processing by adding https://www. prefix if not present.
    This ensures URLs from the website crawler (which stores normalized URLs like 'domain.com/path')
    are converted back to full URLs for processing.
    
    Args:
        url (str): URL to normalize (may be in format 'domain.com/path' or full URL)
        
    Returns:
        str: Full URL with https://www. prefix
    """
    # If URL already has protocol, return as is
    if url.startswith(('http://', 'https://')):
        return url
    
    # Add https://www. prefix to normalized URLs
    return f"https://www.{url}"

# --- About URL Prioritization Function ---
def prioritize_about_urls(urls):
    """
    Prioritizes URLs containing exactly '/about' or '/about-us' to ensure they are always selected.
    
    Args:
        urls (list): List of URLs to prioritize
        
    Returns:
        tuple: (about_urls, non_about_urls)
    """
    about_urls = []
    non_about_urls = []
    
    for url in urls:
        url_lower = url.lower()
        # Check for exact matches: '/about' or '/about-us' (not just containing these strings)
        if url_lower.endswith('/about') or url_lower.endswith('/about-us') or '/about/' in url_lower or '/about-us/' in url_lower:
            about_urls.append(url)
        else:
            non_about_urls.append(url)
    
    return about_urls, non_about_urls

# --- URL Validation Function ---
def validate_url_content(url, timeout=DEFAULT_REQUEST_TIMEOUT):
    """
    Validates if a URL returns valid HTML content.
    
    Args:
        url (str): URL to validate
        timeout (int): Request timeout in seconds
        
    Returns:
        bool: True if URL returns valid HTML content, False otherwise
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        # Check if response is HTML
        content_type = response.headers.get('content-type', '').lower()
        if 'text/html' in content_type:
            # Check if content is not empty and has reasonable length
            content = response.text.strip()
            if len(content) > 100:  # Minimum content length threshold
                return True
        
        return False
        
    except Exception as e:
        print(f"WARN: URL validation failed for {url}: {e}")
        return False

# --- Fallback Function (Guardrail) ---
# This runs if the LLM fails, ensuring the script never crashes.
# (Keyword scores are now imported from constants.py)

def get_prioritized_urls(url_list, keyword_scores):
    """
    Scores and sorts URLs based on a refined keyword matching algorithm.
    This function tokenizes URLs for accuracy, uses max score logic, positional weighting,
    and handles negative keywords.
    """
    scored_urls = []
    # Prioritize longer, more specific keywords first (e.g., 'contact-us' before 'contact')
    sorted_keywords = sorted(keyword_scores.keys(), key=len, reverse=True)

    for url in url_list:
        max_score = 0
        is_penalized = False

        parsed_url = urlparse(url)
        path = parsed_url.path
        
        # Tokenize the URL path for accurate matching
        clean_path = re.sub(r'[\/_-]', ' ', path).lower()
        tokens = clean_path.split()
        
        highest_keyword_score = 0
        keyword_pos = float('inf')

        for keyword in sorted_keywords:
            found_in_url = False
            for i, token in enumerate(tokens):
                if keyword in token:
                    score = keyword_scores[keyword]
                    
                    # Apply penalty immediately and stop processing this URL
                    if score < 0:
                        max_score = score
                        is_penalized = True
                        break
                    
                    # "Max Score" logic: only the highest value keyword determines the score
                    if score > highest_keyword_score:
                       highest_keyword_score = score
                       keyword_pos = i
                       
                    found_in_url = True
                    break  # Found the most specific keyword, move to the next keyword
            if found_in_url:
                break # A keyword has been matched, move to the next URL

        if is_penalized:
            scored_urls.append((url, max_score))
            continue

        # Apply positional weighting: keywords earlier in the URL are more important
        if highest_keyword_score > 0 and keyword_pos != float('inf'):
            positional_decay = 0.95 ** keyword_pos
            max_score = highest_keyword_score * positional_decay
        
        # Give a small bonus for root URLs
        if not path or path == '/':
            max_score += 2

        scored_urls.append((url, max_score))

    # Sort URLs by score in descending order
    scored_urls.sort(key=lambda x: x[1], reverse=True)
    
    return [url for url, score in scored_urls]

# --- Main Wrapper Function for Classification ---

def get_all_urls_deterministic_classification(url_list):
    """Wrapper function to sort URLs for website topic classification."""
    print("INFO: Using improved algorithm for website classification.")
    return get_prioritized_urls(url_list, GENERAL_CLASSIFICATION_SCORES)

# --- Processing Function ---
def process_single_website(filename):
    """
    Process a single website file.
    Uses about URL prioritization first, then LLM selection, with deterministic queue as backup.
    Validates each selected URL and replaces invalid ones from the queue.
    
    Args:
        filename (str): Name of the website file to process
        
    Returns:
        tuple: (success, filename, urls_processed, error_message)
    """
    input_filepath = os.path.join(RECOMMENDATION_INPUT_DIR, filename)
    output_filepath = os.path.join(RECOMMENDATION_OUTPUT_DIR, filename)
    
    try:
        # Read URLs from file and normalize them
        with open(input_filepath, 'r', encoding='utf-8') as f:
            raw_urls = [line.strip() for line in f if line.strip()]
        
        if not raw_urls:
            return (False, filename, 0, "No URLs found in file")
            
        # Normalize URLs for processing (add https://www. if not present)
        urls = [normalize_url_for_processing(url) for url in raw_urls]
        print(f"📝 Normalized {len(urls)} URLs for processing from {filename}")
        
        # Step 1: Prioritize about URLs first
        about_urls, non_about_urls = prioritize_about_urls(urls)
        if about_urls:
            print(f"🎯 Found {len(about_urls)} about URLs: {about_urls}")
        else:
            print(f"⚠️  No about URLs found in {len(urls)} total URLs")
        
        # Step 2: Create prioritized URL queue for non-about URLs
        top_urls = get_all_urls_deterministic_classification(non_about_urls)
        print(f"📋 Created prioritized queue with {len(top_urls)} non-about URLs for {filename}")
        
        # Step 3: Build final URL selection starting with about URLs
        final_selected_urls = []
        about_urls_added = 0
        
        # First, add all about URLs (up to 5 total)
        for about_url in about_urls:
            if len(final_selected_urls) < 5:
                final_selected_urls.append(about_url)
                about_urls_added += 1
        
        # Step 4: Use LLM to select remaining URLs from non-about URLs
        remaining_slots = 5 - len(final_selected_urls)
        if remaining_slots > 0 and non_about_urls:
            prompt = MASTER_PROMPT_TEMPLATE.format(url_list_json=json.dumps(non_about_urls))
            llm_selected_urls = []
            llm_success = False
            
            # Try Gemini 2.5 Flash first
            print(f"🤖 Attempting LLM selection for {remaining_slots} remaining slots...")
            response_text = generate_content_with_gemini(prompt)
            
            if response_text:
                print(f"📝 LLM response received, parsing...")
                data, parse_error = parse_llm_response(response_text, "json")
                
                if parse_error:
                    print(f"⚠️  WARN: Gemini response parsing failed for {filename}. Error: {parse_error}")
                    llm_success = False
                elif isinstance(data.get('selected_urls'), list) and len(data['selected_urls']) > 0:
                    llm_selected_urls = data['selected_urls']
                    # Limit to remaining slots
                    llm_selected_urls = llm_selected_urls[:remaining_slots]
                    llm_success = True
                    print(f"✅ SUCCESS: Gemini 2.5 Flash selected {len(llm_selected_urls)} non-about URLs for {filename}")
                else:
                    print(f"⚠️  WARN: Gemini response did not contain a valid list of URLs for {filename}")
                    llm_success = False
            else:
                print(f"⚠️  WARN: No response from Gemini API for {filename}")
                llm_success = False
            
            # Fallback to deterministic selection if Gemini failed or not available
            if not llm_success:
                print(f"🔄 Using top {remaining_slots} from prioritized queue for {filename}")
                llm_selected_urls = top_urls[:remaining_slots]
                # Remove these URLs from the queue
                top_urls = top_urls[remaining_slots:]
            
            # Add LLM/fallback selected URLs to final selection
            for url in llm_selected_urls:
                if len(final_selected_urls) < 5 and url not in final_selected_urls:
                    final_selected_urls.append(url)
        
        # If we still need more URLs, get them from the queue
        while len(final_selected_urls) < 5 and top_urls:
            next_url = top_urls.pop(0)
            if next_url not in final_selected_urls:
                final_selected_urls.append(next_url)
        
        if about_urls_added > 0:
            print(f"🎯 PRIORITIZED: Added {about_urls_added} about URLs to final selection")
        
        # Step 5: Validate each URL and replace invalid ones with next from queue
        final_urls = []
        consecutive_errors = 0
        
        print(f"🔍 Validating and finalizing {len(final_selected_urls)} URLs for {filename}")
        
        for i, url in enumerate(final_selected_urls):
            print(f"  Testing URL {i+1}/{len(final_selected_urls)}: {url}")
            
            if validate_url_content(url):
                final_urls.append(url)
                print(f"  ✅ Valid: {url}")
                consecutive_errors = 0  # Reset error counter on success
            else:
                print(f"  ❌ Invalid: {url}")
                consecutive_errors += 1
                
                # Check if we've hit the consecutive error limit
                if consecutive_errors >= RECOMMENDATION_MAX_CONSECUTIVE_ERRORS:
                    print(f"  🛑 STOPPING: {consecutive_errors} consecutive errors reached. Website may be unreachable.")
                    break
                
                # Find next valid URL from the queue
                replacement_found = False
                while top_urls and not replacement_found and consecutive_errors < RECOMMENDATION_MAX_CONSECUTIVE_ERRORS:
                    next_url = top_urls.pop(0)  # Pop from the front of the queue
                    # Check against both final_urls and final_selected_urls to prevent duplicates
                    if next_url not in final_urls and next_url not in final_selected_urls:
                        print(f"  🔄 Trying replacement: {next_url}")
                        if validate_url_content(next_url):
                            final_urls.append(next_url)
                            print(f"  ✅ Valid replacement: {next_url}")
                            replacement_found = True
                            consecutive_errors = 0  # Reset error counter on success
                        else:
                            print(f"  ❌ Invalid replacement: {next_url}")
                            consecutive_errors += 1
                            
                            # Check consecutive errors again
                            if consecutive_errors >= RECOMMENDATION_MAX_CONSECUTIVE_ERRORS:
                                print(f"  🛑 STOPPING: {consecutive_errors} consecutive errors reached. Website may be unreachable.")
                                break
                
                if not replacement_found and consecutive_errors < RECOMMENDATION_MAX_CONSECUTIVE_ERRORS:
                    print(f"  ⚠️  No valid replacement found for {url}")
                elif consecutive_errors >= RECOMMENDATION_MAX_CONSECUTIVE_ERRORS:
                    break
        
        # Step 6: Save the results
        if final_urls:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                for url in final_urls:
                    f.write(url + '\n')
            print(f"💾 Saved {len(final_urls)} valid URLs to {filename}")
            print(f"📊 Summary for {filename}: {len(final_urls)} final URLs")
            return (True, filename, len(final_urls), None)
        else:
            error_msg = f"No valid URLs found for {filename}"
            print(f"❌ {error_msg}")
            return (False, filename, 0, error_msg)
            
    except Exception as e:
        error_msg = f"Error processing {filename}: {e}"
        print(f"❌ {error_msg}")
        return (False, filename, 0, error_msg)

# --- Main Logic ---
def process_websites():
    """
    Main function to process websites.
    """
    if not os.path.exists(RECOMMENDATION_INPUT_DIR):
        print(f"❌ ERROR: Input directory '{RECOMMENDATION_INPUT_DIR}' not found.")
        return

    if not os.path.exists(RECOMMENDATION_OUTPUT_DIR):
        print(f"📁 INFO: Output directory '{RECOMMENDATION_OUTPUT_DIR}' not found. Creating it.")
        os.makedirs(RECOMMENDATION_OUTPUT_DIR)

    website_files = [f for f in os.listdir(RECOMMENDATION_INPUT_DIR) if f.endswith('.txt')]
    
    if not website_files:
        print(f"❌ No website files found in '{RECOMMENDATION_INPUT_DIR}' directory.")
        return

    print(f"🚀 Starting URL Recommendation Extractor")
    print("=" * 60)
    print(f"📊 Total websites to process: {len(website_files)}")
    print(f"🛑 Max consecutive errors: {RECOMMENDATION_MAX_CONSECUTIVE_ERRORS}")
    print(f"📁 Input directory: {RECOMMENDATION_INPUT_DIR}")
    print(f"📁 Output directory: {RECOMMENDATION_OUTPUT_DIR}")
    print("=" * 60)

    # Process websites sequentially
    start_time = time.time()
    successful_processes = 0
    total_urls_processed = 0
    
    for i, filename in enumerate(website_files, 1):
        try:
            success, processed_filename, urls_count, error_msg = process_single_website(filename)
            
            if success:
                successful_processes += 1
                total_urls_processed += urls_count
                print(f"✅ [{i}/{len(website_files)}] Success: {processed_filename} - {urls_count} URLs extracted")
            else:
                print(f"❌ [{i}/{len(website_files)}] Failed: {processed_filename} - {error_msg}")
                
        except Exception as e:
            print(f"❌ [{i}/{len(website_files)}] Exception for {filename}: {e}")
    
    # Calculate execution time
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Display summary
    print("\n" + "=" * 60)
    print("🎉 PROCESSING COMPLETE!")
    print("=" * 60)
    print(f"⏱️  Total Execution Time: {execution_time:.2f} seconds")
    print(f"📊 Websites Processed: {len(website_files)}")
    print(f"✅ Successful Processes: {successful_processes}")
    print(f"❌ Failed Processes: {len(website_files) - successful_processes}")
    print(f"🔗 Total URLs Processed: {total_urls_processed}")
    print(f"📁 Results saved in: {RECOMMENDATION_OUTPUT_DIR}/")
    
    if successful_processes > 0:
        avg_urls = total_urls_processed / successful_processes
        print(f"📈 Average URLs per Website: {avg_urls:.1f}")
    
    print("=" * 60)

# --- Execution ---
if __name__ == "__main__":
    if GEMINI_API_KEY == "YOUR_API_KEY_HERE":
        print("ERROR: Please set your Gemini API key in the script or as an environment variable (GEMINI_API_KEY).")
    else:
        process_websites()
