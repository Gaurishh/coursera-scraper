# Coursera Lead Generation Pipeline

## Project Overview

This project is an automated lead generation system designed to discover, analyze, and extract contact information from institutions (companies and schools) for Coursera course recommendations. The pipeline uses Google Places API for institution discovery, web crawling for content extraction, and Google's Gemini 2.5 Pro AI for intelligent analysis and classification.

The system is specifically optimized for finding leads for **Programming** and **Sales** courses, targeting institutions in Bangalore and Delhi. It processes institutions through a 6-stage pipeline that transforms raw institution data into actionable contact information for sales teams.

### Key Capabilities

- **Automated Institution Discovery**: Uses Google Places API to find relevant companies and schools
- **Intelligent Web Crawling**: Extracts and analyzes website content with multithreading
- **AI-Powered Classification**: Uses Gemini 2.5 Pro to classify institutions and recommend courses
- **Contact Information Extraction**: Identifies and extracts contact details from websites
- **Scalable Processing**: Multithreaded architecture for efficient processing of large datasets

### Target Markets

- **Programming Courses**: Software companies, engineering colleges, tech startups
- **Sales Courses**: Sales and marketing companies, business schools, corporate training departments

---

## File Overview

| File                                           | Purpose                                                     | Output                                                                     |
| ---------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------- |
| `1_institutions_list_fetcher.py`               | Discovers institutions using Google Places API              | `1_discovered_leads.csv` - Institution data with websites                  |
| `2_website_crawler.py`                         | Crawls websites to extract all available URLs               | `websites/` directory - Text files with website URLs                       |
| `3_top_5_urls_for_recommendation_extractor.py` | Selects top 5 URLs for course recommendation analysis       | `top_5_urls/` directory - Text files with selected URLs                    |
| `4_leads_classified_generator.py`              | Classifies institutions and recommends courses using AI     | `2_leads_classified.csv` - Classified leads with course recommendations    |
| `5_top_5_urls_for_contact_info_extractor.py`   | Selects top 5 URLs for contact information extraction       | `contact_urls/` directory - Text files with contact URLs                   |
| `6_final_data_gatherer.py`                     | Extracts contact information from selected URLs             | `contact_info/` directory - JSON files with contact details                |
| `7_final_output_generator.py`                  | Combines classified leads with contact data into final JSON | `output.json` - Complete lead data with sales recommendations and contacts |

---

## File Documentation

### 1_institutions_list_fetcher.py

**Overview**: This script serves as the entry point of the lead generation pipeline, using Google Places API to discover institutions (companies and schools) in specified cities. It performs targeted searches for Programming and Sales course leads, extracts detailed information including websites and contact details, and filters results to include only institutions with valid websites.

**Output**: Generates `1_discovered_leads.csv` containing Institution Name, Institution Type, Website, Location, and Phone fields for all discovered institutions with valid websites.

**Quick Workflow**:

1. **Search Execution**: Performs targeted Google Places API searches using predefined queries for corporates and schools in Bangalore and Delhi, handling pagination to retrieve comprehensive results.
2. **Data Enrichment**: For each discovered institution, fetches detailed information including website, phone number, and location using the Place Details API with rate limiting compliance.
3. **Filtering and Categorization**: Filters institutions to include only those with valid websites, categorizes locations based on keywords, and saves the final dataset to CSV format.

**Detailed Workflow/Algorithm**:

1. **Initialization and Configuration**

   - Loads API keys and configuration from constants
   - Sets up search parameters and rate limiting
   - Initializes data structures for tracking processed places

2. **Search Query Generation**

   - Defines institution-specific search queries:
     - Corporates: "Software companies in {city}", "Sales and marketing companies in {city}"
     - Schools: "Engineering colleges in {city}", "Business schools in {city}"
   - Formats queries with target cities (Bangalore, Delhi)

3. **Google Places Text Search Execution**

   - Iterates through each city and institution type combination
   - Executes text search API calls with proper error handling
   - Implements pagination support (up to 3 pages per query)
   - Applies rate limiting (100ms delay between requests)

4. **Place Details Retrieval**

   - For each discovered place, calls Place Details API
   - Extracts website, phone number, and formatted address
   - Validates website URLs for completeness and accessibility
   - Implements retry logic for failed API calls

5. **Data Processing and Validation**

   - Filters out institutions without valid websites
   - Categorizes locations using keyword matching (Bangalore vs Delhi)
   - Removes duplicate entries using place_id tracking
   - Validates and cleans extracted data

6. **Output Generation**
   - Compiles final dataset with required fields
   - Saves results to CSV with proper encoding
   - Provides execution summary and statistics

**Features/Functionalities**:

- **Targeted Institution Discovery**: Finds relevant companies and schools for specific course types
- **Geographic Focus**: Concentrates on high-potential markets (Bangalore, Delhi)
- **Website Validation**: Ensures all leads have accessible websites for further processing
- **Duplicate Prevention**: Eliminates duplicate institutions across different search queries
- **Rate Limit Compliance**: Respects Google Places API limits to prevent quota exhaustion
- **Comprehensive Data Extraction**: Captures essential contact and business information

---

### 2_website_crawler.py

**Overview**: This script performs comprehensive web crawling on discovered institution websites to extract all available URLs and routes. It uses an iterative crawling algorithm with connection pooling, domain failure tracking, and intelligent URL filtering to efficiently discover website structure while respecting server resources.

**Output**: Generates individual text files in `websites/` directory (e.g., `example.com.txt`) containing normalized URLs (without protocol/www prefixes) for each institution's website structure.

**Quick Workflow**:

1. **Website Processing**: Reads institution data from CSV and processes each website using multithreaded crawling with connection pooling and session management for optimal performance.
2. **URL Discovery and Filtering**: Implements iterative crawling to discover all website routes, filtering out external links, file downloads, and problematic URLs while maintaining domain focus.
3. **Result Storage and Retry Logic**: Saves discovered URLs to individual text files, implements retry mechanism for single-route websites, and provides comprehensive execution statistics.

**Detailed Workflow/Algorithm**:

1. **Initialization and Setup**

   - Loads configuration from constants (max workers, timeouts, limits)
   - Creates output directory structure
   - Initializes thread-safe domain blacklist for failure tracking
   - Sets up connection pooling with proper headers

2. **Multithreaded Processing Setup**

   - Reads institution data from input CSV
   - Creates ThreadPoolExecutor with configured worker count
   - Submits crawling tasks for parallel execution
   - Implements thread-safe progress tracking

3. **Individual Website Crawling**

   - **URL Normalization**: Converts URLs to consistent format for storage
   - **Domain Validation**: Ensures crawling stays within target domain
   - **Iterative Discovery**: Uses breadth-first search with URL queue
   - **Content Filtering**: Skips external links, file downloads, and blocked patterns

4. **Connection Management**

   - **Session Reuse**: Maintains persistent HTTP connections for efficiency
   - **Rate Limiting**: Implements delays between requests to be server-friendly
   - **Error Handling**: Tracks consecutive failures and implements exponential backoff
   - **Domain Blacklisting**: Stops crawling problematic domains across threads

5. **URL Processing and Storage**

   - **Normalization**: Removes protocol and www prefixes for consistent storage
   - **Deduplication**: Prevents duplicate URLs using normalized comparison
   - **File Generation**: Creates individual text files per domain
   - **Sorting**: Organizes URLs alphabetically for consistent output

6. **Retry Mechanism**
   - **Single Route Detection**: Identifies websites with only one discovered URL
   - **Retry Execution**: Re-attempts crawling for single-route websites
   - **Success Tracking**: Monitors improvement in route discovery
   - **Final Statistics**: Provides comprehensive execution summary

**Features/Functionalities**:

- **Comprehensive Website Mapping**: Discovers complete website structure and navigation
- **Efficient Resource Usage**: Uses connection pooling and session management for optimal performance
- **Intelligent Filtering**: Excludes irrelevant content while preserving important pages
- **Failure Recovery**: Implements retry logic for websites with limited initial discovery
- **Scalable Processing**: Multithreaded architecture for handling large institution datasets
- **Server-Friendly Crawling**: Respects rate limits and implements proper delays

---

### 3_top_5_urls_for_recommendation_extractor.py

**Overview**: This script intelligently selects the top 5 most relevant URLs from each institution's website for course recommendation analysis. It combines AI-powered selection using Gemini 2.5 Pro with deterministic fallback algorithms, prioritizes "about" pages, and validates URL accessibility to ensure high-quality content for classification.

**Output**: Generates individual text files in `top_5_urls/` directory (e.g., `example.com.txt`) containing exactly 5 validated URLs per institution, prioritized for course recommendation analysis.

**Quick Workflow**:

1. **URL Prioritization**: Automatically prioritizes "about" and "about-us" pages, then uses AI (Gemini 2.5 Pro) to select remaining URLs from the website's available routes based on relevance to course recommendations.
2. **Intelligent Selection**: Implements deterministic keyword-based scoring as fallback when AI is unavailable, using refined algorithms that consider keyword specificity, positional weighting, and negative keyword penalties.
3. **Validation and Storage**: Validates each selected URL for accessibility and content quality, replaces invalid URLs with alternatives from the prioritized queue, and saves the final 5 URLs to individual text files.

**Detailed Workflow/Algorithm**:

1. **Input Processing and Normalization**

   - Reads website URL files from crawling output
   - Normalizes URLs by adding https://www. prefix if missing
   - Validates file existence and content availability
   - Prepares URL lists for processing

2. **About Page Prioritization**

   - **Pattern Matching**: Identifies URLs containing '/about', '/about-us' patterns
   - **Priority Assignment**: Automatically includes about pages in final selection
   - **Separation**: Splits URLs into about and non-about categories
   - **Slot Management**: Reserves slots for about pages in final 5-URL selection

3. **AI-Powered URL Selection**

   - **Prompt Generation**: Creates detailed prompts for Gemini 2.5 Pro
   - **Context Provision**: Includes institution type and available URLs
   - **Response Processing**: Parses JSON responses and validates URL lists
   - **Error Handling**: Implements retry logic with exponential backoff

4. **Deterministic Fallback Algorithm**

   - **Keyword Scoring**: Uses predefined keyword scores for course relevance
   - **Tokenization**: Splits URLs by delimiters for accurate matching
   - **Max Score Logic**: Uses highest-value keyword, not sum of all keywords
   - **Positional Weighting**: Gives higher scores to keywords earlier in URL path
   - **Negative Keywords**: Applies penalties for irrelevant content

5. **URL Validation and Replacement**

   - **Accessibility Testing**: Validates each URL returns valid HTML content
   - **Content Quality Check**: Ensures minimum content length and proper formatting
   - **Replacement Logic**: Finds alternatives from prioritized queue for invalid URLs
   - **Consecutive Error Tracking**: Stops processing after maximum consecutive failures

6. **Output Generation and Storage**
   - **Final Selection**: Compiles exactly 5 validated URLs per institution
   - **File Creation**: Saves results to individual text files per domain
   - **Progress Tracking**: Provides detailed logging and success statistics
   - **Error Reporting**: Logs failures and provides comprehensive summaries

**Features/Functionalities**:

- **Intelligent URL Selection**: Uses AI to identify most relevant pages for course analysis
- **About Page Prioritization**: Ensures company information pages are always included
- **Robust Fallback System**: Maintains functionality even when AI services are unavailable
- **Content Validation**: Ensures selected URLs contain accessible, relevant content
- **Scalable Processing**: Multithreaded execution for efficient processing of large datasets
- **Quality Assurance**: Implements multiple validation layers to ensure output quality

---

### 4_leads_classified_generator.py

**Overview**: This script performs AI-powered classification of discovered institutions to determine the most suitable course type (Programming or Sales) and provides confidence scores with detailed reasoning. It uses Gemini 2.5 Pro to analyze website content from the top 5 selected URLs and generates comprehensive lead classifications with business context.

**Output**: Generates `2_leads_classified.csv` containing Website, Institution Type, Location, Phone, Course (recommended course type), Score (confidence 0-100), and Reasoning (detailed explanation) fields for each classified institution.

**Quick Workflow**:

1. **Content Analysis**: Reads the top 5 URLs for each institution, scrapes and formats the content, then sends it to Gemini 2.5 Pro for intelligent analysis of the institution's business focus and needs.
2. **AI Classification**: Uses detailed prompts to guide the AI in determining whether the institution would benefit more from Programming or Sales courses, generating confidence scores and detailed reasoning for each decision.
3. **Result Compilation**: Processes AI responses, extracts course recommendations and confidence scores, combines with original institution data, and saves comprehensive classifications to CSV format.

**Detailed Workflow/Algorithm**:

1. **Input Validation and Setup**

   - Validates existence of input CSV and URL files directory
   - Loads institution data and prepares processing queue
   - Initializes multithreaded processing with configured worker count
   - Sets up retry mechanisms and error handling

2. **Content Extraction and Preparation**

   - **File Resolution**: Locates corresponding URL files for each institution
   - **Content Scraping**: Downloads and parses HTML from top 5 URLs
   - **Text Processing**: Removes scripts, styles, and formatting for clean text
   - **Content Formatting**: Structures content with URL headers for context

3. **AI-Powered Analysis**

   - **Prompt Construction**: Creates detailed prompts with institution type and content
   - **API Communication**: Sends requests to Gemini 2.5 Pro with retry logic
   - **Response Processing**: Parses JSON responses and validates structure
   - **Error Recovery**: Implements exponential backoff for failed requests

4. **Data Processing and Validation**

   - **Response Parsing**: Extracts course recommendations, scores, and reasoning
   - **Data Validation**: Ensures required fields are present and properly formatted
   - **Score Normalization**: Validates confidence scores are within expected range
   - **Content Quality Check**: Verifies reasoning provides meaningful explanations

5. **Result Compilation and Enhancement**

   - **Data Integration**: Combines AI results with original institution data
   - **Field Mapping**: Maps all required output fields (Website, Type, Location, Phone, Course, Score, Reasoning)
   - **Data Enrichment**: Adds location and phone information from original leads
   - **Quality Assurance**: Validates completeness of all output records

6. **Output Generation and Statistics**
   - **CSV Creation**: Saves results to classified leads CSV file
   - **Progress Tracking**: Provides real-time processing updates
   - **Statistics Generation**: Calculates success rates and processing times
   - **Error Reporting**: Logs and reports any processing failures

**Features/Functionalities**:

- **Intelligent Course Recommendation**: Uses AI to determine optimal course type for each institution
- **Confidence Scoring**: Provides quantitative assessment of recommendation certainty
- **Detailed Reasoning**: Offers transparent explanations for each classification decision
- **Comprehensive Data Integration**: Combines AI insights with original institution information
- **Scalable Processing**: Multithreaded execution for efficient handling of large datasets
- **Quality Assurance**: Multiple validation layers ensure accurate and complete results

---

### 5_top_5_urls_for_contact_info_extractor.py

**Overview**: This script intelligently selects the top 5 most relevant URLs from each institution's website specifically for contact information extraction. It uses course-specific AI prompts (Programming vs Sales) with Gemini 2.5 Pro, prioritizes contact pages, and implements sophisticated fallback algorithms to ensure optimal contact discovery.

**Output**: Generates individual text files in `contact_urls/` directory (e.g., `example.com.txt`) containing exactly 5 validated URLs per institution, specifically selected for contact information extraction based on course type.

**Quick Workflow**:

1. **Course-Specific Processing**: Reads classified leads and processes each institution based on its recommended course type (Programming or Sales), using specialized AI prompts and keyword scoring algorithms tailored to each course category.
2. **Contact Page Prioritization**: Automatically identifies and prioritizes contact, contact-us, and related pages, then uses AI to select additional URLs that are most likely to contain relevant contact information for the specific course type.
3. **Validation and Storage**: Validates each selected URL for accessibility and content quality, implements intelligent replacement logic for invalid URLs, and saves the final 5 contact-focused URLs to individual text files with comprehensive error logging.

**Detailed Workflow/Algorithm**:

1. **Input Processing and Course Classification**

   - Reads classified leads CSV with course recommendations
   - Separates leads by course type (Programming vs Sales)
   - Loads corresponding website URL files for each institution
   - Prepares course-specific processing parameters

2. **Contact Page Identification and Prioritization**

   - **Pattern Matching**: Identifies URLs containing '/contact', '/contact-us' patterns
   - **Priority Assignment**: Automatically includes contact pages in final selection
   - **Course-Specific Filtering**: Applies different criteria based on course type
   - **Slot Management**: Reserves slots for contact pages in final 5-URL selection

3. **AI-Powered Course-Specific Selection**

   - **Prompt Selection**: Chooses appropriate prompt template based on course type
   - **Context Provision**: Includes course-specific context and available URLs
   - **Gemini 2.5 Pro Analysis**: Sends tailored prompts for Programming or Sales contexts
   - **Response Processing**: Parses JSON responses with course-specific validation

4. **Deterministic Fallback Algorithms**

   - **Programming Keywords**: Uses technical and development-focused keyword scoring
   - **Sales Keywords**: Uses business and marketing-focused keyword scoring
   - **Advanced Scoring**: Implements tokenization, positional weighting, and negative keywords
   - **Course-Specific Logic**: Applies different scoring criteria based on course type

5. **URL Validation and Intelligent Replacement**

   - **Accessibility Testing**: Validates each URL returns valid HTML content
   - **Content Quality Assessment**: Ensures minimum content length and proper formatting
   - **Replacement Queue Management**: Maintains prioritized queue for invalid URL replacement
   - **Consecutive Error Handling**: Implements smart stopping after maximum failures

6. **Error Logging and Output Generation**
   - **Comprehensive Logging**: Records all AI failures with detailed error information
   - **JSON Error Logs**: Maintains structured error logs for debugging and analysis
   - **Final Selection**: Compiles exactly 5 validated URLs per institution
   - **File Storage**: Saves results to individual text files with course-specific naming

**Features/Functionalities**:

- **Course-Specific Intelligence**: Uses different AI prompts and algorithms for Programming vs Sales courses
- **Contact Page Prioritization**: Ensures contact information pages are always included
- **Advanced Fallback Systems**: Maintains functionality with sophisticated keyword-based selection
- **Comprehensive Error Tracking**: Detailed logging of all AI failures for system improvement
- **Content Validation**: Ensures selected URLs contain accessible, relevant contact information
- **Scalable Processing**: Multithreaded execution optimized for large lead datasets

---

### 6_final_data_gatherer.py

**Overview**: This script performs the final step of the lead generation pipeline by extracting detailed contact information from the selected URLs. It uses Gemini 2.5 Pro to analyze website content and identify specific contact details including names, emails, phone numbers, and job titles, saving the results in structured JSON format.

**Output**: Generates individual JSON files in `contact_info/` directory (e.g., `example.com.json`) containing structured contact information arrays with detailed contact records for each institution.

**Quick Workflow**:

1. **Contact URL Processing**: Reads the top 5 contact-focused URLs for each classified lead, scrapes and formats the content from these pages, and prepares comprehensive content for AI analysis of contact information.
2. **AI Contact Extraction**: Uses Gemini 2.5 Pro with specialized prompts to analyze website content and identify specific contact details including names, email addresses, phone numbers, job titles, and departments.
3. **Structured Data Storage**: Processes AI responses to extract contact arrays, validates and structures the contact information, and saves detailed contact records to individual JSON files for each institution.

**Detailed Workflow/Algorithm**:

1. **Input Validation and Setup**

   - Validates existence of classified leads CSV and contact URLs directory
   - Creates output directory structure for contact data
   - Loads lead data and prepares processing queue
   - Initializes multithreaded processing with error handling

2. **Contact URL Content Extraction**

   - **File Resolution**: Locates corresponding contact URL files for each lead
   - **Content Scraping**: Downloads and parses HTML from top 5 contact-focused URLs
   - **Text Processing**: Removes scripts, styles, and formatting for clean analysis
   - **Content Structuring**: Organizes content with URL context for AI processing

3. **AI-Powered Contact Extraction**

   - **Prompt Construction**: Creates detailed prompts for contact information extraction
   - **API Communication**: Sends content to Gemini 2.5 Pro with retry mechanisms
   - **Response Processing**: Parses JSON responses containing contact arrays
   - **Data Validation**: Ensures contact records contain required fields

4. **Contact Data Processing and Validation**

   - **Contact Parsing**: Extracts individual contact records from AI response
   - **Field Validation**: Ensures each contact has name, email, and role information
   - **Data Cleaning**: Removes duplicates and validates contact information format
   - **Quality Assessment**: Filters out incomplete or invalid contact records

5. **Structured Output Generation**

   - **JSON Structure**: Creates standardized contact record format
   - **File Naming**: Generates domain-based filenames for easy identification
   - **Data Serialization**: Saves contact arrays with proper JSON formatting
   - **Encoding Handling**: Ensures proper UTF-8 encoding for international characters

6. **Statistics and Reporting**
   - **Progress Tracking**: Provides real-time processing updates
   - **Contact Counting**: Tracks total contacts extracted per institution
   - **Success Metrics**: Calculates processing success rates and averages
   - **Execution Summary**: Provides comprehensive completion statistics

**Features/Functionalities**:

- **Intelligent Contact Discovery**: Uses AI to identify and extract specific contact information from website content
- **Structured Data Output**: Provides standardized JSON format for easy integration with CRM systems
- **Comprehensive Contact Details**: Extracts names, emails, phone numbers, job titles, and departments
- **Quality Validation**: Ensures extracted contacts meet minimum quality standards
- **Scalable Processing**: Multithreaded execution for efficient handling of large lead datasets
- **Integration Ready**: Output format designed for direct import into sales and marketing tools

---

### 7_final_output_generator.py

**Overview**: This script serves as the final step in the lead generation pipeline, combining classified leads data with extracted contact information to create a comprehensive JSON output file. It processes all records from the classified leads CSV, matches them with corresponding contact data files, and structures the information into a sales-ready format with recommendations and contact details.

**Output**: Generates individual JSON files in `output/` directory (e.g., `example.com.json`) containing structured lead data with website URLs, sales recommendations (course type, confidence score, reasoning), and comprehensive contact details (general contacts, key personnel, and other contacts) for each institution.

**Quick Workflow**:

1. **Data Integration**: Reads classified leads from CSV and matches each lead with its corresponding contact data JSON file based on domain name, processing all available leads systematically.
2. **Contact Processing**: Structures raw contact data into organized categories (general contacts, key personnel, other contacts), cleaning and validating contact information for sales team consumption.
3. **Individual File Generation**: Creates individual JSON files for each website with complete lead information including sales recommendations and structured contact details, providing detailed statistics and coverage metrics.

**Detailed Workflow/Algorithm**:

1. **Input Validation and Setup**

   - Validates existence of classified leads CSV and contact data directory
   - Loads classified leads data using pandas for efficient processing
   - Initializes tracking variables for statistics and error handling
   - Sets up progress monitoring for large datasets

2. **Lead Processing Loop**

   - **Domain Extraction**: Extracts domain names from website URLs for contact file matching
   - **File Resolution**: Locates corresponding contact data JSON files for each lead
   - **Data Loading**: Reads and parses contact data from JSON files with error handling
   - **Progress Tracking**: Provides real-time updates on processing status

3. **Contact Data Processing**

   - **Data Validation**: Ensures contact data is properly formatted and non-empty
   - **Contact Categorization**: Separates contacts into key personnel and general contacts
   - **Information Extraction**: Extracts names, titles, emails, and phone numbers
   - **Structure Creation**: Organizes contacts into hierarchical structure

4. **Lead Entry Creation**

   - **Sales Recommendation**: Structures course recommendations with confidence scores and reasoning
   - **Contact Integration**: Combines structured contact data with lead information
   - **Data Validation**: Ensures all required fields are present and properly formatted
   - **Quality Assurance**: Validates data completeness and consistency

5. **Individual File Generation and Statistics**

   - **JSON Serialization**: Creates properly formatted JSON output with UTF-8 encoding for each website
   - **File Writing**: Saves individual files to output directory with error handling
   - **Statistics Calculation**: Computes coverage metrics and processing statistics
   - **Summary Reporting**: Provides comprehensive execution summary

6. **Error Handling and Logging**
   - **Missing Data Handling**: Gracefully handles leads without contact data
   - **File Error Recovery**: Continues processing despite individual file errors
   - **Progress Monitoring**: Tracks successful and failed processing attempts
   - **Detailed Logging**: Provides informative messages for debugging and monitoring

**Features/Functionalities**:

- **Individual File Generation**: Creates separate JSON files for each website for easy management and processing
- **Sales-Ready Output**: Structures data specifically for sales team consumption with clear recommendations
- **Contact Organization**: Categorizes contacts into key personnel and general inquiries for targeted outreach
- **Quality Metrics**: Provides coverage statistics and data quality assessments
- **Error Resilience**: Continues processing despite missing or corrupted contact data files
- **Structured Output**: Creates standardized JSON format for easy integration with CRM systems

---

## Configuration

The project uses a centralized `constants.py` file for all configuration parameters including:

- **API Keys**: Google Places API and Gemini API configuration
- **Processing Limits**: Worker counts, timeouts, and retry limits
- **File Paths**: Input/output directories and file naming conventions
- **Search Parameters**: Cities, institution types, and search queries
- **AI Prompts**: Detailed prompt templates for different analysis tasks

## Dependencies

- **Google Places API**: For institution discovery and details
- **Google Gemini 2.5 Pro**: For AI-powered analysis and classification
- **Python Libraries**: requests, beautifulsoup4, pandas, concurrent.futures
- **Web Scraping**: BeautifulSoup for HTML parsing and content extraction

## Usage

1. Configure API keys in `constants.py` or environment variables
2. Run scripts in sequence: `1_institutions_list_fetcher.py` → `2_website_crawler.py` → `3_top_5_urls_for_recommendation_extractor.py` → `4_leads_classified_generator.py` → `5_top_5_urls_for_contact_info_extractor.py` → `6_final_data_gatherer.py` → `7_final_output_generator.py`
3. Monitor output directories for generated files and processing results
4. Review individual files in `output/` directory for sales team integration

## Output Structure

```
project/
├── 1_discovered_leads.csv          # Initial institution discovery
├── 2_leads_classified.csv          # AI-classified leads with course recommendations
├── output/                         # Individual JSON files for each website
├── websites/                       # Website crawling results
├── top_5_urls_for_recommendation/  # URLs selected for course analysis
├── top_5_urls_for_contact_info/    # URLs selected for contact extraction
└── contact_info/                   # Contact information in JSON format
```
