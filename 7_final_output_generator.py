#!/usr/bin/env python3
"""
7_final_output_generator.py

Final step of the Coursera Lead Generation Pipeline.
Combines classified leads data with extracted contact information to create individual JSON files for each website.

This script:
1. Reads all records from 2_leads_classified.csv
2. Finds corresponding JSON files in contact_info directory
3. Creates individual JSON files for each website with all CSV data and contact details

Output Format:
{
  "Website": "www.example.com/",
  "Institution Type": "Corporates",
  "Location": "Bangalore",
  "Phone": "08012345678",
  "Course": "Programming",
  "Score": 98,
  "Reasoning": "Detailed reasoning for the recommendation",
  "extracted_contact_details": [
    {
      "name": "John Doe",
      "phone": "+1234567890",
      "email": "john@example.com"
    }
  ]
}
"""

import os
import json
import csv
import re
from urllib.parse import urlparse
from constants import CLASSIFICATION_OUTPUT_FILE, FINAL_GATHERER_OUTPUT_DIR

def get_domain_from_url(url):
    """
    Extract domain from URL for file matching.
    
    Args:
        url (str): Website URL
        
    Returns:
        str: Domain name
    """
    try:
        # Remove protocol if present
        if url.startswith(('http://', 'https://')):
            url = url.split('://', 1)[1]
        
        # Remove www. if present
        if url.startswith('www.'):
            url = url[4:]
        
        # Remove trailing slash and path
        domain = url.split('/')[0]
        
        return domain
    except Exception as e:
        print(f"  ⚠️  Error extracting domain from {url}: {e}")
        return url

def load_contact_data(domain, contact_dir):
    """
    Load contact data for a specific domain.
    
    Args:
        domain (str): Domain name
        contact_dir (str): Directory containing contact JSON files
        
    Returns:
        list: Contact data or None if not found
    """
    contact_file = os.path.join(contact_dir, f"{domain}.json")
    
    if not os.path.exists(contact_file):
        return None
    
    try:
        with open(contact_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️  Error loading contact data for {domain}: {e}")
        return None

def process_leads():
    """
    Main function to process leads and generate individual output JSON files.
    """
    # Validate input files
    if not os.path.exists(CLASSIFICATION_OUTPUT_FILE):
        print(f"❌ ERROR: Classified leads file '{CLASSIFICATION_OUTPUT_FILE}' not found.")
        return
    
    if not os.path.exists(FINAL_GATHERER_OUTPUT_DIR):
        print(f"❌ ERROR: Contact data directory '{FINAL_GATHERER_OUTPUT_DIR}' not found.")
        return
    
    print("🚀 Starting Final Output Generator")
    print("=" * 60)
    print(f"📁 Reading classified leads from: {CLASSIFICATION_OUTPUT_FILE}")
    print(f"📁 Reading contact data from: {FINAL_GATHERER_OUTPUT_DIR}")
    print("=" * 60)
    
    # Read classified leads
    leads = []
    try:
        with open(CLASSIFICATION_OUTPUT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            leads = list(reader)
        print(f"✅ Successfully loaded {len(leads)} classified leads")
    except Exception as e:
        print(f"❌ ERROR: Failed to read classified leads: {e}")
        return
    
    # Create output directory
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"📁 Created output directory: {output_dir}")
    
    # Process each lead
    processed_count = 0
    contact_data_found = 0
    contact_data_missing = 0
    
    for i, lead in enumerate(leads, 1):
        website = lead['Website']
        domain = get_domain_from_url(website)
        
        print(f"📝 [{i}/{len(leads)}] Processing: {website}")
        
        # Load contact data
        contact_data = load_contact_data(domain, FINAL_GATHERER_OUTPUT_DIR)
        
        if contact_data is None:
            print(f"  ⚠️  No contact data found for {domain}")
            contact_data_missing += 1
            # Use empty list for contacts
            extracted_contact_details = []
        else:
            print(f"  ✅ Found {len(contact_data)} contacts for {domain}")
            contact_data_found += 1
            extracted_contact_details = contact_data
        
        # Create output data structure
        output_data = {
            "Website": lead['Website'],
            "Institution Type": lead['Institution Type'],
            "Location": lead['Location'],
            "Phone": lead['Phone'],
            "Course": lead['Course'],
            "Score": int(lead['Score']),
            "Reasoning": lead['Reasoning'],
            "extracted_contact_details": extracted_contact_details
        }
        
        # Save individual JSON file
        output_file = os.path.join(output_dir, f"{domain}.json")
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            print(f"  💾 Saved: {output_file}")
            processed_count += 1
        except Exception as e:
            print(f"  ❌ Error saving {output_file}: {e}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("🎉 FINAL OUTPUT GENERATION COMPLETE!")
    print("=" * 60)
    print(f"📊 Total Leads Processed: {processed_count}")
    print(f"✅ Leads with Contact Data: {contact_data_found}")
    print(f"⚠️  Leads without Contact Data: {contact_data_missing}")
    print(f"📁 Output saved to: {output_dir}/")
    
    if contact_data_found > 0:
        coverage_percentage = (contact_data_found / processed_count) * 100
        print(f"📈 Contact Data Coverage: {coverage_percentage:.1f}%")
    
    # Calculate average confidence score
    total_score = sum(int(lead['Score']) for lead in leads)
    avg_score = total_score / len(leads) if leads else 0
    print(f"📊 Average Confidence Score: {avg_score:.1f}")
    
    print("=" * 60)

if __name__ == "__main__":
    process_leads()