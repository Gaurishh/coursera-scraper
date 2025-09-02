import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import csv
import os
import time
import re

def extract_company_name_from_url(url):
    """
    Extract a clean company name from URL for filename.
    
    Args:
        url (str): The website URL
        
    Returns:
        str: Clean company name for filename
    """
    # Remove protocol and www
    domain = urlparse(url).netloc
    domain = domain.replace('www.', '').replace('https://', '').replace('http://', '')
    
    # Remove common TLDs and get the main part
    domain_parts = domain.split('.')
    if len(domain_parts) > 1:
        main_name = domain_parts[0]
    else:
        main_name = domain
    
    # Clean up the name for filename
    main_name = re.sub(r'[^a-zA-Z0-9]', '', main_name)
    return main_name.lower()

def get_page_content(url):
    """
    Get the text content from a webpage by extracting text from HTML.
    This function is kept for backward compatibility but is no longer used
    in the main crawling logic to avoid duplicate HTTP requests.
    
    Args:
        url (str): The URL to fetch content from
        
    Returns:
        str: Extracted text content of the page
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Parse HTML and extract text content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Clean up the text
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text
        
    except Exception as e:
        return f"Error fetching content: {str(e)}"

def crawl_website_for_content(start_url, max_pages=20):
    """
    Crawl a website and discover all internal routes/URLs.
    
    Args:
        start_url (str): The URL of the website to start crawling from
        max_pages (int): Maximum number of pages to crawl (not used for route discovery)
        
    Returns:
        list: List of all discovered internal URLs
    """
    visited_urls = set()
    
    # Ensure we start with a clean root URL (no path)
    parsed_start = urlparse(start_url)
    base_netloc = parsed_start.netloc
    # Normalize domain by removing www. prefix for comparison
    base_domain = base_netloc.replace('www.', '') if base_netloc.startswith('www.') else base_netloc
    # Create clean root URL without any path
    base_url = f"{parsed_start.scheme}://{base_netloc}"
    
    # Start crawling from the root URL, not the original start_url
    urls_to_visit = [base_url]
    all_discovered_urls = set()  # Store all discovered URLs
    
    # Safety limit to prevent infinite loops
    MAX_URLS = 1000  # Maximum number of URLs to discover per website
    
    import pdb;pdb.set_trace()
    
    print(f"Original URL: {start_url}")
    print(f"Starting crawl at root: {base_url}")
    print(f"Base domain: {base_netloc} (normalized: {base_domain})")
    print(f"Discovering internal routes (max {MAX_URLS} URLs)...")

    # Remove page limit for route discovery - crawl until no more links found or safety limit reached
    while urls_to_visit and len(all_discovered_urls) < MAX_URLS:
        current_url = urls_to_visit.pop(0)

        if current_url in visited_urls:
            continue

        try:
            # Get the response for link discovery
            response = requests.get(current_url, timeout=10)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Mark as visited and add to discovered URLs
            visited_urls.add(current_url)
            all_discovered_urls.add(current_url)
            
            print(f"Discovered: {current_url} (Total routes found: {len(all_discovered_urls)})")
            
            # Commented out: Original functionality for extracting and storing text content
            # # Remove script and style elements
            # for script in soup(["script", "style"]):
            #     script.decompose()
            # 
            # # Get text content
            # text = soup.get_text()
            # 
            # # Clean up the text
            # lines = (line.strip() for line in text.splitlines())
            # chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            # content = ' '.join(chunk for chunk in chunks if chunk)
            # 
            # # Extract the route path
            # parsed_url = urlparse(current_url)
            # route_path = parsed_url.path if parsed_url.path else "/"
            # 
            # # Store the content
            # page_contents[route_path] = content

            # Find new links to crawl (no page limit for route discovery)
            try:
                links_found = 0
                links_added = 0
                links_skipped = 0
                
                for link in soup.find_all('a'):
                    href = link.get('href')
                    if not href:
                        continue
                    
                    links_found += 1
                    absolute_url = urljoin(current_url, href)
                    parsed_url = urlparse(absolute_url)

                    # Skip URLs with file extensions (any file with a dot extension)
                    path = parsed_url.path.lower()
                    # Check if path ends with a dot followed by 1-10 characters (file extension)
                    has_file_extension = bool(re.search(r'\.[a-z0-9]{1,10}$', path))
                    
                    # Skip files with extensions
                    if has_file_extension:
                        links_skipped += 1
                        print(f"INFO: Skipping file with extension: {absolute_url}")
                        continue
                    
                    # Skip problematic URLs that can cause infinite loops
                    if any(skip_pattern in absolute_url.lower() for skip_pattern in [
                        'cdn-cgi/l/email-protection',
                        'javascript:',
                        'mailto:',
                        'tel:',
                        '#',
                        '?utm_',
                        '?ref=',
                        '?source='
                    ]):
                        links_skipped += 1
                        print(f"INFO: Skipping problematic URL: {absolute_url}")
                        continue
                    
                    # Normalize the current URL's domain for comparison
                    current_domain = parsed_url.netloc.replace('www.', '') if parsed_url.netloc.startswith('www.') else parsed_url.netloc
                    
                    # Check if it's a valid internal URL to add to queue (no page limit)
                    if (parsed_url.scheme in ['http', 'https'] and
                            current_domain == base_domain and
                            absolute_url not in visited_urls and
                            absolute_url not in urls_to_visit):
                        
                        urls_to_visit.append(absolute_url)
                        links_added += 1
                        print(f"DEBUG: Added to queue: {absolute_url}")
                    else:
                        # Debug why URL was not added
                        if parsed_url.scheme not in ['http', 'https']:
                            print(f"DEBUG: Skipped non-HTTP URL: {absolute_url}")
                        elif current_domain != base_domain:
                            print(f"DEBUG: Skipped external URL: {absolute_url} (domain: {current_domain} != base: {base_domain})")
                        elif absolute_url in visited_urls:
                            print(f"DEBUG: Skipped already visited: {absolute_url}")
                        elif absolute_url in urls_to_visit:
                            print(f"DEBUG: Skipped already queued: {absolute_url}")
                        # Commented out: Page limit check (not used for route discovery)
                        # elif len(visited_urls) >= max_pages:
                        #     print(f"DEBUG: Skipped - max pages reached: {absolute_url}")
                
                print(f"DEBUG: Found {links_found} links, added {links_added} to queue, skipped {links_skipped} files")
                        
            except Exception as e:
                print(f"Error processing links for {current_url}: {e}")

        except requests.RequestException as e:
            print(f"Could not request {current_url}. Error: {e}")
        except Exception as e:
            print(f"An error occurred while processing {current_url}. Error: {e}")

    print(f"\n--- Route Discovery Complete for {base_url} ---")
    print(f"Total unique routes discovered: {len(all_discovered_urls)}")
    
    # Safety check - if we hit the limit, warn the user
    if len(all_discovered_urls) >= MAX_URLS:
        print(f"⚠️  WARNING: Hit maximum URL limit ({MAX_URLS}). There may be more routes on this website.")
    
    return list(all_discovered_urls)

def save_website_routes(company_name, discovered_routes, output_dir="websites"):
    """
    Save the discovered website routes to a text file.
    
    Args:
        company_name (str): Name of the company for filename
        discovered_routes (list): List of discovered URLs
        output_dir (str): Directory to save the file
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Create filename
    filename = f"{company_name}.txt"
    filepath = os.path.join(output_dir, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            for route in sorted(discovered_routes):
                f.write(f"{route}\n")
        
        print(f"✅ Saved {len(discovered_routes)} routes to: {filepath}")
        return True
        
    except Exception as e:
        print(f"❌ Error saving routes to {filepath}: {e}")
        return False

# Commented out: Original functionality for saving text content
# def save_website_content(company_name, page_contents, output_dir="websites"):
#     """
#     Save the crawled website text content to a text file.
#     
#     Args:
#         company_name (str): Name of the company for filename
#         page_contents (dict): Dictionary with route paths and text content
#         output_dir (str): Directory to save the file
#     """
#     # Create output directory if it doesn't exist
#     os.makedirs(output_dir, exist_ok=True)
#     
#     # Create filename
#     filename = f"{company_name}.txt"
#     filepath = os.path.join(output_dir, filename)
#     
#     try:
#         with open(filepath, 'w', encoding='utf-8') as f:
#             f.write(f"Website Text Content for {company_name}\n")
#             f.write("=" * 50 + "\n\n")
#             
#             for route, text_content in page_contents.items():
#                 f.write(f"{route} route:\n")
#                 f.write("-" * 30 + "\n")
#                 f.write(f"{text_content}\n\n")
#                 f.write("=" * 50 + "\n\n")
#         
#         print(f"✅ Saved text content to: {filepath}")
#         return True
#         
#     except Exception as e:
#         print(f"❌ Error saving content to {filepath}: {e}")
#         return False

def crawl_single_website(website_url, company_name, clean_name, max_pages_per_site):
    """
    Crawl a single website to discover all routes.
    
    Args:
        website_url (str): The website URL to crawl
        company_name (str): The company name
        clean_name (str): Clean name for filename
        max_pages_per_site (int): Not used for route discovery (kept for compatibility)
        
    Returns:
        tuple: (success, clean_name, routes_discovered)
    """
    try:
        print(f"\n📊 Processing: {company_name}")
        print(f"🌐 Website: {website_url}")
        
        # Discover all routes on the website
        print(f"🕷️  Starting route discovery for {clean_name}...")
        discovered_routes = crawl_website_for_content(website_url, max_pages_per_site)
        
        if discovered_routes:
            # Save the routes
            success = save_website_routes(clean_name, discovered_routes)
            if success:
                print(f"✅ Successfully discovered {len(discovered_routes)} routes for {clean_name}")
                return (True, clean_name, len(discovered_routes))
            else:
                print(f"❌ Failed to save routes for {clean_name}")
                return (False, clean_name, 0)
        else:
            print(f"❌ No routes found for {clean_name}")
            return (False, clean_name, 0)
            
    except Exception as e:
        print(f"❌ Error discovering routes for {clean_name}: {e}")
        return (False, clean_name, 0)

def read_csv_and_crawl_websites(csv_file="discovered_leads.csv", max_pages_per_site=20):
    """
    Read the CSV file and discover all routes for websites that have valid URLs sequentially.
    Saves the discovered routes to text files.
    
    Args:
        csv_file (str): Path to the CSV file
        max_pages_per_site (int): Not used for route discovery (kept for compatibility)
    """
    if not os.path.exists(csv_file):
        print(f"❌ CSV file not found: {csv_file}")
        return
    
    crawled_count = 0
    processed_count = 0
    
    print("🚀 Starting Sequential Website Route Discovery for All Coursera Leads")
    print("=" * 60)
    
    # Read and process websites sequentially
    try:
        with open(csv_file, 'r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            
            for row in csv_reader:
                website_url = row.get('Website', '').strip()
                company_name = row.get('Institution Name', '').strip()
                
                # Skip if no website or website is N/A
                if not website_url or website_url.lower() == 'n/a':
                    continue
                
                # Extract company name from URL for filename
                clean_name = extract_company_name_from_url(website_url)
                processed_count += 1
                
                # Discover routes for the website
                success, clean_name, routes_discovered = crawl_single_website(
                    website_url, company_name, clean_name, max_pages_per_site
                )
                
                if success:
                    crawled_count += 1
                    print(f"✅ Completed: {clean_name} ({routes_discovered} routes)")
                else:
                    print(f"❌ Failed: {clean_name}")
    
    except Exception as e:
        print(f"❌ Error reading CSV file: {e}")
        return
    
    print("\n" + "=" * 60)
    print("🎉 ROUTE DISCOVERY COMPLETE!")
    print("=" * 60)
    print(f"📈 Total websites processed: {processed_count}")
    print(f"✅ Successfully discovered routes for: {crawled_count}")
    print(f"📁 Routes saved in: websites/ folder")

# --- Main Execution ---
if __name__ == "__main__":
    # Start timing
    start_time = time.time()
    
    # Discover all routes for websites from the CSV sequentially
    read_csv_and_crawl_websites(
        csv_file="discovered_leads.csv",
        max_pages_per_site=10  # Not used for route discovery
    )
    
    # Calculate and display total execution time
    end_time = time.time()
    total_time = end_time - start_time
    
    print("\n" + "=" * 60)
    print("⏱️  EXECUTION SUMMARY")
    print("=" * 60)
    
    # Format time display
    if total_time < 60:
        print(f"⏰ Total execution time: {total_time:.2f} seconds")
    elif total_time < 3600:
        minutes = int(total_time // 60)
        seconds = total_time % 60
        print(f"⏰ Total execution time: {minutes} minutes {seconds:.2f} seconds")
    else:
        hours = int(total_time // 3600)
        minutes = int((total_time % 3600) // 60)
        seconds = total_time % 60
        print(f"⏰ Total execution time: {hours} hours {minutes} minutes {seconds:.2f} seconds")
    
    print("✅ Website route discovery completed successfully!")
    print("=" * 60)
