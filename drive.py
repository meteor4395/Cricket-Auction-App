import pandas as pd
import requests
import re
import os

# ==== CONFIGURATION ====
EXCEL_FILE = "input.xlsx"   # your Excel file
OUTPUT_FILE = "output.xlsx" # updated Excel with new column
DOWNLOAD_FOLDER = "downloads" # folder to save images

# Make download folder if not exists
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Read Excel
df = pd.read_excel(EXCEL_FILE)

# Ensure 'photo' column exists
if 'photo' not in df.columns:
    raise ValueError("Excel must contain a column named 'photo' with Google Drive links.")

# Function to extract file ID from Google Drive link
def extract_file_id(url):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None

# Function to download file from Google Drive
def download_file_from_google_drive(file_id, dest_path):
    URL = "https://drive.google.com/uc?export=download&id={}".format(file_id)
    response = requests.get(URL, stream=True)
    if response.status_code == 200:
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        return True
    return False

# Process each row
downloaded_paths = []
for index, row in df.iterrows():
    link = row['photo']
    if pd.isna(link):
        downloaded_paths.append(None)
        continue

    file_id = extract_file_id(str(link))
    if not file_id:
        downloaded_paths.append(None)
        continue

    # Save with row index as filename
    filename = f"photo_{index}.jpg"
    dest_path = os.path.join(DOWNLOAD_FOLDER, filename)

    success = download_file_from_google_drive(file_id, dest_path)
    if success:
        downloaded_paths.append(dest_path)
    else:
        downloaded_paths.append(None)

# Add new column
df['downloaded_photo'] = downloaded_paths

# Save back to Excel
df.to_excel(OUTPUT_FILE, index=False)

print("✅ Download complete! Updated file saved as", OUTPUT_FILE)
