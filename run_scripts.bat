@echo off
rem run_scripts.bat

echo "Starting the script sequence..."

python 1_institutions_list_fetcher.py
python 2_website_crawler.py
python 3_top_5_urls_for_recommendation_extractor.py
python 4_leads_classified_generator.py
python 5_top_5_urls_for_contact_info_extractor.py
python 6_final_data_gatherer.py
python 7_final_output_generator.py

echo "Script sequence finished."