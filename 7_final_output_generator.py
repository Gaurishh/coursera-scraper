#!/usr/bin/env python3
"""
7_final_output_generator.py

Final step of the Coursera Lead Generation Pipeline.
Combines classified leads data with extracted contact information to create individual JSON files for each website.

This script:
1. Reads all records from 2_leads_classified.csv
2. Finds corresponding JSON files in contact_info directory
3. Creates individual JSON files in output/ directory with sales recommendations and contact details

Output Format (each file contains an array with one entry):
[
  {
    "website": "https://example.com/",
    "salesRecommendation": {
      "recommendedCourse": "Programming",
      "confidenceScore": 98,
      "reasoning": "Detailed reasoning for the recommendation"
    },
    "contactDetails": {
      "general": {
        "email": "contact@example.com",
        "phone": "+1234567890"
      },
      "keyPersonnel": [
        {
          "name": "John Doe",
          "title": "CTO",
          "email": "john@example.com",
          "phone": "+1234567890"
        }
      ],
      "otherContacts": [
        {
          "description": "General Inquiry",
          "email": "info@example.com",
          "phone": "+1234567890"
        }
      ]
    }
  }
]
"""

import os
import json
import csv
import re
from urllib.parse import urlparse
from typing import Dict, List, Any, Optional

# Import constants
from constants import (
    CLASSIFICATION_OUTPUT_FILE, FINAL_GATHERER_OUTPUT_DIR
)

def get_domain_from_url(url: str) -> str:
    """
    Extract domain from URL for filename generation.
    
    Args:
        url (str): Full URL
        
    Returns:
        str: Domain name without protocol and www
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '')
        return domain
    except Exception:
        # Fallback: extract domain manually
        url = url.replace('http://', '').replace('https://', '').replace('www.', '')
        return url.split('/')[0]

def load_contact_data(domain: str, contact_dir: str) -> Optional[List[Dict]]:
    """
    Load contact data from JSON file for a given domain.
    
    Args:
        domain (str): Domain name
        contact_dir (str): Directory containing contact JSON files
        
    Returns:
        Optional[List[Dict]]: Contact data or None if file not found/error
    """
    contact_file = os.path.join(contact_dir, f"{domain}.json")
    
    if not os.path.exists(contact_file):
        return None
    
    try:
        with open(contact_file, 'r', encoding='utf-8') as f:
            contact_data = json.load(f)
        return contact_data
    except (json.JSONDecodeError, FileNotFoundError, Exception) as e:
        print(f"⚠️  Error loading contact data for {domain}: {e}")
        return None

def categorize_contacts(contact_data: List[Dict]) -> Dict[str, Any]:
    """
    Categorize contacts into general, key personnel, and other contacts.
    
    Args:
        contact_data (List[Dict]): Raw contact data from JSON file
        
    Returns:
        Dict[str, Any]: Categorized contact information
    """
    general_contacts = {}
    key_personnel = []
    other_contacts = []
    
    # Keywords that indicate key personnel
    key_personnel_keywords = [
        'cto', 'ceo', 'founder', 'director', 'manager', 'head', 'lead', 'vp', 'vice president',
        'president', 'chief', 'coordinator', 'supervisor', 'principal', 'dean', 'hod'
    ]
    
    for contact in contact_data:
        if not isinstance(contact, dict):
            continue
            
        # Extract contact information
        name = (contact.get('name') or '').strip()
        title = (contact.get('title') or '').strip()
        email = (contact.get('email') or '').strip()
        phone = (contact.get('phone') or '').strip()
        
        # Skip if no meaningful information
        if not any([name, title, email, phone]):
            continue
        
        # Determine if this is key personnel based on title
        is_key_personnel = False
        if title:
            title_lower = title.lower()
            is_key_personnel = any(keyword in title_lower for keyword in key_personnel_keywords)
        
        # If it has a name and title, it's likely key personnel
        if name and title and is_key_personnel:
            key_personnel.append({
                "name": name,
                "title": title,
                "email": email if email else None,
                "phone": phone if phone else None
            })
        elif name and title:
            # Has name and title but not key personnel keywords
            other_contacts.append({
                "description": f"{name} - {title}",
                "email": email if email else None,
                "phone": phone if phone else None
            })
        elif email or phone:
            # General contact information
            if email and not general_contacts.get('email'):
                general_contacts['email'] = email
            if phone and not general_contacts.get('phone'):
                general_contacts['phone'] = phone
        elif title and (email or phone):
            # Contact with title but no name
            other_contacts.append({
                "description": title,
                "email": email if email else None,
                "phone": phone if phone else None
            })
    
    return {
        "general": general_contacts if general_contacts else {},
        "keyPersonnel": key_personnel,
        "otherContacts": other_contacts
    }

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
    
    # Create output directory
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"📁 Created output directory: {output_dir}")
    
    print("🚀 Starting Final Output Generator")
    print("=" * 60)
    print(f"📁 Reading classified leads from: {CLASSIFICATION_OUTPUT_FILE}")
    print(f"📁 Reading contact data from: {FINAL_GATHERER_OUTPUT_DIR}")
    print(f"📁 Writing individual files to: {output_dir}/")
    print("=" * 60)
    
    # Read classified leads
    leads = []
    try:
        with open(CLASSIFICATION_OUTPUT_FILE, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if 'Website' in row and row['Website'].strip():
                    leads.append({
                        'Website': row['Website'].strip(),
                        'Institution Type': row.get('Institution Type', '').strip(),
                        'Location': row.get('Location', '').strip(),
                        'Phone': row.get('Phone', '').strip(),
                        'Course': row.get('Course', '').strip(),
                        'Score': row.get('Score', '').strip(),
                        'Reasoning': row.get('Reasoning', '').strip()
                    })
    except Exception as e:
        print(f"❌ ERROR: Could not read classified leads file. Error: {e}")
        return
    
    if not leads:
        print(f"❌ No valid leads found in '{CLASSIFICATION_OUTPUT_FILE}'.")
        return
    
    print(f"📊 Processing {len(leads)} classified leads...")
    
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
            # Still include the lead but with empty contact details
            contact_details = {
                "general": {},
                "keyPersonnel": [],
                "otherContacts": []
            }
        else:
            print(f"  ✅ Found contact data for {domain}")
            contact_data_found += 1
            contact_details = categorize_contacts(contact_data)
        
        # Create lead entry
        lead_entry = {
            "website": website,
            "salesRecommendation": {
                "recommendedCourse": lead['Course'],
                "confidenceScore": int(lead['Score']) if lead['Score'].isdigit() else 0,
                "reasoning": lead['Reasoning']
            },
            "contactDetails": contact_details
        }
        
        # Write individual JSON file
        output_filename = f"{domain}.json"
        output_filepath = os.path.join(output_dir, output_filename)
        
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                json.dump([lead_entry], f, indent=2, ensure_ascii=False)
            print(f"  💾 Saved: {output_filename}")
        except Exception as e:
            print(f"  ❌ Error saving {output_filename}: {e}")
            continue
        
        processed_count += 1
    
    # Display final statistics
    print("\n" + "=" * 60)
    print("🎉 INDIVIDUAL OUTPUT FILES GENERATION COMPLETE!")
    print("=" * 60)
    print(f"📊 Total Leads Processed: {processed_count}")
    print(f"✅ Leads with Contact Data: {contact_data_found}")
    print(f"⚠️  Leads without Contact Data: {contact_data_missing}")
    print(f"📁 Individual files saved to: {output_dir}/")
    
    if contact_data_found > 0:
        coverage_percentage = (contact_data_found / processed_count) * 100
        print(f"📈 Contact Data Coverage: {coverage_percentage:.1f}%")
    
    # Count by course type
    programming_count = sum(1 for lead in leads if lead['Course'].lower() == 'programming')
    sales_count = sum(1 for lead in leads if lead['Course'].lower() == 'sales')
    print(f"💻 Programming Course Leads: {programming_count}")
    print(f"💼 Sales Course Leads: {sales_count}")
    
    # Calculate average confidence score
    total_score = sum(int(lead['Score']) if lead['Score'].isdigit() else 0 for lead in leads)
    avg_confidence = total_score / len(leads) if leads else 0
    print(f"📊 Average Confidence Score: {avg_confidence:.1f}")
    
    print("=" * 60)

if __name__ == "__main__":
    process_leads()