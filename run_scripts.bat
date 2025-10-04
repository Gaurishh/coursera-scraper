@echo off
rem run_scripts.bat

echo "Starting the script sequence..."

python 1_institutions_fetcher.py
python 2_website_crawler.py
python 3_urls_for_course_recommendation.py
python 4_course_recommendation.py
python 5_urls_for_contact_info.py
python 6_contact_extractor.py
python 7_final_output_generator.py

echo "Script sequence finished."